"""
Self-Healing API Resilience Package
=====================================

A reusable Python developer package for reliable API communication
and controlled automated failure recovery.

Usage::

    from self_healing_api import SelfHealingClient
    from self_healing_api.config import TimeoutConfig, RetryConfig, CircuitBreakerConfig

    client = SelfHealingClient(
        base_url="https://api.example.com",
        timeout=TimeoutConfig(connect=5.0, read=10.0, total=30.0),
        retry=RetryConfig(max_attempts=3, backoff="exponential", jitter=True),
        circuit_breaker=CircuitBreakerConfig(enabled=True, failure_threshold=5),
    )

    response = client.get("/data")
"""

from __future__ import annotations

# Package version — single source of truth
__version__ = "0.1.0"
__author__ = "Self-Healing API Project"
__license__ = "MIT"

# Public config surface
# Public client interfaces
from self_healing_api.client import AsyncSelfHealingClient, SelfHealingClient
from self_healing_api.config import (
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

# Public exception surface
from self_healing_api.errors import (
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

__all__ = [
    # Meta
    "__version__",
    "__author__",
    "__license__",
    # Client
    "SelfHealingClient",
    "AsyncSelfHealingClient",
    # Config
    "ClientConfig",
    "TimeoutConfig",
    "RetryConfig",
    "CircuitBreakerConfig",
    "HealthConfig",
    "RoutingConfig",
    "RateLimitConfig",
    "FallbackConfig",
    "ObservabilityConfig",
    "IdempotencyConfig",
    # Exceptions
    "SelfHealingError",
    "ConfigurationError",
    "ConfigurationValueError",
    "RequestError",
    "RetryExhaustedError",
    "CircuitOpenError",
    "SelfHealingTimeoutError",
    "ConnectTimeoutError",
    "ReadTimeoutError",
    "RateLimitError",
    "FallbackError",
    "AllEndpointsUnavailableError",
    "IdempotencyError",
    "CompatibilityError",
    "SchemaMismatchError",
    "MappingValidationError",
    "ApprovalRequiredError",
]
