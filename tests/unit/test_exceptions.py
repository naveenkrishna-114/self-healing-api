"""
Unit tests for the exception hierarchy.
"""
from __future__ import annotations

import pytest

from self_healing_api.errors.exceptions import (
    AllEndpointsUnavailableError,
    ApprovalRequiredError,
    CircuitOpenError,
    CompatibilityError,
    ConfigurationError,
    ConfigurationValueError,
    ConnectTimeoutError,
    FallbackError,
    IdempotencyError,
    MappingValidationError,
    RateLimitError,
    ReadTimeoutError,
    RequestError,
    RetryExhaustedError,
    SchemaMismatchError,
    SelfHealingError,
    SelfHealingTimeoutError,
)


@pytest.mark.unit
class TestSelfHealingError:
    def test_basic_construction(self) -> None:
        exc = SelfHealingError("something went wrong")
        assert str(exc) == "something went wrong"
        assert exc.message == "something went wrong"
        assert exc.endpoint is None
        assert exc.request_id is None
        assert exc.context == {}
        assert exc.timestamp is not None

    def test_with_all_fields(self) -> None:
        exc = SelfHealingError(
            "failure",
            endpoint="https://api.example.com",
            request_id="req-123",
            context={"attempt": 1},
        )
        assert exc.endpoint == "https://api.example.com"
        assert exc.request_id == "req-123"
        assert exc.context == {"attempt": 1}

    def test_to_dict(self) -> None:
        exc = SelfHealingError("failure", endpoint="https://api.example.com")
        d = exc.to_dict()
        assert d["error_type"] == "SelfHealingError"
        assert d["message"] == "failure"
        assert d["endpoint"] == "https://api.example.com"
        assert "timestamp" in d

    def test_is_exception(self) -> None:
        exc = SelfHealingError("test")
        assert isinstance(exc, Exception)

    def test_repr(self) -> None:
        exc = SelfHealingError("msg", endpoint="https://ep", request_id="rid")
        assert "SelfHealingError" in repr(exc)
        assert "https://ep" in repr(exc)


@pytest.mark.unit
class TestConfigurationErrors:
    def test_configuration_error_is_self_healing_error(self) -> None:
        exc = ConfigurationError("bad config")
        assert isinstance(exc, SelfHealingError)

    def test_configuration_value_error(self) -> None:
        exc = ConfigurationValueError(
            "invalid value",
            field="retry.max_attempts",
            invalid_value=-1,
        )
        assert exc.field == "retry.max_attempts"
        assert exc.invalid_value == -1
        assert isinstance(exc, ConfigurationError)

    def test_configuration_value_error_to_dict(self) -> None:
        exc = ConfigurationValueError("bad", field="timeout", invalid_value=0)
        d = exc.to_dict()
        assert d["field"] == "timeout"
        assert "invalid_value" in d


@pytest.mark.unit
class TestRequestErrors:
    def test_retry_exhausted_error(self) -> None:
        inner = ConnectionError("connection refused")
        exc = RetryExhaustedError(
            "all retries exhausted",
            max_attempts=3,
            last_exception=inner,
            endpoint="https://api.example.com",
        )
        assert exc.max_attempts == 3
        assert exc.last_exception is inner
        assert exc.attempt_count == 3
        assert isinstance(exc, RequestError)

    def test_retry_exhausted_to_dict(self) -> None:
        exc = RetryExhaustedError("exhausted", max_attempts=3)
        d = exc.to_dict()
        assert d["max_attempts"] == 3

    def test_circuit_open_error(self) -> None:
        exc = CircuitOpenError(
            "circuit is open",
            recovery_timeout=30.0,
            endpoint="https://api.example.com",
        )
        assert exc.recovery_timeout == 30.0
        assert isinstance(exc, RequestError)

    def test_timeout_error_hierarchy(self) -> None:
        connect_exc = ConnectTimeoutError("connect timeout", timeout_seconds=5.0)
        read_exc = ReadTimeoutError("read timeout", timeout_seconds=30.0)
        assert isinstance(connect_exc, SelfHealingTimeoutError)
        assert isinstance(read_exc, SelfHealingTimeoutError)
        assert isinstance(connect_exc, RequestError)
        assert connect_exc.timeout_seconds == 5.0
        assert read_exc.timeout_seconds == 30.0

    def test_rate_limit_error(self) -> None:
        exc = RateLimitError("rate limited", retry_after=60.0)
        assert exc.status_code == 429
        assert exc.retry_after == 60.0
        assert isinstance(exc, RequestError)

    def test_fallback_error(self) -> None:
        original = ValueError("original failure")
        fallback = RuntimeError("fallback failure")
        exc = FallbackError(
            "fallback also failed",
            original_error=original,
            fallback_error=fallback,
        )
        assert exc.original_error is original
        assert exc.fallback_error is fallback
        assert isinstance(exc, RequestError)

    def test_all_endpoints_unavailable(self) -> None:
        exc = AllEndpointsUnavailableError(
            "no healthy endpoints",
            endpoints=["https://primary.com", "https://secondary.com"],
        )
        assert len(exc.endpoints) == 2
        assert isinstance(exc, RequestError)


