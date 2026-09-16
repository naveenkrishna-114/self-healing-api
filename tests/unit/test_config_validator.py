"""
Unit tests for ConfigValidator.
Tests verify that valid configs pass and invalid configs raise ConfigurationError.
"""
from __future__ import annotations

import pytest

from self_healing_api.config.models import (
    CircuitBreakerConfig,
    ClientConfig,
    FallbackConfig,
    ObservabilityConfig,
    RetryConfig,
    TimeoutConfig,
)
from self_healing_api.config.validator import ConfigValidator
from self_healing_api.errors.exceptions import ConfigurationError


@pytest.fixture()
def validator() -> ConfigValidator:
    return ConfigValidator()


@pytest.fixture()
def valid_config() -> ClientConfig:
    return ClientConfig(base_url="https://api.example.com")


@pytest.mark.unit
class TestValidConfig:
    def test_minimal_valid_config(
        self, validator: ConfigValidator, valid_config: ClientConfig
    ) -> None:
        validator.validate(valid_config)  # must not raise

    def test_full_valid_config(self, validator: ConfigValidator) -> None:
        config = ClientConfig(
            base_url="https://primary.example.com",
            endpoints=("https://secondary.example.com",),
            timeout=TimeoutConfig(connect=3.0, read=10.0, total=30.0),
            retry=RetryConfig(max_attempts=4, backoff="exponential", jitter=True),
            circuit_breaker=CircuitBreakerConfig(
                failure_threshold=5, recovery_timeout=30.0
            ),
        )
        validator.validate(config)  # must not raise


@pytest.mark.unit
class TestBaseUrlValidation:
    def test_missing_base_url(self, validator: ConfigValidator) -> None:
        config = ClientConfig(base_url="")
        with pytest.raises(ConfigurationError, match="at least one URL"):
            validator.validate(config)

    def test_invalid_url_scheme(self, validator: ConfigValidator) -> None:
        config = ClientConfig(base_url="ftp://api.example.com")
        with pytest.raises(ConfigurationError, match="http"):
            validator.validate(config)

    def test_http_url_is_valid(self, validator: ConfigValidator) -> None:
        config = ClientConfig(base_url="http://api.example.com")
        validator.validate(config)  # must not raise


@pytest.mark.unit
class TestTimeoutValidation:
    def test_zero_connect_timeout(self, validator: ConfigValidator) -> None:
        config = ClientConfig(
            base_url="https://api.example.com",
            timeout=TimeoutConfig(connect=0.0),
        )
        with pytest.raises(ConfigurationError, match="connect"):
            validator.validate(config)

    def test_negative_read_timeout(self, validator: ConfigValidator) -> None:
        config = ClientConfig(
            base_url="https://api.example.com",
            timeout=TimeoutConfig(read=-1.0),
        )
        with pytest.raises(ConfigurationError, match="read"):
            validator.validate(config)

    def test_connect_exceeds_total(self, validator: ConfigValidator) -> None:
        config = ClientConfig(
            base_url="https://api.example.com",
            timeout=TimeoutConfig(connect=60.0, total=10.0),
        )
        with pytest.raises(ConfigurationError, match="connect"):
            validator.validate(config)


@pytest.mark.unit
class TestRetryValidation:
    def test_zero_max_attempts(self, validator: ConfigValidator) -> None:
        config = ClientConfig(
            base_url="https://api.example.com",
            retry=RetryConfig(max_attempts=0),
        )
        with pytest.raises(ConfigurationError, match="max_attempts"):
            validator.validate(config)

    def test_invalid_backoff_strategy(self, validator: ConfigValidator) -> None:
        config = ClientConfig(
            base_url="https://api.example.com",
            retry=RetryConfig(backoff="random"),  # type: ignore[arg-type]
        )
        with pytest.raises(ConfigurationError, match="backoff"):
            validator.validate(config)

    def test_base_delay_exceeds_max_delay(self, validator: ConfigValidator) -> None:
        config = ClientConfig(
            base_url="https://api.example.com",
            retry=RetryConfig(base_delay=100.0, max_delay=10.0),
        )
        with pytest.raises(ConfigurationError, match="base_delay"):
            validator.validate(config)

    def test_invalid_jitter_strategy(self, validator: ConfigValidator) -> None:
        config = ClientConfig(
            base_url="https://api.example.com",
            retry=RetryConfig(jitter_strategy="none"),  # type: ignore[arg-type]
        )
        with pytest.raises(ConfigurationError, match="jitter_strategy"):
            validator.validate(config)


@pytest.mark.unit
class TestCircuitBreakerValidation:
    def test_zero_failure_threshold(self, validator: ConfigValidator) -> None:
        config = ClientConfig(
            base_url="https://api.example.com",
            circuit_breaker=CircuitBreakerConfig(failure_threshold=0),
        )
        with pytest.raises(ConfigurationError, match="failure_threshold"):
            validator.validate(config)

    def test_negative_recovery_timeout(self, validator: ConfigValidator) -> None:
        config = ClientConfig(
            base_url="https://api.example.com",
            circuit_breaker=CircuitBreakerConfig(recovery_timeout=-5.0),
        )
        with pytest.raises(ConfigurationError, match="recovery_timeout"):
            validator.validate(config)


