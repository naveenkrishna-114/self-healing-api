# Configuration Reference

All configuration objects in `self_healing_api.config` are frozen dataclasses.

| Config Dataclass | Key Parameters | Defaults |
|---|---|---|
| `TimeoutConfig` | `connect`, `read`, `total` | `connect=5.0`, `read=30.0`, `total=60.0` |
| `RetryConfig` | `max_attempts`, `backoff`, `base_delay`, `max_delay`, `jitter`, `jitter_strategy`, `retryable_status_codes` | `max_attempts=3`, `backoff="exponential"`, `base_delay=1.0`, `max_delay=60.0`, `jitter=True`, `jitter_strategy="full"`, `retryable_status_codes={500,502,503,504}` |
| `CircuitBreakerConfig` | `enabled`, `failure_threshold`, `success_threshold`, `recovery_timeout`, `window_size` | `enabled=True`, `failure_threshold=5`, `success_threshold=2`, `recovery_timeout=30.0`, `window_size=10` |
| `HealthConfig` | `enabled`, `unhealthy_threshold`, `recovery_threshold`, `health_check_path`, `check_interval` | `enabled=True`, `unhealthy_threshold=3`, `recovery_threshold=2`, `check_interval=30.0` |
| `RoutingConfig` | `strategy`, `failover_enabled` | `strategy="priority"`, `failover_enabled=True` |
| `RateLimitConfig` | `respect_retry_after`, `max_retry_after_wait`, `backoff_on_429` | `respect_retry_after=True`, `max_retry_after_wait=120.0`, `backoff_on_429=True` |
| `FallbackConfig` | `handler`, `cache_last_success`, `static_response` | `handler=None`, `cache_last_success=False`, `static_response=None` |
| `ObservabilityConfig` | `log_level`, `mask_headers`, `mask_body_fields`, `metrics_enabled`, `tracing_enabled` | `log_level="INFO"`, `metrics_enabled=False`, `tracing_enabled=False` |
| `IdempotencyConfig` | `enabled`, `header_name`, `auto_generate` | `enabled=True`, `header_name="Idempotency-Key"`, `auto_generate=False` |
