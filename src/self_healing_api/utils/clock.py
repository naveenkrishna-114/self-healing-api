"""
clock.py — Abstracted time source.

Injecting a Clock instead of calling time.time() / datetime.now() directly
makes every time-dependent module (circuit breaker, health monitor, retry
backoff) fully deterministic in tests — no sleep(), no real wall-clock
dependency.

Usage
-----
Production code receives a ``SystemClock`` (or the default).
Tests inject a ``FakeClock`` and advance time manually.

::

    # Production
    clock = SystemClock()
    now = clock.now()

    # Tests
    clock = FakeClock(start=0.0)
    clock.advance(30.0)   # simulate 30 seconds passing
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """
    Protocol for a time source.

    Any object with ``now()`` and ``monotonic()`` satisfies this protocol.
    """

    def now(self) -> datetime:
        """Return the current UTC datetime."""
        ...  # pragma: no cover

    def monotonic(self) -> float:
        """
        Return a monotonic timestamp in seconds.

        Used for measuring elapsed time (timeouts, recovery intervals).
        Not suitable for wall-clock display.
        """
        ...  # pragma: no cover


class SystemClock:
    """
    Real wall-clock implementation. Used in production.

    ``monotonic()`` uses ``time.monotonic()`` which never goes backwards,
    making it safe for measuring durations even across system-clock adjustments.
    """

    def now(self) -> datetime:
        """Return the current UTC datetime."""
        return datetime.now(tz=UTC)

    def monotonic(self) -> float:
        """Return ``time.monotonic()``."""
        return time.monotonic()


class FakeClock:
    """
    Deterministic clock for testing.

    Starts at ``start`` (default 0.0) and advances only when
    ``advance()`` is called explicitly. Never calls real system time.

    Example
    -------
    ::

        clock = FakeClock(start=1_000_000.0)
        t1 = clock.monotonic()   # → 1_000_000.0
        clock.advance(30.0)
        t2 = clock.monotonic()   # → 1_000_030.0
        assert t2 - t1 == 30.0
    """

    def __init__(self, start: float = 0.0) -> None:
        self._mono: float = start
        self._epoch: float = start

    def now(self) -> datetime:
        """Return a deterministic UTC datetime based on the fake epoch."""
        return datetime.fromtimestamp(self._epoch, tz=UTC)

    def monotonic(self) -> float:
        """Return the current fake monotonic time."""
        return self._mono

    def advance(self, seconds: float) -> None:
        """
        Advance both clocks by ``seconds``.

        Parameters
        ----------
        seconds : float
            Number of seconds to advance. Must be non-negative.
        """
        if seconds < 0:
            msg = f"FakeClock.advance() requires non-negative seconds, got {seconds}"
            raise ValueError(msg)
        self._mono += seconds
        self._epoch += seconds

    def set_monotonic(self, value: float) -> None:
        """Directly set the monotonic clock to an absolute value."""
        self._mono = value

    def __repr__(self) -> str:
        return f"FakeClock(mono={self._mono}, epoch={self._epoch})"
