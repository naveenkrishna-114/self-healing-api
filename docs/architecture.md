# Self-Healing API Resilience Package — Architecture

## Overview

The **Self-Healing API Resilience Package** sits transparently between application code and upstream API endpoints. It standardizes communication resilience policies across applications using reusable, immutable configuration objects.

```
Developer Application
        │
        ▼
SelfHealingClient / AsyncSelfHealingClient
        │
        ├── Config Validator (Eager construction validation)
        ├── Health-Aware Router (Priority, Round Robin, Random failover)
        ├── Idempotency Guard (UUID key generation & retry safeguards)
        ├── Circuit Breaker (CLOSED → OPEN → HALF_OPEN state machine per endpoint)
        ├── Timeout Policy (Connect, Read, & Total budget tracking)
        ├── Retry Engine (Exponential/Linear/Fixed backoff + Full/Equal/Decorrelated Jitter)
        ├── Error Classifier (Typed exception mapping)
        ├── Rate Limit Handler (429 Retry-After parsing)
        ├── Health Tracker (Passive & active endpoint observation)
        ├── Observability Manager (Credential masking, OpenTelemetry, Prometheus)
        ├── Compatibility Engine & AI Assistant (Schema drift & mandatory approval gate)
        └── Fallback Handler (Stale cache, static response, custom callback)
        │
        ▼
Upstream HTTP API
```

## Resilience Execution Pipeline

1. **Routing**: `HealthAwareRouter` selects an active endpoint based on configured strategy. Unhealthy endpoints are filtered out if failover is enabled.
2. **Idempotency Guard**: Validates that retries of non-idempotent HTTP methods (`POST`, `PATCH`) include an idempotency key header or auto-generates a UUID v4 key if enabled.
3. **Circuit Breaker**: Checks if the target endpoint's breaker is `OPEN`. If `OPEN`, short-circuits to the fallback handler.
4. **Timeout Policy**: Computes connect and remaining read timeouts. Enforces total operation deadline.
5. **Transport Execution**: Sends request via `AbstractTransport` (`HttpxTransport` or `FakeTransport`).
6. **Retry Engine & Error Classifier**: On HTTP 5xx or network error, evaluates retryability and calculates backoff delay with jitter.
7. **Rate Limit Handler**: On HTTP 429, parses `Retry-After` header and enforces maximum wait ceiling.
8. **Health Monitoring**: Updates endpoint health counters and state (`HEALTHY`, `UNHEALTHY`, `DEGRADED`, `RECOVERING`).
9. **Observability Manager**: Emits logs with credential redaction (`SecretMasker`), Prometheus metrics, and OpenTelemetry trace spans.
10. **Fallback Handler**: If all retries/recovery attempts fail, executes configured fallback strategy (custom handler, last-known-good cached response, or static payload).
