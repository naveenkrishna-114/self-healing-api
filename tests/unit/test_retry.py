"""Unit tests for retry engine, backoff, and jitter."""
from __future__ import annotations

import pytest

from self_healing_api.config.models import RetryConfig
from self_healing_api.errors.categories import ErrorCategory
from self_healing_api.errors.exceptions import CircuitOpenError
from self_healing_api.retry.backoff import compute_delay
from self_healing_api.retry.engine import RetryEngine
from self_healing_api.retry.jitter import apply_jitter

# ── Backoff tests ─────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestBackoff:
    def test_exponential_doubles(self) -> None:
        assert compute_delay("exponential", base=1.0, attempt=0, max_delay=60) == pytest.approx(1.0)
        assert compute_delay("exponential", base=1.0, attempt=1, max_delay=60) == pytest.approx(2.0)
        assert compute_delay("exponential", base=1.0, attempt=2, max_delay=60) == pytest.approx(4.0)

    def test_exponential_capped(self) -> None:
        assert compute_delay("exponential", base=1.0, attempt=10, max_delay=60) == 60.0

    def test_linear_increments(self) -> None:
        assert compute_delay("linear", base=2.0, attempt=0, max_delay=60) == pytest.approx(2.0)
        assert compute_delay("linear", base=2.0, attempt=1, max_delay=60) == pytest.approx(4.0)
        assert compute_delay("linear", base=2.0, attempt=2, max_delay=60) == pytest.approx(6.0)

    def test_fixed_always_base(self) -> None:
        for attempt in range(5):
            delay = compute_delay("fixed", base=3.0, attempt=attempt, max_delay=60)
            assert delay == pytest.approx(3.0)

    def test_unknown_strategy_fallback(self) -> None:
        delay = compute_delay("unknown_strategy", base=2.0, attempt=1, max_delay=60)
        assert delay == pytest.approx(4.0)


# ── Jitter tests ──────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestJitter:
    def test_full_jitter_in_range(self) -> None:
        for _ in range(50):
            result = apply_jitter("full", delay=10.0)
            assert 0.0 <= result <= 10.0

    def test_equal_jitter_in_range(self) -> None:
        for _ in range(50):
            result = apply_jitter("equal", delay=10.0)
            assert 5.0 <= result <= 10.0

    def test_decorrelated_jitter_positive(self) -> None:
        for _ in range(50):
            result = apply_jitter("decorrelated", delay=4.0, base=1.0, prev_delay=2.0)
            assert result >= 1.0

    def test_decorrelated_jitter_none_prev_delay(self) -> None:
        result = apply_jitter("decorrelated", delay=4.0, base=2.0, prev_delay=None)
        assert result >= 2.0

    def test_unknown_jitter_strategy_fallback(self) -> None:
        result = apply_jitter("custom_jitter", delay=5.0)
        assert 0.0 <= result <= 5.0


# ── RetryEngine tests ─────────────────────────────────────────────────────────

@pytest.fixture()
def engine() -> RetryEngine:
    cfg = RetryConfig(max_attempts=3, backoff="exponential", jitter=False, base_delay=1.0)
    return RetryEngine(cfg)


@pytest.mark.unit
class TestRetryEngine:
    def test_retries_on_connection_error(self, engine: RetryEngine) -> None:
        engine.start()
        decision = engine.evaluate(ConnectionError("refused"), attempt=0)
        assert decision.should_retry is True
        assert decision.delay > 0

    def test_no_retry_on_auth_error(self, engine: RetryEngine) -> None:
        engine.start()
        decision = engine.evaluate(Exception("401"), attempt=0, http_status=401)
        assert decision.should_retry is False
        assert "not retryable" in decision.reason

    def test_no_retry_on_client_error(self, engine: RetryEngine) -> None:
        engine.start()
        decision = engine.evaluate(Exception("400"), attempt=0, http_status=400)
        assert decision.should_retry is False

    def test_no_retry_when_max_attempts_reached(self, engine: RetryEngine) -> None:
        engine.start()
        # attempt=2 means this is the 3rd attempt (0-based), max_attempts=3
        decision = engine.evaluate(ConnectionError("refused"), attempt=2)
        assert decision.should_retry is False
        assert "max_attempts" in decision.reason

    def test_no_retry_for_non_idempotent(self, engine: RetryEngine) -> None:
        engine.start()
        decision = engine.evaluate(
            ConnectionError("refused"), attempt=0, is_idempotent=False
        )
        assert decision.should_retry is False
        assert "idempotent" in decision.reason

    def test_delay_is_exponential(self, engine: RetryEngine) -> None:
        engine.start()
        d0 = engine.evaluate(ConnectionError("x"), attempt=0).delay
        d1 = engine.evaluate(ConnectionError("x"), attempt=1).delay
        assert d1 > d0

    def test_server_error_retried(self, engine: RetryEngine) -> None:
        engine.start()
        decision = engine.evaluate(Exception("503"), attempt=0, http_status=503)
        assert decision.should_retry is True

    def test_429_retried(self, engine: RetryEngine) -> None:
        engine.start()
        decision = engine.evaluate(Exception("429"), attempt=0, http_status=429)
        assert decision.should_retry is True

    def test_circuit_open_not_retried(self, engine: RetryEngine) -> None:
        engine.start()
        exc = CircuitOpenError("circuit open")
        decision = engine.evaluate(exc, attempt=0)
        assert decision.should_retry is False

    def test_decision_has_category(self, engine: RetryEngine) -> None:
        engine.start()
        decision = engine.evaluate(ConnectionError("x"), attempt=0)
        assert isinstance(decision.category, ErrorCategory)

    def test_jitter_adds_randomness(self) -> None:
        cfg = RetryConfig(max_attempts=5, jitter=True, jitter_strategy="full", base_delay=1.0)
        eng = RetryEngine(cfg)
        delays = set()
        for _ in range(20):
            eng.start()
            d = eng.evaluate(ConnectionError("x"), attempt=0).delay
            delays.add(round(d, 4))
        # With jitter we should see multiple distinct delay values
        assert len(delays) > 1

    def test_sleep_method(self, engine: RetryEngine) -> None:
        engine.sleep(-1.0)
        engine.sleep(0.0)
        engine.sleep(0.0001)
