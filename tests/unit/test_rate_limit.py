"""Unit tests for RateLimitHandler."""

from datetime import UTC

import pytest

from self_healing_api.config.models import RateLimitConfig
from self_healing_api.errors.exceptions import RateLimitError
from self_healing_api.rate_limit import RateLimitHandler
from self_healing_api.transport.fake_transport import make_response


@pytest.mark.unit
class TestRateLimitHandler:
    def test_parse_retry_after_seconds(self) -> None:
        handler = RateLimitHandler(RateLimitConfig())
        res = make_response(429, headers={"retry-after": "30"})
        assert handler.parse_retry_after(res) == 30.0

    def test_exceeds_max_retry_after_wait_raises(self) -> None:
        handler = RateLimitHandler(RateLimitConfig(max_retry_after_wait=60.0))
        res = make_response(429, headers={"retry-after": "120"})
        with pytest.raises(RateLimitError) as exc_info:
            handler.process_rate_limit(res)
        assert exc_info.value.retry_after == 120.0

    def test_valid_retry_after_returns_delay(self) -> None:
        handler = RateLimitHandler(RateLimitConfig(max_retry_after_wait=60.0))
        res = make_response(429, headers={"retry-after": "15"})
        delay = handler.process_rate_limit(res)
        assert delay == 15.0

    def test_no_retry_after_returns_none(self) -> None:
        handler = RateLimitHandler(RateLimitConfig())
        res = make_response(429)
        assert handler.process_rate_limit(res) is None

    def test_parse_retry_after_http_date_and_non_429(self) -> None:
        import email.utils
        from datetime import datetime, timedelta

        handler = RateLimitHandler(RateLimitConfig())
        future = datetime.now(UTC) + timedelta(seconds=100)
        date_str = email.utils.format_datetime(future)

        res = make_response(429, headers={"retry-after": date_str})
        delay = handler.parse_retry_after(res)
        assert delay is not None
        assert 90.0 < delay < 110.0

        # Non-429 response returns 0.0
        res_200 = make_response(200)
        assert handler.process_rate_limit(res_200) == 0.0

    def test_parse_retry_after_naive_date_and_invalid_date(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import email.utils
        from datetime import datetime, timedelta

        handler = RateLimitHandler(RateLimitConfig())
        # Naive datetime
        future_naive = datetime.now() + timedelta(seconds=50)
        monkeypatch.setattr(email.utils, "parsedate_to_datetime", lambda _: future_naive)
        res_naive = make_response(429, headers={"retry-after": "somedate"})
        delay = handler.parse_retry_after(res_naive)
        assert delay is not None

        # None return from date parsing
        monkeypatch.setattr(email.utils, "parsedate_to_datetime", lambda _: None)
        res_none = make_response(429, headers={"retry-after": "nonedate"})
        assert handler.parse_retry_after(res_none) is None

        # Invalid date exception
        monkeypatch.setattr(email.utils, "parsedate_to_datetime", lambda _: 1 / 0)
        res_err = make_response(429, headers={"retry-after": "baddate"})
        assert handler.parse_retry_after(res_err) is None

    def test_process_rate_limit_ignore_retry_after(self) -> None:
        handler = RateLimitHandler(RateLimitConfig(respect_retry_after=False))
        res = make_response(429, headers={"retry-after": "10"})
        assert handler.process_rate_limit(res) is None
