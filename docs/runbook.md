# Operational Runbook: Self-Healing API Resilience

## 1. Overview & Architecture

The **Self-Healing API Resilience Client** protects distributed microservice communication from transient network disruptions, cascading upstream failures, rate limits, and schema changes.

```
Application Service
       │
       ▼
SelfHealingClient
  ├── Idempotency Guard  (Enforces UUID keys on POST/PATCH retry)
  ├── Health-Aware Router (Filters out UNHEALTHY endpoints)
  ├── Circuit Breaker    (CLOSED -> OPEN -> HALF_OPEN per target)
  ├── Rate Limit Handler (Honors 429 Retry-After header)
  ├── Observability      (Redacts credentials, emits OTel spans & Prometheus metrics)
  └── Fallback Handler   (Serves degraded static/stale responses when recovery fails)
       │
       ▼
Target Endpoints / Microservices
```

---

## 2. Telemetry & Alerting Thresholds

### Metrics Emitted
- `self_healing_api_requests_total{method, endpoint, status_code}`: Total count of requests sent.
- `self_healing_api_request_duration_seconds{method, endpoint}`: Latency histogram per endpoint.

### Primary Alerts & Thresholds
| Alert | Condition | Severity | Immediate Action |
| :--- | :--- | :--- | :--- |
| **CircuitBreakerOpen** | Breaker state == OPEN for > 2 min | P1 / Warning | Check downstream health; verify network connectivity; verify endpoint error rate. |
| **HighFallbackRate** | Fallback requests (`response.degraded == True`) > 5% for 5 min | P2 / Major | Inspect error logs; review database and upstream dependency health. |
| **IdempotencyRejection** | `IdempotencyError` > 10 / min | P3 / Minor | Upstream client retrying mutating `POST`/`PATCH` without `Idempotency-Key`. Fix calling code. |
| **RateLimitSpike** | HTTP 429 response rate > 10% | P2 / Major | Inspect downstream rate limit quota; increase client pool or adjust backoff. |

---

## 3. Incident Triage Procedures

### Scenario A: Target Service Circuit Tripped (Breaker OPEN)
1. **Symptoms**: Requests return fallback responses immediately (`response.degraded == True`) without network egress; logs show `Circuit breaker opened for endpoint: <URL>`.
2. **Diagnosis**:
   - Check target endpoint status endpoint (e.g. `/health`).
   - Query metrics for 5xx error spikes on the target service.
3. **Remediation**:
   - If secondary failover endpoint exists: Verify router successfully shifted traffic (`HealthAwareRouter`).
   - Allow cooldown period: The circuit breaker will automatically enter `HALF_OPEN` after `recovery_timeout` (default 30s) and send a single probe request.
   - If downstream is recovered, probe succeeds and breaker automatically resets to `CLOSED`.

### Scenario B: Degraded Responses Served to Users
1. **Symptoms**: Response payload has `response.degraded == True`, or contains `x-self-healing-fallback: true` or `x-self-healing-stale: true`.
2. **Diagnosis**:
   - Identify whether degraded response is from `cache_last_success` (stale data) or `static_response`.
   - Inspect `ctx.error` attached to fallback context in logs.
3. **Remediation**:
   - Verify if upstream outage is transient or requires roll-back of a recent service deployment.

### Scenario C: HTTP 429 Rate Limiting
1. **Symptoms**: Requests delayed by `Retry-After` seconds or failing with `RateLimitError`.
2. **Diagnosis**:
   - Check if downstream API rate limit header `Retry-After` exceeds `max_retry_after_wait` (default 120s).
3. **Remediation**:
   - Request rate limit quota increase from upstream service owner.
   - Tune client request concurrency.

---

## 4. Rollout & Rollback Strategy

1. **Canary Verification**:
   - Deploy new service version with 10% traffic routing.
   - Monitor `self_healing_api_requests_total` status codes and latency.
   - If error rate exceeds 1% or circuit breakers trip during canary, **immediately roll back**.
   - If healthy after 10 minutes, scale traffic: 50% -> 100%.
2. **Configuration Changes**:
   - Never disable `verify_ssl` in production.
   - Keep `auto_generate=True` for `IdempotencyConfig` unless downstream explicitly mandates caller-provided keys.

