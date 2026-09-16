"""Integration tests simulating real-world client workflows."""

import pytest

from self_healing_api.client import SelfHealingClient
from self_healing_api.config import (
    CircuitBreakerConfig,
    FallbackConfig,
    HealthConfig,
    RetryConfig,
    RoutingConfig,
)
from self_healing_api.transport.fake_transport import FakeTransport, make_response
from self_healing_api.utils.clock import FakeClock


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock(start=0.0)


@pytest.mark.integration
class TestIntegrationPipeline:
    def test_full_failover_and_retry_flow(self, clock: FakeClock) -> None:
        """Test primary endpoint failing, triggering failover to secondary endpoint."""
        transport = FakeTransport(
            responses=[
                make_response(503),  # Primary attempt 1 fails
                make_response(503),  # Primary attempt 2 fails -> primary marked unhealthy
                make_response(200, json_body={"from": "secondary"}),  # Secondary succeeds
            ]
        )
        client = SelfHealingClient(
            base_url="https://primary.api.com",
            endpoints=["https://secondary.api.com"],
            # Exhaust the primary endpoint's two allowed attempts so the
            # health threshold triggers failover before the secondary call.
            retry=RetryConfig(max_attempts=2, base_delay=0.1),
            health=HealthConfig(enabled=True, unhealthy_threshold=2),
            routing=RoutingConfig(strategy="priority", failover_enabled=True),
            transport=transport,
            clock=clock,
        )

        res = client.get("/users")
        assert res.status_code == 200
        assert res.json() == {"from": "secondary"}

    def test_circuit_breaker_short_circuits_and_recovers(self, clock: FakeClock) -> None:
        """Test circuit breaker tripping OPEN after failures, then probing and recovering."""
        transport = FakeTransport(
            responses=[
                make_response(500),
                make_response(500),  # Failure threshold 2 reached -> OPEN
                make_response(200, json_body={"recovered": True}),
            ]
        )
        client = SelfHealingClient(
            base_url="https://api.example.com",
            retry=RetryConfig(max_attempts=1),
            circuit_breaker=CircuitBreakerConfig(
                enabled=True,
                failure_threshold=2,
                success_threshold=1,
                recovery_timeout=10.0,
            ),
            health=HealthConfig(enabled=False),
            fallback=FallbackConfig(static_response={"status": "offline"}),
            transport=transport,
            clock=clock,
        )

        # Attempt 1 & 2 fail
        client.get("/data")
        client.get("/data")

        # 3rd call short-circuits via fallback because circuit is OPEN
        fb_res = client.get("/data")
        assert fb_res.json() == {"status": "offline"}
        assert fb_res.degraded is True

        # Advance time to allow probe
        clock.advance(15.0)

        # Next call probes HALF_OPEN and succeeds -> CLOSED
        rec_res = client.get("/data")
        assert rec_res.json() == {"recovered": True}
        assert rec_res.degraded is False
