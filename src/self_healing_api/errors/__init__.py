"""
errors — Standardized public exception hierarchy and error classifier.
"""

from self_healing_api.errors.categories import (
    CIRCUIT_BREAKER_COUNTING_CATEGORIES,
    NON_RETRYABLE_CATEGORIES,
    RETRYABLE_CATEGORIES,
    ErrorCategory,
)
from self_healing_api.errors.classifier import ErrorClassifier
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

__all__ = [
    # Base
    "SelfHealingError",
    # Configuration
    "ConfigurationError",
    "ConfigurationValueError",
    # Request
    "RequestError",
    "RetryExhaustedError",
    "CircuitOpenError",
    "SelfHealingTimeoutError",
    "ConnectTimeoutError",
    "ReadTimeoutError",
    "RateLimitError",
    "FallbackError",
    "AllEndpointsUnavailableError",
    # Idempotency
    "IdempotencyError",
    # Compatibility
    "CompatibilityError",
    "SchemaMismatchError",
    "MappingValidationError",
    "ApprovalRequiredError",
    # Classifier
    "ErrorClassifier",
    "ErrorCategory",
    "RETRYABLE_CATEGORIES",
    "NON_RETRYABLE_CATEGORIES",
    "CIRCUIT_BREAKER_COUNTING_CATEGORIES",
]
