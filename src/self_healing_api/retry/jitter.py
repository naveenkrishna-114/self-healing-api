"""
jitter.py — Jitter strategies to prevent retry storms.

When many clients retry simultaneously after a failure, they can
flood the recovering service in waves — the "thundering herd" problem.
Jitter randomizes the delay so retries are spread out over time.

Three strategies (from AWS Architecture Blog):

full         random(0, delay)
             Widest spread. Minimum wait is 0, so some clients retry
             immediately. Best for reducing peak load.

equal        delay/2 + random(0, delay/2)
             Bounded minimum (at least half the computed delay).
             Good balance between spread and guaranteed minimum wait.

decorrelated random(base, prev_delay * 3)
             Each retry is uncorrelated with the previous. Tends to
             produce lower average delays than full jitter.
             Requires tracking the previous delay.
"""
from __future__ import annotations

import random


def full_jitter(delay: float) -> float:
    """Return a random value in [0, delay]."""
    return random.uniform(0.0, delay)


def equal_jitter(delay: float) -> float:
    """Return a value in [delay/2, delay]."""
    half = delay / 2.0
    return half + random.uniform(0.0, half)


def decorrelated_jitter(base: float, prev_delay: float) -> float:
    """Return a value in [base, prev_delay * 3], capped implicitly by caller."""
    return random.uniform(base, prev_delay * 3.0)


def apply_jitter(
    strategy: str,
    delay: float,
    base: float = 1.0,
    prev_delay: float | None = None,
) -> float:
    """
    Apply the named jitter strategy to a computed delay.

    Parameters
    ----------
    strategy : str         One of "full", "equal", "decorrelated".
    delay : float          The computed backoff delay (pre-jitter).
    base : float           Base delay (needed for decorrelated).
    prev_delay : float     Previous attempt delay (needed for decorrelated).

    Returns
    -------
    float  Jittered delay in seconds. Always >= 0.
    """
    if strategy == "full":
        return full_jitter(delay)
    if strategy == "equal":
        return equal_jitter(delay)
    if strategy == "decorrelated":
        effective_prev = prev_delay if prev_delay is not None else base
        return decorrelated_jitter(base, effective_prev)
    return full_jitter(delay)
