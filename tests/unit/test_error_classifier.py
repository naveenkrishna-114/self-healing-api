"""
Unit tests for ErrorClassifier.
"""
from __future__ import annotations

import pytest

from self_healing_api.errors.categories import ErrorCategory
from self_healing_api.errors.classifier import ErrorClassifier
from self_healing_api.errors.exceptions import (
    CircuitOpenError,
    ConnectTimeoutError,
    ReadTimeoutError,
    SelfHealingTimeoutError,
)


@pytest.fixture()
def classifier() -> ErrorClassifier:
    return ErrorClassifier()


@pytest.mark.unit
class TestClassifyStatusCode:
    def test_200_is_non_retryable(self, classifier: ErrorClassifier) -> None:
        assert classifier.classify_status_code(200) == ErrorCategory.NON_RETRYABLE

    def test_429_is_rate_limited(self, classifier: ErrorClassifier) -> None:
        assert classifier.classify_status_code(429) == ErrorCategory.RATE_LIMITED

    def test_401_is_authentication_error(self, classifier: ErrorClassifier) -> None:
        assert classifier.classify_status_code(401) == ErrorCategory.AUTHENTICATION_ERROR

    def test_403_is_authorization_error(self, classifier: ErrorClassifier) -> None:
        assert classifier.classify_status_code(403) == ErrorCategory.AUTHORIZATION_ERROR

    def test_404_is_not_found(self, classifier: ErrorClassifier) -> None:
        assert classifier.classify_status_code(404) == ErrorCategory.NOT_FOUND

    def test_400_is_client_error(self, classifier: ErrorClassifier) -> None:
        assert classifier.classify_status_code(400) == ErrorCategory.CLIENT_ERROR

    def test_422_is_client_error(self, classifier: ErrorClassifier) -> None:
        assert classifier.classify_status_code(422) == ErrorCategory.CLIENT_ERROR

    def test_500_is_server_error(self, classifier: ErrorClassifier) -> None:
        assert classifier.classify_status_code(500) == ErrorCategory.SERVER_ERROR

    def test_502_is_server_error(self, classifier: ErrorClassifier) -> None:
        assert classifier.classify_status_code(502) == ErrorCategory.SERVER_ERROR

    def test_503_is_server_error(self, classifier: ErrorClassifier) -> None:
        assert classifier.classify_status_code(503) == ErrorCategory.SERVER_ERROR

    def test_504_is_server_error(self, classifier: ErrorClassifier) -> None:
        assert classifier.classify_status_code(504) == ErrorCategory.SERVER_ERROR

    def test_non_retryable_5xx(self, classifier: ErrorClassifier) -> None:
        # 501 is not in the default retryable set
        assert classifier.classify_status_code(501) == ErrorCategory.NON_RETRYABLE

    def test_custom_retryable_codes(self) -> None:
        c = ErrorClassifier(retryable_status_codes={503, 429})
        assert c.classify_status_code(503) == ErrorCategory.SERVER_ERROR
        # 500 not in custom set → non-retryable
        assert c.classify_status_code(500) == ErrorCategory.NON_RETRYABLE


