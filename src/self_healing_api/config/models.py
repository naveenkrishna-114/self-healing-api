"""
models.py — Configuration dataclasses for the self_healing_api package.

All config objects are frozen dataclasses (immutable after construction).
Validation is performed by config/validator.py at client construction time.

Design decisions
----------------
- Frozen dataclasses: configuration must not change mid-flight.
- All fields have sensible defaults: minimal config required from developer.
- Types are strict: no silent coercion of wrong types.
- Callables (fallback handler, observability hooks) are typed with Protocols.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

# ── Timeout configuration ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class TimeoutConfig:
    """
    Controls how long the client waits at each stage of a request.

    Parameters
    ----------
    connect : float
        Maximum seconds to wait when establishing the connection.
        Default: 5.0 seconds.
    read : float
        Maximum seconds to wait for the server to send a response.
        Default: 30.0 seconds.
    total : float
        Hard ceiling on the entire operation (connect + read + retries).
        Default: 60.0 seconds.

    Example
    -------
    ::

        TimeoutConfig(connect=3.0, read=10.0, total=30.0)
    """

    connect: float = 5.0
    read: float = 30.0
    total: float = 60.0


# ── Retry configuration ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class RetryConfig:
    """
    Controls when and how the client retries failed requests.

    Parameters
    ----------
    max_attempts : int
        Total number of attempts including the first. Must be >= 1.
        Default: 3.
    backoff : Literal["exponential", "linear", "fixed"]
        Backoff strategy between attempts.
        - "exponential": delay doubles each attempt (recommended).
        - "linear":      delay increases by base_delay each attempt.
        - "fixed":       delay is always base_delay.
        Default: "exponential".
    base_delay : float
        Starting delay in seconds. Default: 1.0.
    max_delay : float
        Cap on the computed delay. Prevents runaway waits. Default: 60.0.
    jitter : bool
        Whether to add randomness to the delay to prevent retry storms.
        Default: True.
    jitter_strategy : Literal["full", "equal", "decorrelated"]
        - "full":         random(0, delay) — widest spread.
        - "equal":        delay/2 + random(0, delay/2) — bounded minimum.
        - "decorrelated": random(base_delay, prev_delay * 3) — AWS-style.
        Default: "full".
    retryable_status_codes : frozenset[int]
        HTTP status codes that are eligible for retry.
        Default: {500, 502, 503, 504}.

    Example
    -------
    ::

        RetryConfig(
            max_attempts=4,
            backoff="exponential",
            jitter=True,
            retryable_status_codes=frozenset({500, 503}),
        )
    """

    max_attempts: int = 3
    backoff: Literal["exponential", "linear", "fixed"] = "exponential"
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: bool = True
    jitter_strategy: Literal["full", "equal", "decorrelated"] = "full"
    retryable_status_codes: frozenset[int] = field(
        default_factory=lambda: frozenset({500, 502, 503, 504})
    )


# ── Circuit breaker configuration ─────────────────────────────────────────────

@dataclass(frozen=True)
class CircuitBreakerConfig:
    """
    Controls circuit-breaker behaviour per endpoint.

    The circuit breaker uses a CLOSED → OPEN → HALF_OPEN state machine.

    Parameters
    ----------
    enabled : bool
        Whether the circuit breaker is active. Default: True.
    failure_threshold : int
        Number of qualifying failures within the window before the circuit
        transitions from CLOSED to OPEN. Default: 5.
    success_threshold : int
        Number of consecutive successes in HALF_OPEN before the circuit
        transitions back to CLOSED. Default: 2.
    recovery_timeout : float
        Seconds the circuit stays OPEN before transitioning to HALF_OPEN
        to allow a probe request. Default: 30.0.
    window_size : int
        Sliding window of recent requests used to count failures.
        Default: 10.

    Example
    -------
    ::

        CircuitBreakerConfig(
            enabled=True,
            failure_threshold=5,
            recovery_timeout=30.0,
        )
    """

    enabled: bool = True
    failure_threshold: int = 5
    success_threshold: int = 2
    recovery_timeout: float = 30.0
    window_size: int = 10


# ── Health monitoring configuration ───────────────────────────────────────────

@dataclass(frozen=True)
class HealthConfig:
    """
    Controls passive health monitoring per endpoint.

    Parameters
    ----------
    enabled : bool
        Whether health monitoring is active. Default: True.
    unhealthy_threshold : int
        Consecutive failures required to mark an endpoint UNHEALTHY.
        Default: 3.
    recovery_threshold : int
        Consecutive successes required to mark an endpoint HEALTHY again.
        Default: 2.
    health_check_path : str | None
        Optional path for active health-check pings. If None, only
        passive monitoring from real requests is used. Default: None.
    check_interval : float
        Seconds between active health-check pings (only used when
        health_check_path is set). Default: 30.0.
    """

    enabled: bool = True
    unhealthy_threshold: int = 3
    recovery_threshold: int = 2
    health_check_path: str | None = None
    check_interval: float = 30.0


# ── Routing configuration ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class RoutingConfig:
    """
    Controls how the client selects endpoints when multiple are configured.

    Parameters
    ----------
    strategy : Literal["priority", "round_robin", "random"]
        - "priority":    always try endpoints in configured order.
        - "round_robin": distribute across healthy endpoints.
        - "random":      random healthy endpoint selection.
        Default: "priority".
    failover_enabled : bool
        Whether to try alternate endpoints when the primary fails.
        Default: True.
    """

    strategy: Literal["priority", "round_robin", "random"] = "priority"
    failover_enabled: bool = True


# ── Rate-limit configuration ──────────────────────────────────────────────────

@dataclass(frozen=True)
class RateLimitConfig:
    """
    Controls how the client handles HTTP 429 rate-limit responses.

    Parameters
    ----------
    respect_retry_after : bool
        Whether to honour the Retry-After header from the server.
        Default: True.
    max_retry_after_wait : float
        Cap on the Retry-After wait in seconds. If Retry-After exceeds
        this value, RateLimitError is raised immediately instead of
        waiting. Prevents indefinite blocking. Default: 120.0.
    backoff_on_429 : bool
        Whether to apply exponential backoff when no Retry-After header
        is present. Default: True.
    """

    respect_retry_after: bool = True
    max_retry_after_wait: float = 120.0
    backoff_on_429: bool = True


# ── Fallback configuration ────────────────────────────────────────────────────

@dataclass(frozen=True)
class FallbackConfig:
    """
    Controls fallback behaviour when all resilience mechanisms are exhausted.

    The package never invents a fallback — it calls what you configure.
    At least one of handler, cache_last_success, or static_response
    should be set, otherwise the fallback is a no-op and the error is
    propagated.

    Parameters
    ----------
    handler : Callable | None
        A callable that receives the RequestContext and returns a response.
        Signature: ``fn(context: RequestContext) -> Any``
        Default: None.
    cache_last_success : bool
        Return the last known-good response (with staleness metadata).
        Default: False.
    static_response : Any
        A static value to return as the fallback response. Default: None.
    """

    handler: Callable[..., Any] | None = None
    cache_last_success: bool = False
    static_response: Any = None


# ── Observability configuration ───────────────────────────────────────────────

@dataclass(frozen=True)
class ObservabilityConfig:
    """
    Controls logging, metrics, and tracing behaviour.

    Parameters
    ----------
    log_level : str
        Python logging level name. Default: "INFO".
    mask_headers : frozenset[str]
        Request/response header names whose values are redacted in logs
        and telemetry. Default: Authorization, X-Api-Key.
    mask_body_fields : frozenset[str]
        JSON body field names whose values are redacted. Default: empty.
    metrics_enabled : bool
        Whether to emit Prometheus-compatible metrics (requires
        prometheus_client extra). Default: False.
    tracing_enabled : bool
        Whether to emit OpenTelemetry spans (requires opentelemetry
        extra). Default: False.
    """

    log_level: str = "INFO"
    mask_headers: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"Authorization", "X-Api-Key", "X-Auth-Token", "Cookie"}
        )
    )
    mask_body_fields: frozenset[str] = field(default_factory=frozenset)
    metrics_enabled: bool = False
    tracing_enabled: bool = False


# ── Idempotency configuration ─────────────────────────────────────────────────

@dataclass(frozen=True)
class IdempotencyConfig:
    """
    Controls idempotency safeguards for retry-sensitive operations.

    Parameters
    ----------
    enabled : bool
        Whether idempotency enforcement is active. Default: True.
    header_name : str
        The HTTP header used to send the idempotency key to the server.
        Default: "Idempotency-Key".
    auto_generate : bool
        If True and no key is provided for a non-idempotent operation,
        a UUID v4 is auto-generated with a warning.
        If False (default), IdempotencyError is raised instead.
        Default: False (strict mode).
    """

    enabled: bool = True
    header_name: str = "Idempotency-Key"
    auto_generate: bool = False


# ── Master client configuration ───────────────────────────────────────────────

@dataclass(frozen=True)
class ClientConfig:
    """
    Master configuration object for SelfHealingClient.

    Combines all per-concern config objects into one place.
    Pass this to SelfHealingClient, or use the convenience keyword
    arguments on the client constructor.

    Parameters
    ----------
    base_url : str
        Primary base URL. Required.
    endpoints : list[str]
        Additional endpoint URLs for failover. Optional.
    timeout : TimeoutConfig
        Timeout settings. Defaults to TimeoutConfig().
    retry : RetryConfig
        Retry settings. Defaults to RetryConfig().
    circuit_breaker : CircuitBreakerConfig
        Circuit-breaker settings. Defaults to CircuitBreakerConfig().
    health : HealthConfig
        Health monitoring settings. Defaults to HealthConfig().
    routing : RoutingConfig
        Routing/failover settings. Defaults to RoutingConfig().
    rate_limit : RateLimitConfig
        Rate-limit handling settings. Defaults to RateLimitConfig().
    fallback : FallbackConfig
        Fallback settings. Defaults to FallbackConfig().
    observability : ObservabilityConfig
        Observability settings. Defaults to ObservabilityConfig().
    idempotency : IdempotencyConfig
        Idempotency settings. Defaults to IdempotencyConfig().
    default_headers : dict[str, str]
        Headers sent on every request. Default: empty.
    verify_ssl : bool
        Whether to verify TLS certificates. MUST be True in production.
        Default: True.

    Example
    -------
    ::

        config = ClientConfig(
            base_url="https://api.example.com",
            retry=RetryConfig(max_attempts=4),
            circuit_breaker=CircuitBreakerConfig(failure_threshold=3),
        )
        client = SelfHealingClient(config)
    """

    base_url: str = ""
    endpoints: tuple[str, ...] = field(default_factory=tuple)
    timeout: TimeoutConfig = field(default_factory=TimeoutConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    health: HealthConfig = field(default_factory=HealthConfig)
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    fallback: FallbackConfig = field(default_factory=FallbackConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    idempotency: IdempotencyConfig = field(default_factory=IdempotencyConfig)
    default_headers: dict[str, str] = field(default_factory=dict)
    verify_ssl: bool = True
