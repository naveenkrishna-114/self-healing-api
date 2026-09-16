"""Unit tests for FallbackHandler."""

import pytest

from self_healing_api.config.models import FallbackConfig
from self_healing_api.errors.exceptions import FallbackError, RequestError
from self_healing_api.fallback import FallbackContext, FallbackHandler
from self_healing_api.transport.fake_transport import make_response


@pytest.fixture()
def context() -> FallbackContext:
    return FallbackContext(
        endpoint="https://api.example.com",
        method="GET",
        url="https://api.example.com/data",
        error=RequestError("Original error"),
        attempt_count=3,
    )


@pytest.mark.unit
class TestFallbackHandler:
    def test_custom_callable_handler(self, context: FallbackContext) -> None:
        def custom_handler(ctx: FallbackContext) -> dict:
            return {"fallback": True, "attempts": ctx.attempt_count}

        handler = FallbackHandler(FallbackConfig(handler=custom_handler))
        res = handler.execute_fallback(context)
        assert res.status_code == 200
        assert res.headers.get("x-self-healing-fallback") == "true"
        assert res.degraded is True

    def test_custom_callable_raises_fallback_error(self, context: FallbackContext) -> None:
        def broken_handler(ctx: FallbackContext) -> None:
            raise ValueError("Handler broken")

        handler = FallbackHandler(FallbackConfig(handler=broken_handler))
        with pytest.raises(FallbackError) as exc_info:
            handler.execute_fallback(context)
        assert exc_info.value.original_error == context.error

    def test_cache_last_success(self, context: FallbackContext) -> None:
        handler = FallbackHandler(FallbackConfig(cache_last_success=True))
        route = "GET:https://api.example.com/data"
        good_response = make_response(200, body=b'{"ok": true}')
        handler.cache_response(route, good_response)

        res = handler.execute_fallback(context, route_key=route)
        assert res.status_code == 200
        assert res.headers.get("x-self-healing-stale") == "true"
        assert res.degraded is True

    def test_static_response(self, context: FallbackContext) -> None:
        handler = FallbackHandler(FallbackConfig(static_response="offline payload"))
        res = handler.execute_fallback(context)
        assert res.status_code == 200
        assert res.content == b"offline payload"
        assert res.degraded is True

    def test_no_fallback_reraises_original_error(self, context: FallbackContext) -> None:
        handler = FallbackHandler(FallbackConfig())
        with pytest.raises(RequestError):
            handler.execute_fallback(context)

    def test_fallback_handler_returns_various_types(self, context: FallbackContext) -> None:
        resp = make_response(200, json_body={"direct": True})
        handler = FallbackHandler(FallbackConfig(handler=lambda: resp))
        res = handler.execute_fallback(context)
        assert res.json() == {"direct": True}
        assert res.degraded is True

        str_handler = FallbackHandler(FallbackConfig(handler=lambda: "plain text"))
        res_str = str_handler.execute_fallback(context)
        assert res_str.text() == "plain text"
        assert res_str.degraded is True

        int_handler = FallbackHandler(FallbackConfig(handler=lambda: 999))
        res_int = int_handler.execute_fallback(context)
        assert res_int.text() == "999"
        assert res_int.degraded is True

    def test_fallback_handler_returns_none_and_fallback_error_raised(
        self, context: FallbackContext
    ) -> None:
        from self_healing_api.errors.exceptions import FallbackError

        # Handler returns None -> falls through to static response
        handler_none = FallbackHandler(
            FallbackConfig(handler=lambda: None, static_response={"status": "ok"})
        )
        res = handler_none.execute_fallback(context)
        assert res.json() == {"status": "ok"}

        # Handler raises FallbackError
        def raise_fallback() -> None:
            raise FallbackError("direct fallback error")

        handler_err = FallbackHandler(FallbackConfig(handler=raise_fallback))
        with pytest.raises(FallbackError, match="direct fallback error"):
            handler_err.execute_fallback(context)

    def test_fallback_cache_miss_and_static_transport_response(
        self, context: FallbackContext
    ) -> None:
        static_resp = make_response(200, json_body={"from_resp": True})
        # Cache miss falls through to static TransportResponse
        handler = FallbackHandler(
            FallbackConfig(cache_last_success=True, static_response=static_resp)
        )
        res = handler.execute_fallback(context)
        assert res.json() == {"from_resp": True}
        assert res.degraded is True