@pytest.mark.unit
class TestClassifyException:
    def test_circuit_open_error(self, classifier: ErrorClassifier) -> None:
        exc = CircuitOpenError("open")
        assert classifier.classify_exception(exc) == ErrorCategory.CIRCUIT_OPEN

    def test_connect_timeout_error(self, classifier: ErrorClassifier) -> None:
        exc = ConnectTimeoutError("timeout")
        assert classifier.classify_exception(exc) == ErrorCategory.RETRYABLE_TIMEOUT

    def test_read_timeout_error(self, classifier: ErrorClassifier) -> None:
        exc = ReadTimeoutError("timeout")
        assert classifier.classify_exception(exc) == ErrorCategory.RETRYABLE_TIMEOUT

    def test_self_healing_timeout_error(self, classifier: ErrorClassifier) -> None:
        exc = SelfHealingTimeoutError("timeout")
        assert classifier.classify_exception(exc) == ErrorCategory.RETRYABLE_TIMEOUT

    def test_connection_reset_error(self, classifier: ErrorClassifier) -> None:
        exc = ConnectionResetError("reset")
        assert classifier.classify_exception(exc) == ErrorCategory.RETRYABLE_TRANSIENT

    def test_connection_refused_error(self, classifier: ErrorClassifier) -> None:
        exc = ConnectionRefusedError("refused")
        assert classifier.classify_exception(exc) == ErrorCategory.RETRYABLE_TRANSIENT

    def test_os_error(self, classifier: ErrorClassifier) -> None:
        exc = OSError("network error")
        assert classifier.classify_exception(exc) == ErrorCategory.RETRYABLE_TRANSIENT

    def test_stdlib_timeout_error(self, classifier: ErrorClassifier) -> None:
        exc = TimeoutError("timed out")
        assert classifier.classify_exception(exc) == ErrorCategory.RETRYABLE_TIMEOUT

    def test_unknown_exception(self, classifier: ErrorClassifier) -> None:
        exc = ValueError("unexpected")
        assert classifier.classify_exception(exc) == ErrorCategory.UNKNOWN


@pytest.mark.unit
class TestHelperMethods:
    def test_is_retryable_true(self, classifier: ErrorClassifier) -> None:
        assert classifier.is_retryable(ErrorCategory.RETRYABLE_TRANSIENT) is True
        assert classifier.is_retryable(ErrorCategory.SERVER_ERROR) is True
        assert classifier.is_retryable(ErrorCategory.RATE_LIMITED) is True

    def test_is_retryable_false(self, classifier: ErrorClassifier) -> None:
        assert classifier.is_retryable(ErrorCategory.CLIENT_ERROR) is False
        assert classifier.is_retryable(ErrorCategory.AUTHENTICATION_ERROR) is False
        assert classifier.is_retryable(ErrorCategory.CIRCUIT_OPEN) is False
        assert classifier.is_retryable(ErrorCategory.UNKNOWN) is False

    def test_counts_for_circuit_breaker(self, classifier: ErrorClassifier) -> None:
        assert classifier.counts_for_circuit_breaker(ErrorCategory.SERVER_ERROR) is True
        assert classifier.counts_for_circuit_breaker(ErrorCategory.RETRYABLE_TRANSIENT) is True
        assert classifier.counts_for_circuit_breaker(ErrorCategory.CLIENT_ERROR) is False
        assert classifier.counts_for_circuit_breaker(ErrorCategory.AUTHENTICATION_ERROR) is False

    def test_httpx_exception_types(self, classifier: ErrorClassifier) -> None:
        import httpx

        req = httpx.Request("GET", "https://example.com")
        resp = httpx.Response(500, request=req)

        c = classifier.classify_exception
        assert c(httpx.ConnectTimeout("t")) == ErrorCategory.RETRYABLE_TIMEOUT
        assert c(httpx.ReadTimeout("t")) == ErrorCategory.RETRYABLE_TIMEOUT
        assert c(httpx.TimeoutException("t")) == ErrorCategory.RETRYABLE_TIMEOUT
        assert c(httpx.ConnectError("r")) == ErrorCategory.RETRYABLE_TRANSIENT
        assert c(httpx.NetworkError("n")) == ErrorCategory.RETRYABLE_TRANSIENT
        assert c(httpx.RemoteProtocolError("proto")) == ErrorCategory.RETRYABLE_TRANSIENT
        status_err = httpx.HTTPStatusError("500", request=req, response=resp)
        assert c(status_err) == ErrorCategory.SERVER_ERROR
        assert c(ConnectionAbortedError()) == ErrorCategory.RETRYABLE_TRANSIENT

    def test_classify_status_unknown_and_no_httpx(
        self, classifier: ErrorClassifier, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys

        assert classifier.classify_status_code(600) == ErrorCategory.UNKNOWN

        # Test classify_exception without httpx
        monkeypatch.setitem(sys.modules, "httpx", None)
        res = classifier.classify_exception(ConnectionResetError())
        assert res == ErrorCategory.RETRYABLE_TRANSIENT
