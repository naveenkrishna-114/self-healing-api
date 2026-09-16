# Changelog

All notable changes to the Self-Healing API Resilience Package are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] - 2026-09-05

### Added
- Initial package scaffold and configuration system
- Exception hierarchy
- HTTP transport abstraction (httpx)
- Timeout policy
- Error classification
- Retry engine with exponential backoff and jitter
- Circuit breaker (CLOSED / OPEN / HALF_OPEN)
- Health monitoring (passive)
- Health-aware routing and failover
- Fallback handler
- Rate-limit handling (HTTP 429 + Retry-After)
- Observability hooks (logs, metrics, traces, events)
- Idempotency guard
- SelfHealingClient (sync)
- AsyncSelfHealingClient
- API compatibility layer with mapping validator and approval gate

### Planned for 1.x
- Broader schema-change detection tooling
- Rule versioning and rollback

### Planned for 2.x
- Optional AI-assisted compatibility analysis
- Confidence scoring
- Audit logging for AI suggestions

### Planned for 3.x
- Predictive failure detection
- Adaptive retry policies
- Multi-region failover integrations

---

## Version History

| Version | Date | Summary |
|---------|------|---------|
| 0.1.0 | 2026-09-05 | Initial release |
