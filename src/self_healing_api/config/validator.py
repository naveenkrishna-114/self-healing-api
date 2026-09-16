"""
validator.py — Eager configuration validation for ClientConfig.

All validation runs at client construction time, not at request time.
This means misconfiguration is caught immediately with a clear error
message, rather than silently producing incorrect behaviour mid-flight.

Design rules
------------
- Every validation check raises ConfigurationValueError with field name + value.
- The validator collects ALL errors before raising, not just the first one.
- No network calls, no side effects — pure validation logic.
"""

from __future__ import annotations

import logging
import warnings

from self_healing_api.config.models import (
    CircuitBreakerConfig,
    ClientConfig,
    FallbackConfig,
    HealthConfig,
    IdempotencyConfig,
    ObservabilityConfig,
    RateLimitConfig,
    RetryConfig,
    RoutingConfig,
    TimeoutConfig,
)
from self_healing_api.errors.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class ConfigValidator:
    """
    Validates a ClientConfig and all its nested config objects.

    Usage
    -----
    ::

        validator = ConfigValidator()
        validator.validate(config)   # raises ConfigurationError if invalid
    """

    def validate(self, config: ClientConfig) -> None:
        """
        Validate the complete ClientConfig.

        Collects all validation errors and raises a single
        ConfigurationError listing every problem found.

        Parameters
        ----------
        config : ClientConfig
            The configuration to validate.

        Raises
        ------
        ConfigurationError
            If one or more validation rules are violated.
        ConfigurationValueError
            For a single specific field violation (also wrapped in
            ConfigurationError when multiple errors exist).
        """
        errors: list[str] = []

        # Run all validators and collect errors
        errors.extend(self._validate_base_url(config))
        errors.extend(self._validate_timeout(config.timeout))
        errors.extend(self._validate_retry(config.retry))
        errors.extend(self._validate_circuit_breaker(config.circuit_breaker))
        errors.extend(self._validate_health(config.health))
        errors.extend(self._validate_routing(config.routing))
        errors.extend(self._validate_rate_limit(config.rate_limit))
        errors.extend(self._validate_fallback(config.fallback))
        errors.extend(self._validate_observability(config.observability))
        errors.extend(self._validate_idempotency(config.idempotency))
        errors.extend(self._validate_ssl_warning(config))

        if errors:
            summary = "; ".join(errors)
            raise ConfigurationError(
                f"ClientConfig validation failed with {len(errors)} error(s): {summary}"
            )

    # ── Per-section validators ────────────────────────────────────────────────

    def _validate_base_url(self, config: ClientConfig) -> list[str]:
        errors: list[str] = []
        urls = [config.base_url, *config.endpoints]
        all_urls = [u for u in urls if u]

        if not config.base_url and not config.endpoints:
            errors.append(
                "ClientConfig.base_url: at least one URL must be provided "
                "(set base_url or endpoints)"
            )
            return errors

        for url in all_urls:
            if not isinstance(url, str):
                errors.append(f"ClientConfig URL: must be a string, got {type(url).__name__!r}")
            elif not url.startswith(("http://", "https://")):
                errors.append(
                    f"ClientConfig URL {url!r}: must start with 'http://' or 'https://'"
                )
        return errors

    def _validate_timeout(self, cfg: TimeoutConfig) -> list[str]:
        errors: list[str] = []

        if not isinstance(cfg.connect, (int, float)) or cfg.connect <= 0:
            errors.append(
                f"TimeoutConfig.connect: must be a positive number, got {cfg.connect!r}"
            )
        if not isinstance(cfg.read, (int, float)) or cfg.read <= 0:
            errors.append(
                f"TimeoutConfig.read: must be a positive number, got {cfg.read!r}"
            )
        if not isinstance(cfg.total, (int, float)) or cfg.total <= 0:
            errors.append(
                f"TimeoutConfig.total: must be a positive number, got {cfg.total!r}"
            )
        if (
            isinstance(cfg.connect, (int, float))
            and isinstance(cfg.total, (int, float))
            and cfg.connect > cfg.total
        ):
            errors.append(
                f"TimeoutConfig.connect ({cfg.connect}) must not exceed total ({cfg.total})"
            )
        return errors

    def _validate_retry(self, cfg: RetryConfig) -> list[str]:
        errors: list[str] = []

        if not isinstance(cfg.max_attempts, int) or cfg.max_attempts < 1:
            errors.append(
                f"RetryConfig.max_attempts: must be an integer >= 1, got {cfg.max_attempts!r}"
            )
        if cfg.backoff not in ("exponential", "linear", "fixed"):
            errors.append(
                f"RetryConfig.backoff: must be 'exponential', 'linear', or 'fixed', "
                f"got {cfg.backoff!r}"
            )
        if not isinstance(cfg.base_delay, (int, float)) or cfg.base_delay <= 0:
            errors.append(
                f"RetryConfig.base_delay: must be a positive number, got {cfg.base_delay!r}"
            )
        if not isinstance(cfg.max_delay, (int, float)) or cfg.max_delay <= 0:
            errors.append(
                f"RetryConfig.max_delay: must be a positive number, got {cfg.max_delay!r}"
            )
        if (
            isinstance(cfg.base_delay, (int, float))
            and isinstance(cfg.max_delay, (int, float))
            and cfg.base_delay > cfg.max_delay
        ):
            errors.append(
                f"RetryConfig.base_delay ({cfg.base_delay}) must not exceed "
                f"max_delay ({cfg.max_delay})"
            )
        if cfg.jitter_strategy not in ("full", "equal", "decorrelated"):
            errors.append(
                f"RetryConfig.jitter_strategy: must be 'full', 'equal', or 'decorrelated', "
                f"got {cfg.jitter_strategy!r}"
            )
        if not isinstance(cfg.retryable_status_codes, frozenset):
            errors.append(
                "RetryConfig.retryable_status_codes: must be a frozenset, "
                f"got {type(cfg.retryable_status_codes).__name__!r}"
            )
        return errors

    def _validate_circuit_breaker(self, cfg: CircuitBreakerConfig) -> list[str]:
        errors: list[str] = []

        if not isinstance(cfg.failure_threshold, int) or cfg.failure_threshold < 1:
            errors.append(
                f"CircuitBreakerConfig.failure_threshold: must be integer >= 1, "
                f"got {cfg.failure_threshold!r}"
            )
        if not isinstance(cfg.success_threshold, int) or cfg.success_threshold < 1:
            errors.append(
                f"CircuitBreakerConfig.success_threshold: must be integer >= 1, "
                f"got {cfg.success_threshold!r}"
            )
        if (
            not isinstance(cfg.recovery_timeout, (int, float))
            or cfg.recovery_timeout <= 0
        ):
            errors.append(
                f"CircuitBreakerConfig.recovery_timeout: must be positive number, "
                f"got {cfg.recovery_timeout!r}"
            )
        if not isinstance(cfg.window_size, int) or cfg.window_size < 1:
            errors.append(
                f"CircuitBreakerConfig.window_size: must be integer >= 1, "
                f"got {cfg.window_size!r}"
            )
        return errors

    def _validate_health(self, cfg: HealthConfig) -> list[str]:
        errors: list[str] = []

        if not isinstance(cfg.unhealthy_threshold, int) or cfg.unhealthy_threshold < 1:
            errors.append(
                f"HealthConfig.unhealthy_threshold: must be integer >= 1, "
                f"got {cfg.unhealthy_threshold!r}"
            )
        if not isinstance(cfg.recovery_threshold, int) or cfg.recovery_threshold < 1:
            errors.append(
                f"HealthConfig.recovery_threshold: must be integer >= 1, "
                f"got {cfg.recovery_threshold!r}"
            )
        if not isinstance(cfg.check_interval, (int, float)) or cfg.check_interval <= 0:
            errors.append(
                f"HealthConfig.check_interval: must be positive number, "
                f"got {cfg.check_interval!r}"
            )
        return errors

    def _validate_routing(self, cfg: RoutingConfig) -> list[str]:
        errors: list[str] = []
        if cfg.strategy not in ("priority", "round_robin", "random"):
            errors.append(
                f"RoutingConfig.strategy: must be 'priority', 'round_robin', or 'random', "
                f"got {cfg.strategy!r}"
            )
        return errors

    def _validate_rate_limit(self, cfg: RateLimitConfig) -> list[str]:
        errors: list[str] = []
        if (
            not isinstance(cfg.max_retry_after_wait, (int, float))
            or cfg.max_retry_after_wait <= 0
        ):
            errors.append(
                f"RateLimitConfig.max_retry_after_wait: must be positive number, "
                f"got {cfg.max_retry_after_wait!r}"
            )
        return errors

    def _validate_fallback(self, cfg: FallbackConfig) -> list[str]:
        errors: list[str] = []
        if cfg.handler is not None and not callable(cfg.handler):
            errors.append(
                f"FallbackConfig.handler: must be callable or None, "
                f"got {type(cfg.handler).__name__!r}"
            )
        return errors

    def _validate_observability(self, cfg: ObservabilityConfig) -> list[str]:
        errors: list[str] = []
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if cfg.log_level.upper() not in valid_levels:
            errors.append(
                f"ObservabilityConfig.log_level: must be one of {valid_levels}, "
                f"got {cfg.log_level!r}"
            )
        return errors

    def _validate_idempotency(self, cfg: IdempotencyConfig) -> list[str]:
        errors: list[str] = []
        if not isinstance(cfg.header_name, str) or not cfg.header_name.strip():
            errors.append(
                f"IdempotencyConfig.header_name: must be a non-empty string, "
                f"got {cfg.header_name!r}"
            )
        return errors

    def _validate_ssl_warning(self, config: ClientConfig) -> list[str]:
        """Not an error, but emit a loud warning when SSL verification is disabled."""
        if not config.verify_ssl:
            warnings.warn(
                "ClientConfig.verify_ssl=False disables TLS certificate verification. "
                "This must NEVER be used in production environments.",
                stacklevel=4,
                category=UserWarning,
            )
            logger.warning(
                "TLS verification disabled. verify_ssl=False should only be used "
                "in controlled development environments."
            )
        return []
