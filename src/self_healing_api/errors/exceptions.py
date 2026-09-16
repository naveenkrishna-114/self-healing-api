"""
exceptions.py — Complete public exception hierarchy for self_healing_api.

Every exception carries structured context so consuming applications can log,
alert, or handle failures precisely without string-parsing error messages.

Hierarchy
---------
SelfHealingError                        ← base for everything
├── ConfigurationError                  ← raised at client construction time
│   └── ConfigurationValueError        ← specific field has an invalid value
├── RequestError                        ← base for all request-time failures
│   ├── RetryExhaustedError            ← all retry attempts consumed
│   ├── CircuitOpenError               ← circuit is OPEN, request short-circuited
│   ├── SelfHealingTimeoutError        ← request timed out
│   │   ├── ConnectTimeoutError        ← could not establish connection in time
│   │   └── ReadTimeoutError           ← connected but response took too long
│   ├── RateLimitError                 ← 429 with no further retry possible
│   ├── FallbackError                  ← fallback callable itself raised
│   └── AllEndpointsUnavailableError   ← every configured endpoint is unhealthy
├── IdempotencyError                    ← unsafe retry on non-idempotent operation
└── CompatibilityError                 ← compatibility layer failure
    ├── SchemaMismatchError            ← observed schema differs from known schema
    ├── MappingValidationError         ← proposed mapping failed validation
    └── ApprovalRequiredError          ← AI suggestion is pending approval
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# ── Base ──────────────────────────────────────────────────────────────────────

class SelfHealingError(Exception):
    """
    Base exception for the self_healing_api package.

    All exceptions raised by this package inherit from this class, so
    consuming applications can catch everything with a single except clause
    when needed::

        try:
            response = client.get("/data")
        except SelfHealingError as exc:
            logger.error("resilience failure", extra=exc.to_dict())
    """

    def __init__(
        self,
        message: str,
        *,
        endpoint: str | None = None,
        request_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.endpoint = endpoint
        self.request_id = request_id
        self.context: dict[str, Any] = context or {}
        self.timestamp: datetime = datetime.now(tz=UTC)

    def to_dict(self) -> dict[str, Any]:
        """Return a structured representation safe for logging."""
        return {
            "error_type": type(self).__name__,
            "message": self.message,
            "endpoint": self.endpoint,
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
        }

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"message={self.message!r}, "
            f"endpoint={self.endpoint!r}, "
            f"request_id={self.request_id!r})"
        )


# ── Configuration errors ──────────────────────────────────────────────────────

class ConfigurationError(SelfHealingError):
    """
    Raised when the client is constructed with invalid configuration.

    This is an eager validation failure — it fires at construction time,
    not at request time, so misconfiguration is caught immediately.
    """


class ConfigurationValueError(ConfigurationError):
    """
    Raised when a specific configuration field has an invalid value.

    Attributes
    ----------
    field : str
        The name of the configuration field that is invalid.
    invalid_value : Any
        The value that was rejected.
    """

    def __init__(
        self,
        message: str,
        *,
        field: str,
        invalid_value: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.field = field
        self.invalid_value = invalid_value

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["field"] = self.field
        d["invalid_value"] = repr(self.invalid_value)
        return d


# ── Request-time errors ───────────────────────────────────────────────────────

class RequestError(SelfHealingError):
    """
    Base for all errors that occur during a request lifecycle.

    Attributes
    ----------
    status_code : int | None
        HTTP status code if the error came from an HTTP response.
    attempt_count : int
        Number of attempts made before this error was raised.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        attempt_count: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.status_code = status_code
        self.attempt_count = attempt_count

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["status_code"] = self.status_code
        d["attempt_count"] = self.attempt_count
        return d


class RetryExhaustedError(RequestError):
    """
    Raised when all retry attempts have been consumed without a successful response.

    Attributes
    ----------
    max_attempts : int
        The configured maximum number of attempts.
    last_exception : BaseException | None
        The last exception that caused a retry failure, if available.
    """

    def __init__(
        self,
        message: str,
        *,
        max_attempts: int,
        last_exception: BaseException | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, attempt_count=max_attempts, **kwargs)
        self.max_attempts = max_attempts
        self.last_exception = last_exception

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["max_attempts"] = self.max_attempts
        d["last_exception"] = repr(self.last_exception) if self.last_exception else None
        return d


