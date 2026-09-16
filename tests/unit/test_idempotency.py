"""Unit tests for IdempotencyGuard."""

import pytest

from self_healing_api.config.models import IdempotencyConfig
from self_healing_api.errors.exceptions import IdempotencyError
from self_healing_api.idempotency import IdempotencyGuard


@pytest.mark.unit
class TestIdempotencyGuard:
    def test_get_is_idempotent(self) -> None:
        guard = IdempotencyGuard(IdempotencyConfig())
        assert guard.is_idempotent_method("GET")
        assert guard.is_idempotent_method("PUT")
        assert guard.is_idempotent_method("DELETE")
        assert not guard.is_idempotent_method("POST")

    def test_retry_post_without_key_raises(self) -> None:
        guard = IdempotencyGuard(IdempotencyConfig(auto_generate=False))
        headers = {"content-type": "application/json"}
        with pytest.raises(IdempotencyError) as exc_info:
            guard.check_or_inject_key("POST", headers, attempt=2)
        assert exc_info.value.http_method == "POST"

    def test_retry_post_with_key_succeeds(self) -> None:
        guard = IdempotencyGuard(IdempotencyConfig(auto_generate=False))
        headers = {"idempotency-key": "my-custom-key"}
        result = guard.check_or_inject_key("POST", headers, attempt=2)
        assert result.get("idempotency-key") == "my-custom-key"

    def test_auto_generate_key_on_retry(self) -> None:
        guard = IdempotencyGuard(IdempotencyConfig(auto_generate=True))
        headers = {}
        result = guard.check_or_inject_key("POST", headers, attempt=2)
        assert "Idempotency-Key" in result
        assert len(result["Idempotency-Key"]) > 10

    def test_disabled_guard_returns_copy(self) -> None:
        guard = IdempotencyGuard(IdempotencyConfig(enabled=False))
        headers = {"h1": "v1"}
        res = guard.check_or_inject_key("POST", headers, attempt=2)
        assert res == headers
        assert res is not headers
