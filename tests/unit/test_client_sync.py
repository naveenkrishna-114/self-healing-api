"""Unit tests for SelfHealingClient (sync)."""

import pytest

from self_healing_api.client import SelfHealingClient
from self_healing_api.config import FallbackConfig, RetryConfig
from self_healing_api.transport.fake_transport import FakeTransport, make_response
from self_healing_api.utils.clock import FakeClock


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock(start=0.0)


@pytest.mark.unit
class TestSelfHealingClientSync:
    def test_successful_get_request(self, clock: FakeClock) -> None:
        transport = FakeTransport(responses=[make_response(200, json_body={"data": "hello"})])
        client = SelfHealingClient(
            base_url="https://api.example.com",
            transport=transport,
            clock=clock,
        )

        res = client.get("/data")
        assert res.status_code == 200
        assert res.json() == {"data": "hello"}
        assert len(transport.requests) == 1

    def test_retry_on_server_error_and_succeed(self, clock: FakeClock) -> None:
        transport = FakeTransport(
            responses=[
                make_response(503),
                make_response(200, json_body={"ok": True}),
            ]
        )
        client = SelfHealingClient(
            base_url="https://api.example.com",
            retry=RetryConfig(max_attempts=3, base_delay=0.1),
            transport=transport,
            clock=clock,
        )

        res = client.get("/data")
        assert res.status_code == 200
        assert res.json() == {"ok": True}
        assert len(transport.requests) == 2

    def test_fallback_executed_on_exhausted_retries(self, clock: FakeClock) -> None:
        transport = FakeTransport(
            responses=[
                make_response(500),
                make_response(500),
                make_response(500),
            ]
        )
        client = SelfHealingClient(
            base_url="https://api.example.com",
            retry=RetryConfig(max_attempts=3, base_delay=0.1),
            fallback=FallbackConfig(static_response={"fallback": True}),
            transport=transport,
            clock=clock,
        )

        res = client.get("/data")
        assert res.status_code == 200
        assert res.json() == {"fallback": True}
        assert len(transport.requests) == 3

    def test_sync_all_http_methods_and_context_manager(self, clock: FakeClock) -> None:
        transport = FakeTransport(
            default_response=make_response(200, json_body={"success": True})
        )
        with SelfHealingClient(
            base_url="https://api.example.com",
            transport=transport,
            clock=clock,
        ) as client:
            assert client.post("/items", json={"a": 1}).status_code == 200
            assert client.put("/items/1", json={"a": 2}).status_code == 200
            assert client.delete("/items/1").status_code == 200
            assert client.patch("/items/1", json={"a": 3}).status_code == 200
            assert client.head("/items/1").status_code == 200
            assert client.options("/items/1").status_code == 200

    def test_sync_failover_and_circuit_open_fallback(self, clock: FakeClock) -> None:
        from self_healing_api.config import CircuitBreakerConfig, HealthConfig, RoutingConfig

        transport = FakeTransport(
            responses=[
                make_response(503),
                make_response(503),
                make_response(200, json_body={"endpoint": "secondary"}),
            ]
        )
        client = SelfHealingClient(
            base_url="https://pri.com",
            endpoints=["https://sec.com"],
            retry=RetryConfig(max_attempts=2, base_delay=0.01),
            health=HealthConfig(enabled=True, unhealthy_threshold=2),
            routing=RoutingConfig(strategy="priority", failover_enabled=True),
            circuit_breaker=CircuitBreakerConfig(failure_threshold=2, recovery_timeout=10.0),
            transport=transport,
            clock=clock,
        )
        res = client.get("/data")
        assert res.status_code == 200
        assert res.json() == {"endpoint": "secondary"}
        client.close()

    def test_sync_exhausted_failover_to_fallback(self, clock: FakeClock) -> None:
        from self_healing_api.config import RoutingConfig

        transport = FakeTransport(
            responses=[
                make_response(500),
                make_response(500),
                make_response(500),
                make_response(500),
            ]
        )
        client = SelfHealingClient(
            base_url="https://pri.com",
            endpoints=["https://sec.com"],
            retry=RetryConfig(max_attempts=2, base_delay=0.01),
            routing=RoutingConfig(strategy="priority", failover_enabled=True),
            fallback=FallbackConfig(static_response={"exhausted_fallback": True}),
            transport=transport,
            clock=clock,
        )
        res = client.get("/data")
        assert res.status_code == 200
        assert res.degraded is True
        assert res.json() == {"exhausted_fallback": True}
        client.close()

    def test_sync_client_helpers_and_branch_coverage(self, clock: FakeClock) -> None:
        from self_healing_api.circuit_breaker.state import CircuitState
        from self_healing_api.config.models import ClientConfig, RoutingConfig

        transport = FakeTransport(default_response=make_response(200))
        cfg = ClientConfig(
            base_url="https://pri.com",
            endpoints=("https://sec.com", "https://tert.com"),
            routing=RoutingConfig(failover_enabled=True),
        )
        client = SelfHealingClient(config=cfg, transport=transport, clock=clock)

        # _build_url with absolute url
        abs_url = client._build_url("https://pri.com", "https://other.com/api")
        assert abs_url == "https://other.com/api"

        # _sleep with 0
        client._sleep(0.0)

        # _get_breaker on unseen endpoint
        breaker = client._get_breaker("https://unseen.com")
        assert breaker is not None

        # _failover_target when failover is disabled
        cfg_no_fo = ClientConfig(
            base_url="https://pri.com",
            routing=RoutingConfig(failover_enabled=False),
        )
        client_no_fo = SelfHealingClient(config=cfg_no_fo, transport=transport, clock=clock)
        assert client_no_fo._failover_target(set()) is None
        client_no_fo.close()

        # Unhealthy endpoint branch
        client._health_tracker.record_failure("https://sec.com")
        client._health_tracker.record_failure("https://sec.com")
        client._health_tracker.record_failure("https://sec.com")
        assert not client._health_tracker.is_healthy("https://sec.com")

        # Open circuit endpoint branch
        tert_breaker = client._get_breaker("https://tert.com")
        for _ in range(5):
            tert_breaker.record_failure()
        assert tert_breaker.state == CircuitState.OPEN

        # Pass headers to request
        res = client.get("/test", headers={"X-Header": "value"}, params={"q": "1"})
        assert res.status_code == 200
        client.close()

    def test_sync_circuit_open_failover_and_rate_limit_retry(self, clock: FakeClock) -> None:
        from self_healing_api.config import CircuitBreakerConfig, RateLimitConfig, RoutingConfig

        # Primary circuit open triggers failover to secondary
        transport = FakeTransport(
            responses=[
                make_response(200, json_body={"from": "sec"}),
            ]
        )
        client = SelfHealingClient(
            base_url="https://pri.com",
            endpoints=["https://sec.com"],
            routing=RoutingConfig(failover_enabled=True),
            circuit_breaker=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=100.0),
            transport=transport,
            clock=clock,
        )
        # Open primary circuit
        client._get_breaker("https://pri.com").record_failure()
        res = client.get("/data")
        assert res.json() == {"from": "sec"}
        client.close()

        # Rate limit 429 with retry-after triggers sleep & retry
        rl_transport = FakeTransport(
            responses=[
                make_response(429, headers={"retry-after": "1"}),
                make_response(200, json_body={"after_rl": True}),
            ]
        )
        rl_client = SelfHealingClient(
            base_url="https://pri.com",
            rate_limit=RateLimitConfig(respect_retry_after=True),
            transport=rl_transport,
            clock=clock,
        )
        res_rl = rl_client.get("/limited")
        assert res_rl.json() == {"after_rl": True}
        rl_client.close()

    def test_sync_repeated_429_loop_exhaustion(self, clock: FakeClock) -> None:
        from self_healing_api.config import (
            FallbackConfig,
            RateLimitConfig,
            RetryConfig,
            RoutingConfig,
        )

        # Repeated 429 causes inner while attempt <= max_attempts to exit without exception
        # hitting lines 351-372
        transport = FakeTransport(
            responses=[
                make_response(429, headers={"retry-after": "1"}),
                make_response(429, headers={"retry-after": "1"}),
                make_response(429, headers={"retry-after": "1"}),
                make_response(200, json_body={"from": "sec_after_429"}),
            ]
        )
        client = SelfHealingClient(
            base_url="https://pri.com",
            endpoints=["https://sec.com"],
            retry=RetryConfig(max_attempts=2),
            routing=RoutingConfig(failover_enabled=True),
            rate_limit=RateLimitConfig(respect_retry_after=True),
            fallback=FallbackConfig(static_response={"exhausted_429": True}),
            transport=transport,
            clock=clock,
        )
        res = client.get("/infinite-rl")
        assert res.json() == {"from": "sec_after_429"}
        client.close()

    def test_sync_system_clock_sleep_and_failover_filters(self) -> None:
        from self_healing_api.circuit_breaker.state import CircuitState
        from self_healing_api.config.models import ClientConfig, RoutingConfig
        from self_healing_api.utils.clock import SystemClock

        transport = FakeTransport(default_response=make_response(200))
        cfg = ClientConfig(
            base_url="https://pri.com",
            endpoints=("https://sec.com", "https://tert.com"),
            routing=RoutingConfig(failover_enabled=True),
        )
        client = SelfHealingClient(config=cfg, transport=transport, clock=SystemClock())
        client._sleep(0.0001)

        # Make sec unhealthy and tert open
        client._health_tracker.record_failure("https://sec.com")
        client._health_tracker.record_failure("https://sec.com")
        client._health_tracker.record_failure("https://sec.com")

        tert_breaker = client._get_breaker("https://tert.com")
        for _ in range(5):
            tert_breaker.record_failure()
        assert tert_breaker.state == CircuitState.OPEN

        # Tried pri, sec is unhealthy (hits 168), tert is open (hits 170) -> returns None
        assert client._failover_target({"https://pri.com"}) is None
        client.close()

    def test_sync_circuit_open_fallback_when_no_failover(self, clock: FakeClock) -> None:
        from self_healing_api.config import CircuitBreakerConfig, FallbackConfig

        transport = FakeTransport(default_response=make_response(200))
        client = SelfHealingClient(
            base_url="https://pri.com",
            circuit_breaker=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=100.0),
            fallback=FallbackConfig(static_response={"cb_fallback": True}),
            transport=transport,
            clock=clock,
        )
        client._get_breaker("https://pri.com").record_failure()
        res = client.get("/cb-fallback")
        assert res.json() == {"cb_fallback": True}
        assert res.degraded is True
        client.close()

    def test_sync_429_without_retry_after_and_connection_error_retry(
        self, clock: FakeClock
    ) -> None:
        from self_healing_api.config import FallbackConfig, RateLimitConfig, RetryConfig

        # 429 without Retry-After header -> rate_limit_delay is None -> hits 262->270
        # then fails 429 on retry, falls back to static response
        transport_429 = FakeTransport(
            responses=[
                make_response(429),
                make_response(429),
            ]
        )
        client_429 = SelfHealingClient(
            base_url="https://pri.com",
            retry=RetryConfig(max_attempts=1),
            rate_limit=RateLimitConfig(respect_retry_after=True),
            fallback=FallbackConfig(static_response={"no_header_fallback": True}),
            transport=transport_429,
            clock=clock,
        )
        res_429 = client_429.get("/no-header-429")
        assert res_429.json() == {"no_header_fallback": True}
        client_429.close()

        # Connection error retry: raises ConnectionError, retries, succeeds on attempt 2
        # Hits lines 307-308 and 345-349
        transport_conn = FakeTransport(
            responses=[
                ConnectionError("network reset"),
                make_response(200, json_body={"network_recovered": True}),
            ]
        )
        client_conn = SelfHealingClient(
            base_url="https://pri.com",
            retry=RetryConfig(max_attempts=3, base_delay=0.01),
            transport=transport_conn,
            clock=clock,
        )
        res_conn = client_conn.get("/conn-retry")
        assert res_conn.json() == {"network_recovered": True}
        client_conn.close()

    def test_sync_single_endpoint_429_exhaustion_and_raise_for_status_return(
        self, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from self_healing_api.config import FallbackConfig, RateLimitConfig, RetryConfig

        # Single endpoint repeated 429 exhaustion hits line 361
        transport_single = FakeTransport(
            responses=[
                make_response(429, headers={"retry-after": "1"}),
                make_response(429, headers={"retry-after": "1"}),
            ]
        )
        client_single = SelfHealingClient(
            base_url="https://pri.com",
            retry=RetryConfig(max_attempts=1),
            rate_limit=RateLimitConfig(respect_retry_after=True),
            fallback=FallbackConfig(static_response={"single_429_fallback": True}),
            transport=transport_single,
            clock=clock,
        )
        res_single = client_single.get("/single-429")
        assert res_single.json() == {"single_429_fallback": True}
        client_single.close()

        # Line 291: raise_for_status() does not raise on 404 client error
        from self_healing_api.transport.base import TransportResponse
        monkeypatch.setattr(TransportResponse, "raise_for_status", lambda self: None)
        transport_noop = FakeTransport(responses=[make_response(404)])
        client_noop = SelfHealingClient(
            base_url="https://pri.com",
            retry=RetryConfig(max_attempts=1),
            transport=transport_noop,
            clock=clock,
        )
        res_noop = client_noop.get("/noop-404")
        assert res_noop.status_code == 404
        client_noop.close()