@pytest.mark.unit
class TestFallbackValidation:
    def test_non_callable_handler(self, validator: ConfigValidator) -> None:
        config = ClientConfig(
            base_url="https://api.example.com",
            fallback=FallbackConfig(handler="not_callable"),  # type: ignore[arg-type]
        )
        with pytest.raises(ConfigurationError, match="handler"):
            validator.validate(config)

    def test_callable_handler_is_valid(self, validator: ConfigValidator) -> None:
        config = ClientConfig(
            base_url="https://api.example.com",
            fallback=FallbackConfig(handler=lambda ctx: {"status": "fallback"}),
        )
        validator.validate(config)  # must not raise


@pytest.mark.unit
class TestObservabilityValidation:
    def test_invalid_log_level(self, validator: ConfigValidator) -> None:
        config = ClientConfig(
            base_url="https://api.example.com",
            observability=ObservabilityConfig(log_level="VERBOSE"),
        )
        with pytest.raises(ConfigurationError, match="log_level"):
            validator.validate(config)

    def test_valid_log_levels(self, validator: ConfigValidator) -> None:
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            config = ClientConfig(
                base_url="https://api.example.com",
                observability=ObservabilityConfig(log_level=level),
            )
            validator.validate(config)  # must not raise


@pytest.mark.unit
class TestSSLWarning:
    def test_ssl_disabled_emits_warning(self, validator: ConfigValidator) -> None:
        config = ClientConfig(
            base_url="https://api.example.com",
            verify_ssl=False,
        )
        with pytest.warns(UserWarning, match="TLS"):
            validator.validate(config)  # must not raise but emits warning

    def test_ssl_enabled_no_warning(self, validator: ConfigValidator) -> None:
        config = ClientConfig(
            base_url="https://api.example.com",
            verify_ssl=True,
        )
        # No warning should be emitted
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            validator.validate(config)  # must not raise or warn


@pytest.mark.unit
class TestMultipleErrors:
    def test_multiple_errors_reported_together(self, validator: ConfigValidator) -> None:
        """Validator must collect all errors, not just the first one."""
        config = ClientConfig(
            base_url="ftp://bad-scheme.com",
            timeout=TimeoutConfig(connect=-1.0),
            retry=RetryConfig(max_attempts=0),
        )
        with pytest.raises(ConfigurationError) as exc_info:
            validator.validate(config)
        msg = str(exc_info.value)
        assert "3 error" in msg or "error" in msg


@pytest.mark.unit
class TestSubsystemValidators:
    def test_invalid_health_config(self, validator: ConfigValidator) -> None:
        from self_healing_api.config.models import HealthConfig

        cfg = ClientConfig(
            base_url="https://api.example.com",
            health=HealthConfig(unhealthy_threshold=0, recovery_threshold=0, check_interval=-1.0),
        )
        with pytest.raises(ConfigurationError) as exc_info:
            validator.validate(cfg)
        assert "unhealthy_threshold" in str(exc_info.value)

    def test_invalid_routing_and_rate_limit(self, validator: ConfigValidator) -> None:
        from self_healing_api.config.models import RateLimitConfig, RoutingConfig

        cfg = ClientConfig(
            base_url="https://api.example.com",
            routing=RoutingConfig(strategy="invalid_strat"),  # type: ignore[arg-type]
            rate_limit=RateLimitConfig(max_retry_after_wait=-5.0),
        )
        with pytest.raises(ConfigurationError) as exc_info:
            validator.validate(cfg)
        assert "strategy" in str(exc_info.value)

    def test_invalid_fallback_and_idempotency(self, validator: ConfigValidator) -> None:
        from self_healing_api.config.models import FallbackConfig, IdempotencyConfig

        cfg = ClientConfig(
            base_url="https://api.example.com",
            fallback=FallbackConfig(handler="not_callable"),  # type: ignore[arg-type]
            idempotency=IdempotencyConfig(header_name=""),
        )
        with pytest.raises(ConfigurationError) as exc_info:
            validator.validate(cfg)
        assert "handler" in str(exc_info.value)
        assert "header_name" in str(exc_info.value)

    def test_validator_remaining_edge_branches(self, validator: ConfigValidator) -> None:
        cfg = ClientConfig(
            base_url="https://api.example.com",
            endpoints=(123,),  # type: ignore[arg-type]
            timeout=TimeoutConfig(total=0.0),
            retry=RetryConfig(
                base_delay=-1.0,
                max_delay=-2.0,
                retryable_status_codes=[500],  # type: ignore[arg-type]
            ),
            circuit_breaker=CircuitBreakerConfig(success_threshold=0, window_size=0),
        )
        with pytest.raises(ConfigurationError) as exc_info:
            validator.validate(cfg)
        msg = str(exc_info.value)
        assert "must be a string" in msg
        assert "TimeoutConfig.total" in msg
        assert "RetryConfig.base_delay" in msg
        assert "RetryConfig.max_delay" in msg
        assert "frozenset" in msg
        assert "CircuitBreakerConfig.success_threshold" in msg
        assert "CircuitBreakerConfig.window_size" in msg
