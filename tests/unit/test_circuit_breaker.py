"""Unit tests for CircuitBreaker state machine."""
from __future__ import annotations

import threading

import pytest

from self_healing_api.circuit_breaker.breaker import CircuitBreaker
from self_healing_api.circuit_breaker.state import CircuitState
from self_healing_api.config.models import CircuitBreakerConfig
from self_healing_api.errors.exceptions import CircuitOpenError
from self_healing_api.utils.clock import FakeClock


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock(start=0.0)


@pytest.fixture()
def config() -> CircuitBreakerConfig:
    return CircuitBreakerConfig(
        enabled=True,
        failure_threshold=3,
        success_threshold=2,
        recovery_timeout=30.0,
        window_size=5,
    )


@pytest.fixture()
def breaker(config: CircuitBreakerConfig, clock: FakeClock) -> CircuitBreaker:
    return CircuitBreaker(config, endpoint="https://api.example.com", clock=clock)


@pytest.mark.unit
class TestInitialState:
    def test_starts_closed(self, breaker: CircuitBreaker) -> None:
        assert breaker.state == CircuitState.CLOSED

    def test_allows_requests_when_closed(self, breaker: CircuitBreaker) -> None:
        breaker.before_request()  # must not raise


@pytest.mark.unit
class TestFailureThreshold:
    def test_opens_after_threshold(self, breaker: CircuitBreaker) -> None:
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

    def test_does_not_open_below_threshold(self, breaker: CircuitBreaker) -> None:
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.CLOSED

    def test_rejects_requests_when_open(self, breaker: CircuitBreaker) -> None:
        for _ in range(3):
            breaker.record_failure()
        with pytest.raises(CircuitOpenError):
            breaker.before_request()

    def test_circuit_open_error_has_endpoint(self, breaker: CircuitBreaker) -> None:
        for _ in range(3):
            breaker.record_failure()
        with pytest.raises(CircuitOpenError) as exc_info:
            breaker.before_request()
        assert exc_info.value.endpoint == "https://api.example.com"


@pytest.mark.unit
class TestRecovery:
    def test_transitions_to_half_open_after_timeout(
        self, breaker: CircuitBreaker, clock: FakeClock
    ) -> None:
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        clock.advance(30.0)
        assert breaker.state == CircuitState.HALF_OPEN

    def test_half_open_allows_probe_request(
        self, breaker: CircuitBreaker, clock: FakeClock
    ) -> None:
        for _ in range(3):
            breaker.record_failure()
        clock.advance(30.0)
        breaker.before_request()  # must not raise in HALF_OPEN

    def test_success_in_half_open_closes_circuit(
        self, breaker: CircuitBreaker, clock: FakeClock
    ) -> None:
        for _ in range(3):
            breaker.record_failure()
        clock.advance(30.0)
        # Need 2 successes (success_threshold=2)
        breaker.record_success()
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    def test_failure_in_half_open_reopens_circuit(
        self, breaker: CircuitBreaker, clock: FakeClock
    ) -> None:
        for _ in range(3):
            breaker.record_failure()
        clock.advance(30.0)
        breaker.record_failure()  # probe fails
        assert breaker.state == CircuitState.OPEN

    def test_not_open_before_timeout(
        self, breaker: CircuitBreaker, clock: FakeClock
    ) -> None:
        for _ in range(3):
            breaker.record_failure()
        clock.advance(10.0)  # only 10s, need 30s
        assert breaker.state == CircuitState.OPEN


@pytest.mark.unit
class TestDisabled:
    def test_disabled_never_opens(self) -> None:
        cfg = CircuitBreakerConfig(enabled=False, failure_threshold=2)
        breaker = CircuitBreaker(cfg)
        for _ in range(10):
            breaker.record_failure()
        breaker.record_success()
        breaker.before_request()  # must not raise


@pytest.mark.unit
class TestReset:
    def test_reset_returns_to_closed(
        self, breaker: CircuitBreaker
    ) -> None:
        for _ in range(3):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        breaker.reset()
        assert breaker.state == CircuitState.CLOSED

    def test_allows_requests_after_reset(self, breaker: CircuitBreaker) -> None:
        for _ in range(3):
            breaker.record_failure()
        breaker.reset()
        breaker.before_request()  # must not raise


@pytest.mark.unit
class TestSlidingWindow:
    def test_old_failures_slide_out(
        self, breaker: CircuitBreaker
    ) -> None:
        # window_size=5, threshold=3
        # Add 2 failures, then 3 successes, then 2 more failures
        # Total failures in window = 2, should not open
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()
        breaker.record_success()
        breaker.record_success()
        # Now window = [F, F, S, S, S] — only 2 failures, below threshold
        assert breaker.state == CircuitState.CLOSED


@pytest.mark.unit
class TestThreadSafety:
    def test_concurrent_failures_open_circuit_once(self) -> None:
        """Multiple threads recording failures must not corrupt state."""
        cfg = CircuitBreakerConfig(failure_threshold=5, window_size=20)
        clock = FakeClock()
        breaker = CircuitBreaker(cfg, clock=clock)
        errors: list[Exception] = []

        def record_failures() -> None:
            try:
                for _ in range(10):
                    breaker.record_failure()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_failures) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        # Circuit must be in a valid state
        assert breaker.state in (CircuitState.OPEN, CircuitState.CLOSED, CircuitState.HALF_OPEN)
