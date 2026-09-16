"""Unit tests for AsyncSelfHealingClient (async)."""

import pytest

from self_healing_api.client import AsyncSelfHealingClient
from self_healing_api.config import RetryConfig
from self_healing_api.transport.fake_transport import FakeAsyncTransport, make_response
from self_healing_api.utils.clock import FakeClock


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock(start=0.0)


@pytest.mark.asyncio
class TestAsyncSelfHealingClient:
    async def test_async_get_request(self, clock: FakeClock) -> None:
        transport = FakeAsyncTransport(responses=[make_response(200, json_body={"async": True})])
        async with AsyncSelfHealingClient(
            base_url="https://api.example.com",
            transport=transport,
            clock=clock,
        ) as client:
            res = await client.get("/data")
            assert res.status_code == 200
            assert res.json() == {"async": True}
            assert len(transport.requests) == 1

    async def test_async_retry_and_succeed(self, clock: FakeClock) -> None:
        transport = FakeAsyncTransport(
            responses=[
                make_response(502),
                make_response(200, json_body={"ok": True}),
            ]
        )
        client = AsyncSelfHealingClient(
            base_url="https://api.example.com",
            retry=RetryConfig(max_attempts=3, base_delay=0.01),
            transport=transport,
            clock=clock,
        )
        res = await client.get("/data")
        assert res.status_code == 200
        assert res.json() == {"ok": True}
        assert len(transport.requests) == 2

    async def test_async_all_http_methods(self, clock: FakeClock) -> None:
        transport = FakeAsyncTransport(
            default_response=make_response(200, json_body={"success": True})
        )
        client = AsyncSelfHealingClient(
            base_url="https://api.example.com",
            transport=transport,
            clock=clock,
        )
        r_post = await client.post("/items", json={"name": "test"})
        r_put = await client.put("/items/1", json={"name": "test2"})
        r_delete = await client.delete("/items/1")
        r_patch = await client.patch("/items/1", json={"name": "test3"})

        assert r_post.status_code == 200
        assert r_put.status_code == 200
        assert r_delete.status_code == 200
        assert r_patch.status_code == 200
        await client.aclose()

    async def test_async_failover_and_circuit_breaking(self, clock: FakeClock) -> None:
        from self_healing_api.config import CircuitBreakerConfig, HealthConfig, RoutingConfig

        transport = FakeAsyncTransport(
            responses=[
                make_response(503),
                make_response(503),
                make_response(200, json_body={"endpoint": "secondary"}),
            ]
        )
        client = AsyncSelfHealingClient(
            base_url="https://pri.com",
            endpoints=["https://sec.com"],
            retry=RetryConfig(max_attempts=2, base_delay=0.01),
            health=HealthConfig(enabled=True, unhealthy_threshold=2),
            routing=RoutingConfig(strategy="priority", failover_enabled=True),
            circuit_breaker=CircuitBreakerConfig(failure_threshold=2, recovery_timeout=10.0),
            transport=transport,
            clock=clock,
        )
        res = await client.get("/data")
        assert res.status_code == 200
        assert res.json() == {"endpoint": "secondary"}
        await client.aclose()

    async def test_async_fallback_and_rate_limit(self, clock: FakeClock) -> None:
        from self_healing_api.config import FallbackConfig, RateLimitConfig

        transport = FakeAsyncTransport(
            responses=[
                make_response(429, headers={"retry-after": "0.1"}),
                make_response(500),
                make_response(500),
            ]
        )
        client = AsyncSelfHealingClient(
            base_url="https://api.example.com",
            retry=RetryConfig(max_attempts=2, base_delay=0.01),
            rate_limit=RateLimitConfig(respect_retry_after=True, max_retry_after_wait=5.0),
            fallback=FallbackConfig(static_response={"degraded_mode": True}),
            transport=transport,
            clock=clock,
        )
        res = await client.get("/data")
        assert res.status_code == 200
        assert res.degraded is True
        assert res.json() == {"degraded_mode": True}
        await client.aclose()

    async def test_async_exhausted_failover_to_fallback(self, clock: FakeClock) -> None:
        from self_healing_api.config import FallbackConfig, RoutingConfig

        transport = FakeAsyncTransport(
            responses=[
                make_response(500),
                make_response(500),
                make_response(500),
                make_response(500),
            ]
        )
        client = AsyncSelfHealingClient(
            base_url="https://pri.com",
            endpoints=["https://sec.com"],
            retry=RetryConfig(max_attempts=2, base_delay=0.01),
            routing=RoutingConfig(strategy="priority", failover_enabled=True),
            fallback=FallbackConfig(static_response={"async_exhausted": True}),
            transport=transport,
            clock=clock,
        )
        res = await client.get("/data")
        assert res.status_code == 200
        assert res.degraded is True
        assert res.json() == {"async_exhausted": True}
        await client.aclose()

    async def test_async_client_helpers_and_branch_coverage(self, clock: FakeClock) -> None:
        from self_healing_api.circuit_breaker.state import CircuitState
        from self_healing_api.config.models import ClientConfig, RoutingConfig
        from self_healing_api.utils.clock import SystemClock

        transport = FakeAsyncTransport(default_response=make_response(200))
        cfg = ClientConfig(
            base_url="https://pri.com",
            endpoints=("https://sec.com", "https://tert.com"),
            routing=RoutingConfig(failover_enabled=True),
        )
        client = AsyncSelfHealingClient(config=cfg, transport=transport, clock=clock)

        # _build_url with absolute url
        abs_url = client._build_url("https://pri.com", "https://other.com/api")
        assert abs_url == "https://other.com/api"

        # _sleep with 0
        await client._sleep(0.0)

        # _sleep with SystemClock
        sys_client = AsyncSelfHealingClient(config=cfg, transport=transport, clock=SystemClock())
        await sys_client._sleep(0.0001)
        await sys_client.aclose()

        # _get_breaker on unseen endpoint
        breaker = client._get_breaker("https://unseen.com")
        assert breaker is not None

        # _failover_target when failover is disabled
        cfg_no_fo = ClientConfig(
            base_url="https://pri.com",
            routing=RoutingConfig(failover_enabled=False),
        )
        client_no_fo = AsyncSelfHealingClient(config=cfg_no_fo, transport=transport, clock=clock)
        assert client_no_fo._failover_target(set()) is None
        await client_no_fo.aclose()

        # Unhealthy endpoint branch (line 145)
        client._health_tracker.record_failure("https://sec.com")
        client._health_tracker.record_failure("https://sec.com")
        client._health_tracker.record_failure("https://sec.com")
        assert not client._health_tracker.is_healthy("https://sec.com")

        # Open circuit endpoint branch (line 147)
        tert_breaker = client._get_breaker("https://tert.com")
        for _ in range(5):
            tert_breaker.record_failure()
        assert tert_breaker.state == CircuitState.OPEN

        # Tried pri, sec is unhealthy, tert is open -> returns None
        assert client._failover_target({"https://pri.com"}) is None

        # Pass headers to request
        res = await client.get("/test", headers={"X-Header": "value"}, params={"q": "1"})
        assert res.status_code == 200
        await client.aclose()

    async def test_async_circuit_open_failover_and_fallback(self, clock: FakeClock) -> None:
        from self_healing_api.config import CircuitBreakerConfig, FallbackConfig, RoutingConfig

        # Primary circuit open triggers failover to secondary
        transport = FakeAsyncTransport(
            responses=[
                make_response(200, json_body={"from": "sec"}),
            ]
        )
        client = AsyncSelfHealingClient(
            base_url="https://pri.com",
            endpoints=["https://sec.com"],
            routing=RoutingConfig(failover_enabled=True),
            circuit_breaker=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=100.0),
            transport=transport,
            clock=clock,
        )
        client._get_breaker("https://pri.com").record_failure()
        res = await client.get("/data")
        assert res.json() == {"from": "sec"}
        await client.aclose()

        # Circuit open on primary with NO failover target -> returns fallback
        single_transport = FakeAsyncTransport(default_response=make_response(200))
        single_client = AsyncSelfHealingClient(
            base_url="https://pri.com",
            circuit_breaker=CircuitBreakerConfig(failure_threshold=1, recovery_timeout=100.0),
            fallback=FallbackConfig(static_response={"async_cb_fallback": True}),
            transport=single_transport,
            clock=clock,
        )
        single_client._get_breaker("https://pri.com").record_failure()
        res_cb = await single_client.get("/cb-fallback")
        assert res_cb.json() == {"async_cb_fallback": True}
        assert res_cb.degraded is True
        await single_client.aclose()

    async def test_async_429_variations_and_connection_error_retry(
        self, clock: FakeClock
    ) -> None:
        from self_healing_api.config import FallbackConfig, RateLimitConfig, RetryConfig

        # 429 without Retry-After header -> rate_limit_delay is None -> hits 233->241
        transport_429 = FakeAsyncTransport(
            responses=[
                make_response(429),
                make_response(429),
            ]
        )
        client_429 = AsyncSelfHealingClient(
            base_url="https://pri.com",
            retry=RetryConfig(max_attempts=1),
            rate_limit=RateLimitConfig(respect_retry_after=True),
            fallback=FallbackConfig(static_response={"async_no_header": True}),
            transport=transport_429,
            clock=clock,
        )
        res_429 = await client_429.get("/no-header-429")
        assert res_429.json() == {"async_no_header": True}
        await client_429.aclose()

        # Connection error retry: raises ConnectionError, retries, succeeds on attempt 2
        # Hits lines 278-279 and 312-316
        transport_conn = FakeAsyncTransport(
            responses=[
                ConnectionError("async network reset"),
                make_response(200, json_body={"async_network_recovered": True}),
            ]
        )
        client_conn = AsyncSelfHealingClient(
            base_url="https://pri.com",
            retry=RetryConfig(max_attempts=3, base_delay=0.01),
            transport=transport_conn,
            clock=clock,
        )
        res_conn = await client_conn.get("/conn-retry")
        assert res_conn.json() == {"async_network_recovered": True}
        await client_conn.aclose()

    async def test_async_repeated_429_exhaustion_and_raise_for_status(
        self, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from self_healing_api.config import (
            FallbackConfig,
            RateLimitConfig,
            RetryConfig,
            RoutingConfig,
        )
        from self_healing_api.transport.base import TransportResponse

        # Repeated 429 with failover to secondary (hits 318-335)
        transport_fo = FakeAsyncTransport(
            responses=[
                make_response(429, headers={"retry-after": "1"}),
                make_response(429, headers={"retry-after": "1"}),
                make_response(429, headers={"retry-after": "1"}),
                make_response(200, json_body={"from": "async_sec_after_429"}),
            ]
        )
        client_fo = AsyncSelfHealingClient(
            base_url="https://pri.com",
            endpoints=["https://sec.com"],
            retry=RetryConfig(max_attempts=2),
            routing=RoutingConfig(failover_enabled=True),
            rate_limit=RateLimitConfig(respect_retry_after=True),
            fallback=FallbackConfig(static_response={"exhausted_429": True}),
            transport=transport_fo,
            clock=clock,
        )
        res_fo = await client_fo.get("/infinite-rl")
        assert res_fo.json() == {"from": "async_sec_after_429"}
        await client_fo.aclose()

        # Repeated 429 on single endpoint (hits 328-330 fallback)
        transport_single = FakeAsyncTransport(
            responses=[
                make_response(429, headers={"retry-after": "1"}),
                make_response(429, headers={"retry-after": "1"}),
            ]
        )
        client_single = AsyncSelfHealingClient(
            base_url="https://pri.com",
            retry=RetryConfig(max_attempts=1),
            rate_limit=RateLimitConfig(respect_retry_after=True),
            fallback=FallbackConfig(static_response={"async_single_429": True}),
            transport=transport_single,
            clock=clock,
        )
        res_single = await client_single.get("/single-429")
        assert res_single.json() == {"async_single_429": True}
        await client_single.aclose()

        # Line 262: raise_for_status() does not raise on 404 client error
        monkeypatch.setattr(TransportResponse, "raise_for_status", lambda self: None)
        transport_noop = FakeAsyncTransport(responses=[make_response(404)])
        client_noop = AsyncSelfHealingClient(
            base_url="https://pri.com",
            retry=RetryConfig(max_attempts=1),
            transport=transport_noop,
            clock=clock,
        )
        res_noop = await client_noop.get("/noop-404")
        assert res_noop.status_code == 404
        await client_noop.aclose()

