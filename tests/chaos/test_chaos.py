"""Chaos engineering unit tests with simulated network failures."""

import pytest

from self_healing_api.client import SelfHealingClient
from self_healing_api.config import RetryConfig
from self_healing_api.transport.fake_transport import FakeTransport, make_response


@pytest.mark.chaos
class TestChaosNetworkFailures:
    def test_intermittent_flaky_network(self) -> None:
        """Inject connection errors followed by HTTP 500s."""
        transport = FakeTransport(
            responses=[
                ConnectionError("Connection reset by peer"),
                make_response(500),
                make_response(200, json_body={"recovered": True}),
            ]
        )
        client = SelfHealingClient(
            base_url="https://flaky.example.com",
            retry=RetryConfig(max_attempts=3, base_delay=0.01),
            transport=transport,
        )

        res = client.get("/unstable")
        assert res.status_code == 200
        assert res.json() == {"recovered": True}

    def test_circuit_trip_fault_injection_and_degraded_fallback(self) -> None:
        """Inject repeated server errors to trip breaker and assert fallback UX is degraded."""
        from self_healing_api.config import CircuitBreakerConfig, FallbackConfig

        transport = FakeTransport(
            responses=[
                make_response(500),
                make_response(500),
            ]
        )
        client = SelfHealingClient(
            base_url="https://api.faulty.com",
            retry=RetryConfig(max_attempts=1),
            circuit_breaker=CircuitBreakerConfig(
                enabled=True,
                failure_threshold=2,
                recovery_timeout=60.0,
            ),
            fallback=FallbackConfig(
                static_response={"status": "degraded_service", "items": []}
            ),
            transport=transport,
        )

        # Trigger 2 failures to trip circuit breaker to OPEN
        client.get("/orders")
        client.get("/orders")

        # 3rd request trips circuit immediately to fallback
        res = client.get("/orders")
        assert res.status_code == 200
        assert res.degraded is True
        assert res.json() == {"status": "degraded_service", "items": []}
