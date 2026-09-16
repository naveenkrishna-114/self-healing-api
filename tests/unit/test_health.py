"""Unit tests for HealthTracker and EndpointHealth."""

import pytest

from self_healing_api.config.models import HealthConfig
from self_healing_api.health import HealthState, HealthTracker
from self_healing_api.utils.clock import FakeClock


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock(start=0.0)


@pytest.fixture()
def config() -> HealthConfig:
    return HealthConfig(
        enabled=True,
        unhealthy_threshold=3,
        recovery_threshold=2,
    )


@pytest.fixture()
def tracker(config: HealthConfig, clock: FakeClock) -> HealthTracker:
    return HealthTracker(config, clock=clock)


@pytest.mark.unit
class TestHealthTracker:
    def test_initial_state_is_healthy(self, tracker: HealthTracker) -> None:
        assert tracker.is_healthy("https://api.example.com")
        assert tracker.get_state("https://api.example.com") == HealthState.HEALTHY

    def test_transitions_to_unhealthy_after_failures(self, tracker: HealthTracker) -> None:
        ep = "https://api.example.com"
        tracker.record_failure(ep)
        tracker.record_failure(ep)
        assert tracker.is_healthy(ep)

        tracker.record_failure(ep)  # 3rd failure reaches threshold
        assert not tracker.is_healthy(ep)
        assert tracker.get_state(ep) == HealthState.UNHEALTHY

    def test_recovers_after_consecutive_successes(self, tracker: HealthTracker) -> None:
        ep = "https://api.example.com"
        for _ in range(3):
            tracker.record_failure(ep)
        assert tracker.get_state(ep) == HealthState.UNHEALTHY

        tracker.record_success(ep)  # 1st success
        assert tracker.get_state(ep) == HealthState.UNHEALTHY

        tracker.record_success(ep)  # 2nd success reaches recovery_threshold
        assert tracker.get_state(ep) == HealthState.HEALTHY
        assert tracker.is_healthy(ep)

    def test_reset_clears_health(self, tracker: HealthTracker) -> None:
        ep = "https://api.example.com"
        for _ in range(3):
            tracker.record_failure(ep)
        assert not tracker.is_healthy(ep)

        tracker.reset(ep)
        assert tracker.is_healthy(ep)

    def test_disabled_tracker_always_healthy(self, clock: FakeClock) -> None:
        disabled_cfg = HealthConfig(enabled=False)
        tracker = HealthTracker(disabled_cfg, clock=clock)
        ep = "https://api.example.com"
        for _ in range(10):
            tracker.record_failure(ep)
        assert tracker.is_healthy(ep)

    def test_get_health_and_to_dict(self, tracker: HealthTracker) -> None:
        ep = "https://api.example.com"
        tracker.record_failure(ep, error="timeout")
        health = tracker.get_health(ep)
        assert health.endpoint == ep
        assert health.consecutive_failures == 1
        d = health.to_dict()
        assert d["endpoint"] == ep
        assert d["consecutive_failures"] == 1
        assert d["last_error"] == "timeout"

    def test_reset_all_and_nonexistent(self, tracker: HealthTracker) -> None:
        ep = "https://api.example.com"
        for _ in range(3):
            tracker.record_failure(ep)
        tracker.reset("https://nonexistent.com")  # not in endpoints
        assert not tracker.is_healthy(ep)
        tracker.reset(None)  # reset all
        assert tracker.is_healthy(ep)

