"""
classifier.py — ErrorClassifier

Maps raw exceptions and HTTP status codes to an ErrorCategory so the
retry engine can make consistent, policy-driven decisions.

Design rules
------------
- Classification is pure and stateless — no side effects.
- The classifier never retries or raises; it only categorises.
- Consuming code (retry engine, circuit breaker) acts on the category.
- Unknown/unexpected inputs default to NON_RETRYABLE for safety.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from self_healing_api.errors.categories import ErrorCategory

if TYPE_CHECKING:
    pass


class ErrorClassifier:
    """
    Classifies failures into an ErrorCategory.

    Usage
    -----
    ::

        classifier = ErrorClassifier(
            retryable_status_codes={500, 502, 503, 504},
        )
        category = classifier.classify_status_code(503)
        # → ErrorCategory.SERVER_ERROR

        category = classifier.classify_exception(exc)
        # → ErrorCategory.RETRYABLE_TRANSIENT
    """

    # Default retryable 5xx codes — can be overridden via constructor.
    DEFAULT_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset(
        {500, 502, 503, 504}
    )

    def __init__(
        self,
        retryable_status_codes: frozenset[int] | set[int] | None = None,
    ) -> None:
        self._retryable_status_codes: frozenset[int] = (
            frozenset(retryable_status_codes)
            if retryable_status_codes is not None
            else self.DEFAULT_RETRYABLE_STATUS_CODES
        )

    # ── Public interface ──────────────────────────────────────────────────────

    def classify_status_code(self, status_code: int) -> ErrorCategory:
        """
        Map an HTTP status code to an ErrorCategory.

        Parameters
        ----------
        status_code : int
            The HTTP response status code.

        Returns
        -------
        ErrorCategory
            The category that best describes this status code.
        """
        if status_code < 400:
            # 1xx, 2xx, 3xx — not an error
            return ErrorCategory.NON_RETRYABLE

        if status_code == 429:
            return ErrorCategory.RATE_LIMITED

        if status_code == 401:
            return ErrorCategory.AUTHENTICATION_ERROR

        if status_code == 403:
            return ErrorCategory.AUTHORIZATION_ERROR

        if status_code == 404:
            return ErrorCategory.NOT_FOUND

        if 400 <= status_code < 500:
            # All other 4xx — client errors, not retryable without request change
            return ErrorCategory.CLIENT_ERROR

        if status_code in self._retryable_status_codes:
            return ErrorCategory.SERVER_ERROR

        if 500 <= status_code < 600:
            # 5xx not in the retryable set — treat as non-retryable server error
            return ErrorCategory.NON_RETRYABLE

        return ErrorCategory.UNKNOWN

    def classify_exception(self, exc: BaseException) -> ErrorCategory:
        """
        Map a Python exception to an ErrorCategory.

        Checks in order of specificity. Falls back to UNKNOWN (treated
        as non-retryable) for anything unrecognised.

        Parameters
        ----------
        exc : BaseException
            The exception raised during the request.

        Returns
        -------
        ErrorCategory
            The category that best describes this exception.
        """
        # Import here to avoid circular imports at module load time.
        from self_healing_api.errors.exceptions import (
            CircuitOpenError,
            ConnectTimeoutError,
            ReadTimeoutError,
            SelfHealingTimeoutError,
        )

        # Our own exceptions
        if isinstance(exc, CircuitOpenError):
            return ErrorCategory.CIRCUIT_OPEN

        if isinstance(exc, (ConnectTimeoutError, ReadTimeoutError, SelfHealingTimeoutError)):
            return ErrorCategory.RETRYABLE_TIMEOUT

        # httpx exceptions (only imported if httpx is available)
        try:
            import httpx

            if isinstance(exc, httpx.ConnectTimeout):
                return ErrorCategory.RETRYABLE_TIMEOUT
            if isinstance(exc, httpx.ReadTimeout):
                return ErrorCategory.RETRYABLE_TIMEOUT
            if isinstance(exc, httpx.TimeoutException):
                return ErrorCategory.RETRYABLE_TIMEOUT
            if isinstance(exc, httpx.ConnectError):
                return ErrorCategory.RETRYABLE_TRANSIENT
            if isinstance(exc, httpx.RemoteProtocolError):
                return ErrorCategory.RETRYABLE_TRANSIENT
            if isinstance(exc, httpx.NetworkError):
                return ErrorCategory.RETRYABLE_TRANSIENT
            if isinstance(exc, httpx.HTTPStatusError):
                return self.classify_status_code(exc.response.status_code)
        except ImportError:
            pass

        # Standard library connection errors
        if isinstance(exc, ConnectionResetError):
            return ErrorCategory.RETRYABLE_TRANSIENT
        if isinstance(exc, ConnectionRefusedError):
            return ErrorCategory.RETRYABLE_TRANSIENT
        if isinstance(exc, ConnectionAbortedError):
            return ErrorCategory.RETRYABLE_TRANSIENT
        if isinstance(exc, ConnectionError):
            return ErrorCategory.RETRYABLE_TRANSIENT
        if isinstance(exc, TimeoutError):
            return ErrorCategory.RETRYABLE_TIMEOUT
        if isinstance(exc, OSError):
            # Covers BrokenPipeError, socket errors, etc.
            return ErrorCategory.RETRYABLE_TRANSIENT

        return ErrorCategory.UNKNOWN

    def is_retryable(self, category: ErrorCategory) -> bool:
        """Return True if this category may be retried (before idempotency check)."""
        from self_healing_api.errors.categories import RETRYABLE_CATEGORIES

        return category in RETRYABLE_CATEGORIES

    def counts_for_circuit_breaker(self, category: ErrorCategory) -> bool:
        """Return True if this category should increment the circuit-breaker counter."""
        from self_healing_api.errors.categories import CIRCUIT_BREAKER_COUNTING_CATEGORIES

        return category in CIRCUIT_BREAKER_COUNTING_CATEGORIES
