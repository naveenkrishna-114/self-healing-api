"""Unit tests for HealthAwareRouter."""

import pytest

from self_healing_api.config.models import HealthConfig, RoutingConfig
from self_healing_api.errors.exceptions import AllEndpointsUnavailableError
from self_healing_api.health import HealthTracker
from self_healing_api.routing import HealthAwareRouter


@pytest.fixture()
def endpoints() -> list[str]:
    return ["https://api1.example.com", "https://api2.example.com", "https://api3.example.com"]


@pytest.fixture()
def tracker() -> HealthTracker:
    return HealthTracker(HealthConfig(enabled=True, unhealthy_threshold=2))


@pytest.mark.unit
class TestHealthAwareRouter:
    def test_priority_strategy(self, endpoints: list[str], tracker: HealthTracker) -> None:
        router = HealthAwareRouter(RoutingConfig(strategy="priority"), endpoints, tracker)
        assert router.select_endpoint() == "https://api1.example.com"
        assert router.select_endpoint() == "https://api1.example.com"

    def test_failover_when_primary_unhealthy(
        self, endpoints: list[str], tracker: HealthTracker
    ) -> None:
        router = HealthAwareRouter(RoutingConfig(strategy="priority"), endpoints, tracker)
        # Mark api1 unhealthy
        tracker.record_failure("https://api1.example.com")
        tracker.record_failure("https://api1.example.com")

        # Router fails over to api2
        assert router.select_endpoint() == "https://api2.example.com"

    def test_round_robin_strategy(self, endpoints: list[str], tracker: HealthTracker) -> None:
        router = HealthAwareRouter(RoutingConfig(strategy="round_robin"), endpoints, tracker)
        assert router.select_endpoint() == "https://api1.example.com"
        assert router.select_endpoint() == "https://api2.example.com"
        assert router.select_endpoint() == "https://api3.example.com"
        assert router.select_endpoint() == "https://api1.example.com"

    def test_all_endpoints_unhealthy_raises_error(
        self, endpoints: list[str], tracker: HealthTracker
    ) -> None:
        router = HealthAwareRouter(RoutingConfig(strategy="priority"), endpoints, tracker)
        for ep in endpoints:
            tracker.record_failure(ep)
            tracker.record_failure(ep)

        with pytest.raises(AllEndpointsUnavailableError) as exc_info:
            router.select_endpoint()
        assert exc_info.value.endpoints == endpoints

    def test_random_strategy_and_empty_endpoints(self, tracker: HealthTracker) -> None:
        router_empty = HealthAwareRouter(RoutingConfig(), [], tracker)
        with pytest.raises(AllEndpointsUnavailableError, match="No endpoints configured"):
            router_empty.select_endpoint()

        router_random = HealthAwareRouter(
            RoutingConfig(strategy="random"), ["https://r1.com", "https://r2.com"], tracker
        )
        ep = router_random.select_endpoint()
        assert ep in ["https://r1.com", "https://r2.com"]

    def test_routing_failover_disabled_and_fallback_strategy(self) -> None:
        router_no_failover = HealthAwareRouter(
            RoutingConfig(failover_enabled=False, strategy="unknown_strategy"),
            ["https://f1.com", "https://f2.com"],
            None,
        )
        assert router_no_failover.select_endpoint() == "https://f1.com"
