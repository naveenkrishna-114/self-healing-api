"""
categories.py — ErrorCategory enum used by the ErrorClassifier.

Each category maps to a defined action in the resilience pipeline.
The classifier (classifier.py) assigns one of these categories to every
failure before the retry engine decides what to do next.
"""

from __future__ import annotations

from enum import Enum, auto


class ErrorCategory(Enum):
    """
    Classification of a request failure into an actionable category.

    The retry engine and circuit breaker consult this category to decide
    whether to retry, wait, open the circuit, or propagate the error.

    Categories
    ----------
    RETRYABLE_TRANSIENT
        A temporary network or server condition that is likely to resolve
        on its own (e.g. connection reset, 503 Service Unavailable).
        Safe to retry with backoff.

    RETRYABLE_TIMEOUT
        The request exceeded its timeout. May be retried only when the
        operation is idempotent or a valid idempotency key is present.

    RATE_LIMITED
        The server returned HTTP 429. Must wait for Retry-After (if present)
        before retrying. Consumes from the retry budget.

    SERVER_ERROR
        An HTTP 5xx response that indicates a server-side problem.
        Often retryable, subject to endpoint and provider behavior.

    CLIENT_ERROR
        An HTTP 4xx response indicating a problem with the request itself
        (e.g. 400 Bad Request, 422 Unprocessable Entity).
        Not retryable without changing the request.

    AUTHENTICATION_ERROR
        HTTP 401 Unauthorized. Do not retry blindly; credentials must be
        refreshed before retrying if supported.

    AUTHORIZATION_ERROR
        HTTP 403 Forbidden. Do not retry automatically.

    NOT_FOUND
        HTTP 404 Not Found. Not retryable unless resource
        creation/propagation is expected.

    CIRCUIT_OPEN
        The circuit breaker is OPEN. Fail fast or invoke fallback.
        No HTTP request was sent.

    NON_RETRYABLE
        Any error that must not be retried (e.g. malformed request,
        programming error, permanent failure).

    UNKNOWN
        Cannot be classified. Treated as non-retryable for safety.
    """

    RETRYABLE_TRANSIENT = auto()
    RETRYABLE_TIMEOUT = auto()
    RATE_LIMITED = auto()
    SERVER_ERROR = auto()
    CLIENT_ERROR = auto()
    AUTHENTICATION_ERROR = auto()
    AUTHORIZATION_ERROR = auto()
    NOT_FOUND = auto()
    CIRCUIT_OPEN = auto()
    NON_RETRYABLE = auto()
    UNKNOWN = auto()


# ── Convenience sets used by the retry engine ─────────────────────────────────

#: Categories that the retry engine may retry (subject to idempotency check).
RETRYABLE_CATEGORIES: frozenset[ErrorCategory] = frozenset(
    {
        ErrorCategory.RETRYABLE_TRANSIENT,
        ErrorCategory.RETRYABLE_TIMEOUT,
        ErrorCategory.SERVER_ERROR,
        ErrorCategory.RATE_LIMITED,
    }
)

#: Categories that must never be retried.
NON_RETRYABLE_CATEGORIES: frozenset[ErrorCategory] = frozenset(
    {
        ErrorCategory.CLIENT_ERROR,
        ErrorCategory.AUTHENTICATION_ERROR,
        ErrorCategory.AUTHORIZATION_ERROR,
        ErrorCategory.NOT_FOUND,
        ErrorCategory.CIRCUIT_OPEN,
        ErrorCategory.NON_RETRYABLE,
        ErrorCategory.UNKNOWN,
    }
)

#: Categories that should contribute to circuit-breaker failure counting.
CIRCUIT_BREAKER_COUNTING_CATEGORIES: frozenset[ErrorCategory] = frozenset(
    {
        ErrorCategory.RETRYABLE_TRANSIENT,
        ErrorCategory.RETRYABLE_TIMEOUT,
        ErrorCategory.SERVER_ERROR,
        ErrorCategory.RATE_LIMITED,
    }
)
