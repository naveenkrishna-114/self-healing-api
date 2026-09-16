"""
backoff.py — Backoff delay calculators.

Three strategies are supported:
- exponential: delay = min(base * 2^attempt, max_delay)
- linear:      delay = min(base * (attempt + 1), max_delay)
- fixed:       delay = base  (constant, regardless of attempt)

All calculators are pure functions — no state, no side effects.
The retry engine applies jitter on top of the base delay from here.
"""
from __future__ import annotations

import math


def exponential_delay(base: float, attempt: int, max_delay: float) -> float:
    """
    Compute exponential backoff delay.

    delay = min(base * 2^attempt, max_delay)

    Parameters
    ----------
    base : float   Starting delay in seconds.
    attempt : int  Zero-based attempt index (0 = first retry).
    max_delay : float  Cap on computed delay.
    """
    delay = base * math.pow(2, attempt)
    return min(delay, max_delay)


def linear_delay(base: float, attempt: int, max_delay: float) -> float:
    """
    Compute linear backoff delay.

    delay = min(base * (attempt + 1), max_delay)
    """
    delay = base * (attempt + 1)
    return min(delay, max_delay)


def fixed_delay(base: float, max_delay: float) -> float:
    """
    Compute fixed delay (always the base, capped at max_delay).
    """
    return min(base, max_delay)


def compute_delay(
    strategy: str,
    base: float,
    attempt: int,
    max_delay: float,
) -> float:
    """
    Dispatch to the correct delay calculator based on strategy name.

    Parameters
    ----------
    strategy : str   One of "exponential", "linear", "fixed".
    base : float     Base delay in seconds.
    attempt : int    Zero-based retry index.
    max_delay : float  Maximum delay cap.

    Returns
    -------
    float  Computed delay in seconds (before jitter).
    """
    if strategy == "exponential":
        return exponential_delay(base, attempt, max_delay)
    if strategy == "linear":
        return linear_delay(base, attempt, max_delay)
    if strategy == "fixed":
        return fixed_delay(base, max_delay)
    # Fallback — should not happen if config is validated
    return exponential_delay(base, attempt, max_delay)
