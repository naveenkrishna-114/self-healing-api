"""
policy.py — RetryDecision: the decision object returned by RetryEngine.

Separates the decision (should we retry?) from the action (wait and retry).
This keeps the engine testable and the client orchestrator clean.
"""
from __future__ import annotations

from dataclasses import dataclass

from self_healing_api.errors.categories import ErrorCategory


@dataclass(frozen=True)
class RetryDecision:
    """
    The result of asking the RetryEngine whether to retry.

    Attributes
    ----------
    should_retry : bool      Whether another attempt should be made.
    delay : float            Seconds to wait before the next attempt.
    attempt : int            Current attempt number (1-based).
    category : ErrorCategory The error category that led to this decision.
    reason : str             Human-readable explanation for logs.
    """
    should_retry: bool
    delay: float
    attempt: int
    category: ErrorCategory
    reason: str = ""
