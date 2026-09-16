"""
policy.py — Timeout policy enforcement.

Wraps a transport call with timeout tracking and maps transport-level
timeout exceptions into our own SelfHealingTimeoutError hierarchy.

The policy does NOT call time.sleep() or set OS-level timeouts — those
are handled by httpx internally. What this policy does is:

1. Record when the request started (via the injected Clock).
2. Check whether the TOTAL operation timeout has been exceeded before
   each attempt (prevents pointless attempts when total time is gone).
3. Translate raw httpx timeout exceptions into our typed hierarchy so
   the ErrorClassifier always receives consistent exception types.

Design note
-----------
The ``total`` timeout is a hard ceiling across ALL attempts including
retry waits. If retry backoff has already consumed the total budget,
TimeoutPolicy.check_total() raises ConnectTimeoutError immediately
rather than letting another attempt start.
"""

from __future__ import annotations

from self_healing_api.config.models import TimeoutConfig
from self_healing_api.errors.exceptions import (
    ConnectTimeoutError,
    ReadTimeoutError,
    SelfHealingTimeoutError,
)
from self_healing_api.utils.clock import Clock, SystemClock


class TimeoutPolicy:
    """
    Enforces timeout budgets across a request's full lifecycle.

    Parameters
    ----------
    config : TimeoutConfig
        The timeout configuration for this policy instance.
    clock : Clock
        Clock used to measure elapsed time. Inject FakeClock in tests.

    Usage
    -----
    ::

        policy = TimeoutPolicy(config=TimeoutConfig(total=30.0), clock=clock)
        policy.start()                 # record operation start time

        # Before each attempt:
        policy.check_total_budget()    # raises if total time exceeded

        try:
            response = transport.send(request)
        except Exception as exc:
            raise policy.translate(exc) from exc
    """

    def __init__(
        self,
        config: TimeoutConfig,
        clock: Clock | None = None,
    ) -> None:
        self._config = config
        self._clock: Clock = clock or SystemClock()
        self._start_mono: float | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Record the operation start time.

        Must be called once before the first attempt. Subsequent calls
        (e.g. on retry) are intentionally ignored — the total budget
        counts from the very first call.
        """
        if self._start_mono is None:
            self._start_mono = self._clock.monotonic()

    def elapsed(self) -> float:
        """
        Return seconds elapsed since ``start()`` was called.

        Returns 0.0 if ``start()`` has not been called yet.
        """
        if self._start_mono is None:
            return 0.0
        return self._clock.monotonic() - self._start_mono

    def remaining(self) -> float:
        """
        Return the remaining total budget in seconds.

        Returns ``total`` if ``start()`` has not been called.
        Never returns a negative value — floor is 0.0.
        """
        remaining = self._config.total - self.elapsed()
        return max(0.0, remaining)

    # ── Budget check ──────────────────────────────────────────────────────────

    def check_total_budget(self, endpoint: str = "", request_id: str = "") -> None:
        """
        Raise ConnectTimeoutError if the total budget is exhausted.

        Call this before each attempt to short-circuit the request before
        sending it when there is no time left.

        Parameters
        ----------
        endpoint : str
            Endpoint URL for error context.
        request_id : str
            Request ID for error context.

        Raises
        ------
        ConnectTimeoutError
            If total elapsed time has exceeded ``config.total``.
        """
        if self._start_mono is not None and self.elapsed() >= self._config.total:
            raise ConnectTimeoutError(
                f"Total operation timeout of {self._config.total}s exceeded "
                f"after {self.elapsed():.2f}s",
                timeout_seconds=self._config.total,
                endpoint=endpoint,
                request_id=request_id,
            )

    # ── Exception translation ─────────────────────────────────────────────────

    def translate(
        self,
        exc: BaseException,
        endpoint: str = "",
        request_id: str = "",
    ) -> SelfHealingTimeoutError | BaseException:
        """
        Translate a raw transport exception into our timeout hierarchy.

        If the exception is already one of ours, return it unchanged.
        If it is an httpx timeout, map it precisely.
        Otherwise return the original exception unmodified.

        Parameters
        ----------
        exc : BaseException
            The exception caught from the transport layer.
        endpoint : str
            Endpoint URL for error context.
        request_id : str
            Request ID for error context.

        Returns
        -------
        SelfHealingTimeoutError | BaseException
            Translated exception (or original if not a timeout).
        """
        # Already our own type — return as-is
        if isinstance(exc, SelfHealingTimeoutError):
            return exc

        try:
            import httpx

            if isinstance(exc, httpx.ConnectTimeout):
                return ConnectTimeoutError(
                    f"Connection timeout after {self._config.connect}s: {exc}",
                    timeout_seconds=self._config.connect,
                    endpoint=endpoint,
                    request_id=request_id,
                )
            if isinstance(exc, httpx.ReadTimeout):
                return ReadTimeoutError(
                    f"Read timeout after {self._config.read}s: {exc}",
                    timeout_seconds=self._config.read,
                    endpoint=endpoint,
                    request_id=request_id,
                )
            if isinstance(exc, httpx.TimeoutException):
                return SelfHealingTimeoutError(
                    f"Request timeout: {exc}",
                    timeout_seconds=self._config.total,
                    endpoint=endpoint,
                    request_id=request_id,
                )
        except ImportError:
            pass

        # Standard library TimeoutError
        if isinstance(exc, TimeoutError):
            return SelfHealingTimeoutError(
                f"Operation timed out: {exc}",
                timeout_seconds=self._config.total,
                endpoint=endpoint,
                request_id=request_id,
            )

        # Not a timeout — return unchanged so the caller can handle it
        return exc

    # ── Per-attempt timeout values for the transport ──────────────────────────

    @property
    def connect_timeout(self) -> float:
        """Connect timeout in seconds to pass to the transport."""
        return self._config.connect

    @property
    def read_timeout(self) -> float:
        """Read timeout in seconds to pass to the transport."""
        # Cap read timeout at remaining total budget
        return min(self._config.read, max(0.1, self.remaining()))
