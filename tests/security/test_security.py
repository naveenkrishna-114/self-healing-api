"""Security unit tests for credential masking and TLS settings."""

import pytest

from self_healing_api.config.models import ClientConfig
from self_healing_api.config.validator import ConfigValidator
from self_healing_api.utils.masking import MASK_VALUE, SecretMasker


@pytest.mark.security
class TestSecurityMasking:
    def test_authorization_header_redacted(self) -> None:
        masker = SecretMasker()
        headers = {
            "Authorization": "Bearer secret-token-12345",
            "X-Api-Key": "my-secret-key",
            "User-Agent": "SelfHealingClient/0.1.0",
        }
        masked = masker.mask_headers(headers)
        assert masked["Authorization"] == MASK_VALUE
        assert masked["X-Api-Key"] == MASK_VALUE
        assert masked["User-Agent"] == "SelfHealingClient/0.1.0"

    def test_query_param_token_redacted(self) -> None:
        masker = SecretMasker()
        url = "https://api.example.com/v1/data?token=secret123&query=test"
        masked_url = masker.mask_url(url)
        assert f"token={MASK_VALUE}" in masked_url or "token=%2A%2A%2AMASKED%2A%2A%2A" in masked_url
        assert "query=test" in masked_url

    def test_ssl_warning_triggered_when_false(self) -> None:
        config = ClientConfig(base_url="https://api.example.com", verify_ssl=False)
        with pytest.warns(UserWarning, match="verify_ssl=False"):
            ConfigValidator().validate(config)
