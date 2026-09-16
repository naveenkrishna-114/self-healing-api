# API Reference

## Main Developer Clients

### `SelfHealingClient`
Synchronous resilience client.

```python
from self_healing_api import SelfHealingClient
from self_healing_api.config import TimeoutConfig, RetryConfig, CircuitBreakerConfig

client = SelfHealingClient(
    base_url="https://api.example.com",
    timeout=TimeoutConfig(connect=5.0, read=10.0, total=30.0),
    retry=RetryConfig(max_attempts=3, backoff="exponential", jitter=True),
    circuit_breaker=CircuitBreakerConfig(enabled=True, failure_threshold=5),
)

response = client.get("/endpoint")
print(response.json())
```

### `AsyncSelfHealingClient`
Asynchronous resilience client for `asyncio`.

```python
from self_healing_api import AsyncSelfHealingClient

async with AsyncSelfHealingClient(base_url="https://api.example.com") as client:
    response = await client.get("/endpoint")
    print(response.json())
```

## Exception Hierarchy

- `SelfHealingError`: Base class for all package exceptions.
  - `ConfigurationError`: Construction validation error.
    - `ConfigurationValueError`: Invalid configuration field value.
  - `RequestError`: Base request-time failure.
    - `RetryExhaustedError`: All retries consumed.
    - `CircuitOpenError`: Circuit is OPEN; request short-circuited.
    - `SelfHealingTimeoutError`: Timeout exceeded.
      - `ConnectTimeoutError`: Connection establishing timeout.
      - `ReadTimeoutError`: Read response timeout.
    - `RateLimitError`: 429 response exceeding wait threshold.
    - `FallbackError`: Custom fallback handler error.
    - `AllEndpointsUnavailableError`: All endpoints marked UNHEALTHY.
  - `IdempotencyError`: Non-idempotent retry missing key.
  - `CompatibilityError`: Schema adaptation failure.
    - `SchemaMismatchError`: Schema keys differ.
    - `MappingValidationError`: Rule validation failed.
    - `ApprovalRequiredError`: AI suggestion pending human approval.