class CircuitOpenError(RequestError):
    """
    Raised when the circuit breaker is OPEN and the request is short-circuited.

    The circuit opened because the failure threshold was reached. No HTTP
    request was sent. The caller should invoke a fallback or wait for
    the recovery timeout to elapse.

    Attributes
    ----------
    recovery_timeout : float | None
        Seconds until the circuit transitions to HALF_OPEN.
    """

    def __init__(
        self,
        message: str,
        *,
        recovery_timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.recovery_timeout = recovery_timeout

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["recovery_timeout"] = self.recovery_timeout
        return d


class SelfHealingTimeoutError(RequestError):
    """
    Raised when a request exceeds its configured timeout.

    Note: named SelfHealingTimeoutError to avoid shadowing the built-in
    TimeoutError while remaining clear in stack traces.

    Attributes
    ----------
    timeout_seconds : float | None
        The timeout value that was exceeded.
    """

    def __init__(
        self,
        message: str,
        *,
        timeout_seconds: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.timeout_seconds = timeout_seconds

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["timeout_seconds"] = self.timeout_seconds
        return d


class ConnectTimeoutError(SelfHealingTimeoutError):
    """Raised when the connection could not be established within the connect timeout."""


class ReadTimeoutError(SelfHealingTimeoutError):
    """Raised when the connection was established but the response took too long."""


class RateLimitError(RequestError):
    """
    Raised when an HTTP 429 response is received and no further retry is possible
    (Retry-After exceeds max_retry_after_wait, or attempts are exhausted).

    Attributes
    ----------
    retry_after : float | None
        The Retry-After value from the response header, in seconds.
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, status_code=429, **kwargs)
        self.retry_after = retry_after

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["retry_after"] = self.retry_after
        return d


class FallbackError(RequestError):
    """
    Raised when the fallback handler itself raises an exception.

    Wraps both the original request failure and the fallback failure so
    nothing is silently lost.

    Attributes
    ----------
    original_error : Exception | None
        The error that triggered the fallback.
    fallback_error : Exception | None
        The error raised by the fallback callable.
    """

    def __init__(
        self,
        message: str,
        *,
        original_error: Exception | None = None,
        fallback_error: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.original_error = original_error
        self.fallback_error = fallback_error

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["original_error"] = repr(self.original_error) if self.original_error else None
        d["fallback_error"] = repr(self.fallback_error) if self.fallback_error else None
        return d


class AllEndpointsUnavailableError(RequestError):
    """
    Raised when every configured endpoint is marked unhealthy and no
    healthy endpoint can be selected for the request.

    Attributes
    ----------
    endpoints : list[str]
        The list of all configured endpoints that were unavailable.
    """

    def __init__(
        self,
        message: str,
        *,
        endpoints: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.endpoints: list[str] = endpoints or []

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["endpoints"] = self.endpoints
        return d


# ── Idempotency errors ────────────────────────────────────────────────────────

class IdempotencyError(SelfHealingError):
    """
    Raised when a retry would be attempted on a non-idempotent operation
    (e.g. POST, PATCH) without a valid idempotency key.

    A timeout does not prove the server did not complete the operation.
    Retrying without an idempotency key risks creating duplicate business
    operations.

    Attributes
    ----------
    http_method : str
        The HTTP method of the unsafe operation (e.g. "POST").
    """

    def __init__(
        self,
        message: str,
        *,
        http_method: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.http_method = http_method

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["http_method"] = self.http_method
        return d


# ── Compatibility errors ──────────────────────────────────────────────────────

class CompatibilityError(SelfHealingError):
    """Base for all errors from the optional API compatibility layer."""


class SchemaMismatchError(CompatibilityError):
    """
    Raised when the observed API response schema differs from the known schema.

    Attributes
    ----------
    missing_fields : list[str]
        Fields present in the known schema but absent from the observed response.
    unexpected_fields : list[str]
        Fields present in the observed response but absent from the known schema.
    """

    def __init__(
        self,
        message: str,
        *,
        missing_fields: list[str] | None = None,
        unexpected_fields: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.missing_fields: list[str] = missing_fields or []
        self.unexpected_fields: list[str] = unexpected_fields or []

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["missing_fields"] = self.missing_fields
        d["unexpected_fields"] = self.unexpected_fields
        return d


class MappingValidationError(CompatibilityError):
    """
    Raised when a proposed compatibility mapping fails validation.

    AI-generated or manually created mappings must pass validation before
    they can be submitted for approval. This error is raised when they fail.

    Attributes
    ----------
    rule_id : str | None
        Identifier of the mapping rule that failed validation.
    validation_errors : list[str]
        Specific validation failures.
    """

    def __init__(
        self,
        message: str,
        *,
        rule_id: str | None = None,
        validation_errors: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.rule_id = rule_id
        self.validation_errors: list[str] = validation_errors or []

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["rule_id"] = self.rule_id
        d["validation_errors"] = self.validation_errors
        return d


class ApprovalRequiredError(CompatibilityError):
    """
    Raised when an AI-suggested compatibility mapping is pending approval
    and cannot be applied until explicitly approved.

    AI suggestions are NEVER auto-applied. This error signals that a
    suggestion exists but requires developer/operator review.

    Attributes
    ----------
    suggestion_id : str | None
        Identifier of the pending AI suggestion.
    confidence : float | None
        Confidence score of the AI suggestion (0.0 - 1.0).
    """

    def __init__(
        self,
        message: str,
        *,
        suggestion_id: str | None = None,
        confidence: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.suggestion_id = suggestion_id
        self.confidence = confidence

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["suggestion_id"] = self.suggestion_id
        d["confidence"] = self.confidence
        return d