@pytest.mark.unit
class TestIdempotencyError:
    def test_idempotency_error(self) -> None:
        exc = IdempotencyError(
            "unsafe retry on POST without idempotency key",
            http_method="POST",
        )
        assert exc.http_method == "POST"
        assert isinstance(exc, SelfHealingError)

    def test_to_dict_includes_method(self) -> None:
        exc = IdempotencyError("unsafe", http_method="PATCH")
        d = exc.to_dict()
        assert d["http_method"] == "PATCH"


@pytest.mark.unit
class TestCompatibilityErrors:
    def test_schema_mismatch_error(self) -> None:
        exc = SchemaMismatchError(
            "schema changed",
            missing_fields=["user_id"],
            unexpected_fields=["userId"],
        )
        assert exc.missing_fields == ["user_id"]
        assert exc.unexpected_fields == ["userId"]
        assert isinstance(exc, CompatibilityError)

    def test_mapping_validation_error(self) -> None:
        exc = MappingValidationError(
            "mapping failed",
            rule_id="rule-001",
            validation_errors=["field type mismatch"],
        )
        assert exc.rule_id == "rule-001"
        assert "field type mismatch" in exc.validation_errors
        assert isinstance(exc, CompatibilityError)

    def test_approval_required_error(self) -> None:
        exc = ApprovalRequiredError(
            "pending approval",
            suggestion_id="ai-suggestion-42",
            confidence=0.87,
        )
        assert exc.suggestion_id == "ai-suggestion-42"
        assert exc.confidence == pytest.approx(0.87)
        assert isinstance(exc, CompatibilityError)


@pytest.mark.unit
def test_exception_inheritance_tree() -> None:
    """Verify the complete inheritance chain is correct."""
    # All errors are catchable as SelfHealingError
    for exc_class in [
        ConfigurationError,
        ConfigurationValueError,
        RequestError,
        RetryExhaustedError,
        CircuitOpenError,
        SelfHealingTimeoutError,
        ConnectTimeoutError,
        ReadTimeoutError,
        RateLimitError,
        FallbackError,
        AllEndpointsUnavailableError,
        IdempotencyError,
        CompatibilityError,
        SchemaMismatchError,
        MappingValidationError,
        ApprovalRequiredError,
    ]:
        _ = exc_class("test") if exc_class not in (
            ConfigurationValueError,
            RetryExhaustedError,
        ) else None

        assert issubclass(exc_class, SelfHealingError), (
            f"{exc_class.__name__} does not inherit from SelfHealingError"
        )


@pytest.mark.unit
def test_all_specialized_exceptions_to_dict() -> None:
    c_err = CircuitOpenError("open", recovery_timeout=30.0)
    assert c_err.to_dict()["recovery_timeout"] == 30.0

    t_err = SelfHealingTimeoutError("timeout", timeout_seconds=5.0)
    assert t_err.to_dict()["timeout_seconds"] == 5.0

    r_err = RateLimitError("rate limit", retry_after=10.0)
    assert r_err.to_dict()["retry_after"] == 10.0

    f_err = FallbackError(
        "fallback", original_error=ValueError("orig"), fallback_error=KeyError("fb")
    )
    assert "ValueError" in str(f_err.to_dict()["original_error"])

    e_err = AllEndpointsUnavailableError("no endpoints", endpoints=["e1", "e2"])
    assert e_err.to_dict()["endpoints"] == ["e1", "e2"]

    s_err = SchemaMismatchError("mismatch", missing_fields=["m1"], unexpected_fields=["u1"])
    assert s_err.to_dict()["missing_fields"] == ["m1"]

    m_err = MappingValidationError("invalid", rule_id="r1", validation_errors=["err1"])
    assert m_err.to_dict()["rule_id"] == "r1"

    a_err = ApprovalRequiredError("need approval", suggestion_id="s1", confidence=0.9)
    assert a_err.to_dict()["suggestion_id"] == "s1"
