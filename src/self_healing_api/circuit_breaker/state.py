"""
state.py — CircuitState enum for the circuit breaker state machine.
"""
from __future__ import annotations

from enum import Enum, auto


class CircuitState(Enum):
    """
    Three-state circuit breaker model.

    CLOSED     Normal operation. Requests pass through. Failures are counted.
    OPEN       Failure threshold exceeded. Requests are rejected immediately
               (fast-fail). No HTTP calls are made.
    HALF_OPEN  Recovery probe. A limited number of requests are allowed through
               to test if the service has recovered. Success → CLOSED,
               failure → OPEN (reset recovery timer).
    """
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()
