"""Unit tests for TimeoutPolicy."""
from __future__ import annotations

import pytest

from self_healing_api.config.models import TimeoutConfig
from self_healing_api.errors.exceptions import (
    ConnectTimeoutError,
    ReadTimeoutError,
    SelfHealingTimeoutError,
)
from self_healing_api.timeout.policy import TimeoutPolicy
from self_healing_api.utils.clock import FakeClock


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock(start=0.0)


@pytest.fixture()
def policy(clock: FakeClock) -> TimeoutPolicy:
    return TimeoutPolicy(TimeoutConfig(connect=5.0, read=10.0, total=30.0), clock=clock)


@pytest.mark.unit
class TestTimeoutPolicy:
    def test_start_records_time(self, policy: TimeoutPolicy, clock: FakeClock) -> None:
        policy.start()
        assert policy.elapsed() == 0.0

    def test_elapsed_after_advance(self, policy: TimeoutPolicy, clock: FakeClock) -> None:
        policy.start()
        clock.advance(10.0)
        assert policy.elapsed() == pytest.approx(10.0)

    def test_remaining_decreases(self, policy: TimeoutPolicy, clock: FakeClock) -> None:
        policy.start()
        clock.advance(10.0)
        assert policy.remaining() == pytest.approx(20.0)

    def test_remaining_floored_at_zero(self, policy: TimeoutPolicy, clock: FakeClock) -> None:
        policy.start()
        clock.advance(100.0)
        assert policy.remaining() == 0.0

    def test_check_total_budget_ok(self, policy: TimeoutPolicy, clock: FakeClock) -> None:
        policy.start()
        clock.advance(5.0)
        policy.check_total_budget()  # must not raise

    def test_check_total_budget_exceeded(self, policy: TimeoutPolicy, clock: FakeClock) -> None:
        policy.start()
        clock.advance(31.0)
        with pytest.raises(ConnectTimeoutError, match="exceeded"):
            policy.check_total_budget(endpoint="https://api.example.com")

    def test_translate_stdlib_timeout(self, policy: TimeoutPolicy) -> None:
        exc = TimeoutError("timed out")
        result = policy.translate(exc)
        assert isinstance(result, SelfHealingTimeoutError)

    def test_translate_unknown_exc_unchanged(self, policy: TimeoutPolicy) -> None:
        exc = ValueError("not a timeout")
        result = policy.translate(exc)
        assert result is exc

    def test_translate_already_our_exception(self, policy: TimeoutPolicy) -> None:
        exc = ConnectTimeoutError("already ours", timeout_seconds=5.0)
        result = policy.translate(exc)
        assert result is exc

    def test_connect_timeout_property(self, policy: TimeoutPolicy) -> None:
        assert policy.connect_timeout == 5.0

    def test_read_timeout_capped_by_remaining(
        self, policy: TimeoutPolicy, clock: FakeClock
    ) -> None:
        policy.start()
        clock.advance(25.0)  # 5s left
        assert policy.read_timeout <= 5.0

    def test_start_idempotent(self, policy: TimeoutPolicy, clock: FakeClock) -> None:
        policy.start()
        clock.advance(5.0)
        policy.start()  # second call ignored
        assert policy.elapsed() == pytest.approx(5.0)

    def test_translate_httpx_timeouts(self, policy: TimeoutPolicy) -> None:
        import httpx

        res_conn = policy.translate(httpx.ConnectTimeout("conn"))
        res_read = policy.translate(httpx.ReadTimeout("read"))
        res_other = policy.translate(httpx.TimeoutException("other"))

        assert isinstance(res_conn, ConnectTimeoutError)
        assert isinstance(res_read, ReadTimeoutError)
        assert isinstance(res_other, SelfHealingTimeoutError)

    def test_elapsed_before_start(self, policy: TimeoutPolicy) -> None:
        assert policy.elapsed() == 0.0

    def test_translate_without_httpx(
        self, policy: TimeoutPolicy, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys
        monkeypatch.setitem(sys.modules, "httpx", None)
        exc = TimeoutError("stdlib timeout")
        res = policy.translate(exc)
        assert isinstance(res, SelfHealingTimeoutError)
