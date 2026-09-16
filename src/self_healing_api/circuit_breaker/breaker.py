"""
breaker.py — CircuitBreaker state machine.

Implements the classic CLOSED → OPEN → HALF_OPEN → CLOSED cycle.

Safety guarantees
-----------------
- State transitions are protected by threading.Lock (thread-safe).
- Each SelfHealingClient owns its own CircuitBreaker per endpoint
  (no shared global state).
- Sliding window prevents stale open states from old failures.
- Clock is injected for deterministic testing (no real time.time calls).

Algorithm
---------
CLOSED:
    Allow all requests. Count failures in a sliding window of size
    `window_size`. When failure count >= failure_threshold → OPEN.

OPEN:
    Reject all requests immediately with CircuitOpenError.
    After recovery_timeout seconds → transition to HALF_OPEN.

HALF_OPEN:
    Allow up to `success_threshold` probe requests.
    If all succeed → CLOSED.
    If any fail → OPEN (reset recovery timer).
"""
from __future__ import annotations

import threading
from collections import deque

from self_healing_api.circuit_breaker.state import CircuitState
from self_healing_api.config.models import CircuitBreakerConfig
from self_healing_api.errors.exceptions import CircuitOpenError
from self_healing_api.utils.clock import Clock, SystemClock


class CircuitBreaker:
    """
    Thread-safe circuit breaker for a single endpoint.

    Parameters
    ----------
    config : CircuitBreakerConfig
    endpoint : str          The endpoint this breaker guards (for error messages).
    clock : Clock | None    Injected clock; uses SystemClock if None.

    Usage
    -----
    ::

        breaker = CircuitBreaker(config, endpoint="https://api.example.com")

        # Before each request:
        breaker.before_request()      # raises CircuitOpenError if OPEN

        # After each request:
        breaker.record_success()
        # or
        breaker.record_failure()
    """

    def __init__(
        self,
        config: CircuitBreakerConfig,
        endpoint: str = "",
        clock: Clock | None = None,
    ) -> None:
        self._config = config
        self._endpoint = endpoint
        self._clock: Clock = clock or SystemClock()
        self._lock = threading.Lock()

        self._state: CircuitState = CircuitState.CLOSED
        self._window: deque[bool] = deque(maxlen=config.window_size)
        self._open_at: float = 0.0          # monotonic time when circuit opened
        self._half_open_successes: int = 0  # probe successes in HALF_OPEN

    # ── Public interface ──────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        """Current circuit state (thread-safe read)."""
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    def before_request(self, request_id: str = "") -> None:
        """
        Check if the request is allowed.

        Call this before sending each request.

        Raises
        ------
        CircuitOpenError
            If the circuit is OPEN and the recovery timeout has not elapsed.
        """
        if not self._config.enabled:
            return

        with self._lock:
            self._maybe_transition_to_half_open()

            if self._state == CircuitState.OPEN:
                remaining = self._recovery_remaining()
                raise CircuitOpenError(
                    f"Circuit is OPEN for {self._endpoint!r}. "
                    f"Recovery in {remaining:.1f}s.",
                    recovery_timeout=remaining,
                    endpoint=self._endpoint,
                    request_id=request_id,
                )
            # HALF_OPEN: allow through (probe request)

    def record_success(self) -> None:
        """
        Record a successful request outcome.

        In HALF_OPEN: increments probe success counter.
        If success_threshold met → transition to CLOSED.
        In CLOSED: adds success to window.
        """
        if not self._config.enabled:
            return

        with self._lock:
            self._maybe_transition_to_half_open()
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self._config.success_threshold:
                    self._transition_to_closed()
            else:
                self._window.append(True)

    def record_failure(self) -> None:
        """
        Record a failed request outcome.

        In HALF_OPEN: any failure → back to OPEN (reset recovery timer).
        In CLOSED: add failure to window; check if threshold reached.
        """
        if not self._config.enabled:
            return

        with self._lock:
            self._maybe_transition_to_half_open()
            if self._state == CircuitState.HALF_OPEN:
                self._transition_to_open()
                return

            self._window.append(False)
            failure_count = self._count_failures()
            if failure_count >= self._config.failure_threshold:
                self._transition_to_open()

    def reset(self) -> None:
        """
        Forcibly reset to CLOSED state.

        Useful in tests and for manual circuit reset.
        """
        with self._lock:
            self._state = CircuitState.CLOSED
            self._window.clear()
            self._open_at = 0.0
            self._half_open_successes = 0

    # ── Internal transitions ──────────────────────────────────────────────────

    def _transition_to_open(self) -> None:
        """Transition to OPEN and record the time."""
        self._state = CircuitState.OPEN
        self._open_at = self._clock.monotonic()
        self._half_open_successes = 0

    def _transition_to_closed(self) -> None:
        """Transition to CLOSED and clear all state."""
        self._state = CircuitState.CLOSED
        self._window.clear()
        self._open_at = 0.0
        self._half_open_successes = 0

    def _maybe_transition_to_half_open(self) -> None:
        """
        If OPEN and recovery_timeout has elapsed, transition to HALF_OPEN.

        Must be called inside the lock.
        """
        if self._state == CircuitState.OPEN:
            elapsed = self._clock.monotonic() - self._open_at
            if elapsed >= self._config.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_successes = 0

    def _count_failures(self) -> int:
        """Count failures in the current sliding window."""
        return sum(1 for result in self._window if result is False)

    def _recovery_remaining(self) -> float:
        """Seconds remaining until HALF_OPEN transition."""
        elapsed = self._clock.monotonic() - self._open_at
        return max(0.0, self._config.recovery_timeout - elapsed)

    # ── Debug helpers ─────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(state={self._state.name}, "
            f"endpoint={self._endpoint!r}, "
            f"failures={self._count_failures()}/{self._config.failure_threshold})"
        )
