# Self-Healing API Resilience Package

A reusable Python developer package for reliable API communication and controlled automated failure recovery.

---

## Overview

Modern applications frequently depend on internal and external APIs. Temporary network failures, service unavailability, timeouts, server errors and rate limits can cause application requests to fail and may produce cascading effects when dependencies are tightly coupled.

The **Self-Healing API Resilience Package** places standardized resilience behavior between your application code and API endpoints — so you write the policy once and reuse it everywhere.

---

## Features

| Feature | Description |
|---|---|
| **Configurable Timeouts** | Connect, read, and total operation timeouts |
| **Retry with Backoff** | Exponential backoff with optional jitter (full, equal, decorrelated) |
| **Circuit Breaker** | CLOSED / OPEN / HALF_OPEN state machine per endpoint |
| **Error Classification** | Retryable vs. non-retryable error categories |
| **Health Monitoring** | Passive health tracking per endpoint |
| **Health-Aware Routing** | Automatic failover to healthy endpoints |
| **Fallback Handling** | Developer-configured fallback hooks |
| **Rate-Limit Awareness** | HTTP 429 + `Retry-After` header handling |
| **Idempotency Safeguards** | Prevents duplicate operations on retry |
| **Structured Observability** | Logs, metrics, traces, and event hooks |
| **API Compatibility Layer** | Schema change detection and versioned mapping rules |
| **AI-Assisted Compatibility** | Optional AI suggestions with mandatory approval gate |

---

## Installation

```bash
# Core package (one required dependency: httpx)
pip install self-healing-api

# With OpenTelemetry support
pip install "self-healing-api[opentelemetry]"

# With Prometheus metrics
pip install "self-healing-api[prometheus]"

# With AI compatibility assistant
pip install "self-healing-api[ai]"

# Everything
pip install "self-healing-api[full]"
```

---

## Quick Start

```python
from self_healing_api import SelfHealingClient
from self_healing_api.config import TimeoutConfig, RetryConfig, CircuitBreakerConfig

client = SelfHealingClient(
    base_url="https://api.example.com",
    timeout=TimeoutConfig(connect=5.0, read=10.0, total=30.0),
    retry=RetryConfig(max_attempts=3, backoff="exponential", jitter=True),
    circuit_breaker=CircuitBreakerConfig(
        enabled=True,
        failure_threshold=5,
        recovery_timeout=30,
    ),
)

response = client.get("/data")
print(response.json())
```

---

## Design Principles

1. **Resilience reduces boilerplate — it does not replace application logic.** The package handles communication failures; your application remains responsible for business correctness.

2. **Retries for non-idempotent operations require idempotency keys.** A timeout does not prove the server did not complete the operation.

3. **AI suggestions are never auto-applied.** The compatibility assistant can propose schema mappings but every mapping must pass validation and explicit approval before taking effect.

4. **Fail predictably.** When recovery is not possible, the package raises a structured, documented exception — never silently swallowing errors.

5. **Zero surprise dependencies.** Only one required dependency (`httpx`). All integrations are optional extras.

---

## Architecture

```
Developer Application
        │
        ▼
SelfHealingClient
        │
        ├── Config Validator
        ├── Idempotency Guard
        ├── Circuit Breaker
        ├── Timeout Policy
        ├── Retry Engine (backoff + jitter)
        ├── Error Classifier
        ├── Rate Limit Handler
        ├── Health Monitor
        ├── Health-Aware Router
        ├── Fallback Handler
        └── Observability Hooks
        │
        ▼
Internal / External API
```

---

## Safety Guarantees

- No infinite retries — `max_attempts` is always enforced
- No retry storms — exponential backoff with jitter and circuit breaker
- No duplicate operations — idempotency guard enforced before every retry
- No secret leakage — credentials masked before any log/event emission
- No uncontrolled AI changes — approval gate is non-bypassable
- No global state — every client instance owns its own circuit breaker and health state

---

## Project Structure

```
self-healing-api/
├── src/self_healing_api/     # Package source
│   ├── client/               # Public SelfHealingClient
│   ├── config/               # Configuration models and validation
│   ├── transport/            # HTTP transport abstraction
│   ├── retry/                # Retry engine, backoff, jitter
│   ├── circuit_breaker/      # Circuit breaker state machine
│   ├── timeout/              # Timeout policies
│   ├── errors/               # Exception hierarchy + error classifier
│   ├── health/               # Health monitoring
│   ├── routing/              # Health-aware routing
│   ├── fallback/             # Fallback handler
│   ├── rate_limit/           # Rate-limit handling
│   ├── idempotency/          # Idempotency guard
│   ├── observability/        # Logs, metrics, traces, events
│   ├── compatibility/        # Schema compatibility layer
│   └── utils/                # Shared utilities
├── tests/                    # Full test suite
├── examples/                 # Usage examples
├── docs/                     # Documentation
└── benchmarks/               # Performance benchmarks
```

---

## Development Setup

```bash
# Clone the repository
git clone https://github.com/self-healing-api/self-healing-api.git
cd self-healing-api

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Linux/macOS

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check src/ tests/

# Run type checker
mypy src/
```

---

## Testing

```bash
pytest tests/unit/          # Unit tests
pytest tests/integration/   # Integration tests (mock HTTP)
pytest tests/security/      # Security tests
pytest tests/concurrency/   # Concurrency tests
pytest tests/chaos/         # Chaos/failure injection tests
pytest tests/performance/   # Performance benchmarks
pytest                      # All tests
```

---

## Scope

**The package handles:**
- Retry and backoff
- Timeouts
- Circuit breaking
- Health-aware routing
- Fallback hooks
- Error classification
- Observability hooks

**Outside the package scope:**
- Business-logic bug correction
- Database corruption repair
- Guaranteeing external provider availability
- Automatically approving unsafe AI changes
- Eliminating all application-level error handling

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.
