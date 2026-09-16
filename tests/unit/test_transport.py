"""
Unit tests for transport abstractions and FakeTransport.

These tests never make real HTTP calls. They verify:
- TransportRequest / TransportResponse value objects
- FakeTransport scripted sequences
- FakeTransport exception injection
- FakeTransport URL-specific queues
- FakeTransport assertion helpers
- make_response() helper
"""
from __future__ import annotations

from datetime import UTC

import pytest

from self_healing_api.transport.base import TransportRequest, TransportResponse
from self_healing_api.transport.fake_transport import (
    FakeTransport,
    make_response,
)

# ── TransportRequest tests ────────────────────────────────────────────────────

@pytest.mark.unit
class TestTransportRequest:
    def test_method_uppercased(self) -> None:
        req = TransportRequest(method="get", url="https://api.example.com/data")
        assert req.method == "GET"

    def test_defaults(self) -> None:
        req = TransportRequest(method="POST", url="https://api.example.com")
        assert req.headers == {}
        assert req.params == {}
        assert req.json is None
        assert req.content is None
        assert req.timeout_connect == 5.0
        assert req.timeout_read == 30.0
        assert req.request_id == ""

    def test_full_construction(self) -> None:
        req = TransportRequest(
            method="POST",
            url="https://api.example.com/orders",
            headers={"Authorization": "Bearer token"},
            json={"item": "book"},
            request_id="req-abc",
        )
        assert req.method == "POST"
        assert req.headers["Authorization"] == "Bearer token"
        assert req.json == {"item": "book"}
        assert req.request_id == "req-abc"


# ── TransportResponse tests ───────────────────────────────────────────────────

@pytest.mark.unit
class TestTransportResponse:
    def _make_req(self) -> TransportRequest:
        return TransportRequest(method="GET", url="https://api.example.com")

    def test_is_success(self) -> None:
        resp = TransportResponse(
            status_code=200, headers={}, content=b"ok",
            request=self._make_req()
        )
        assert resp.is_success is True
        assert resp.is_client_error is False
        assert resp.is_server_error is False

    def test_is_client_error(self) -> None:
        resp = TransportResponse(
            status_code=404, headers={}, content=b"not found",
            request=self._make_req()
        )
        assert resp.is_client_error is True
        assert resp.is_success is False

    def test_is_server_error(self) -> None:
        resp = TransportResponse(
            status_code=503, headers={}, content=b"unavailable",
            request=self._make_req()
        )
        assert resp.is_server_error is True
        assert resp.is_success is False

    def test_json_parsing(self) -> None:
        import json
        body = json.dumps({"key": "value"}).encode()
        resp = TransportResponse(
            status_code=200, headers={}, content=body,
            request=self._make_req()
        )
        assert resp.json() == {"key": "value"}

    def test_text_decoding(self) -> None:
        resp = TransportResponse(
            status_code=200, headers={}, content=b"hello world",
            request=self._make_req()
        )
        assert resp.text() == "hello world"

    def test_repr(self) -> None:
        resp = TransportResponse(
            status_code=200, headers={}, content=b"",
            request=self._make_req(), elapsed_ms=42.5
        )
        assert "200" in repr(resp)
        assert "42.5" in repr(resp)


# ── make_response helper ──────────────────────────────────────────────────────

@pytest.mark.unit
class TestMakeResponse:
    def test_default_200(self) -> None:
        r = make_response()
        assert r.status_code == 200
        assert r.content == b""

    def test_json_body(self) -> None:
        r = make_response(json_body={"ok": True})
        assert r.json() == {"ok": True}
        assert r.headers["content-type"] == "application/json"

    def test_bytes_body(self) -> None:
        r = make_response(status_code=201, body=b"created")
        assert r.status_code == 201
        assert r.content == b"created"

    def test_custom_headers(self) -> None:
        r = make_response(headers={"x-request-id": "abc"})
        assert r.headers["x-request-id"] == "abc"

    def test_elapsed_ms(self) -> None:
        r = make_response(elapsed_ms=55.0)
        assert r.elapsed_ms == 55.0


# ── FakeTransport tests ───────────────────────────────────────────────────────

@pytest.mark.unit
class TestFakeTransport:
    def _make_req(self, url: str = "https://api.example.com/data") -> TransportRequest:
        return TransportRequest(method="GET", url=url)

    def test_single_scripted_response(self) -> None:
        transport = FakeTransport(responses=[make_response(200)])
        resp = transport.send(self._make_req())
        assert resp.status_code == 200
        assert transport.call_count == 1

    def test_sequence_of_responses(self) -> None:
        transport = FakeTransport(responses=[
            make_response(503),
            make_response(503),
            make_response(200),
        ])
        r1 = transport.send(self._make_req())
        r2 = transport.send(self._make_req())
        r3 = transport.send(self._make_req())
        assert r1.status_code == 503
        assert r2.status_code == 503
        assert r3.status_code == 200
        assert transport.call_count == 3

    def test_exception_injection(self) -> None:
        transport = FakeTransport(responses=[
            ConnectionError("connection refused"),
            make_response(200),
        ])
        with pytest.raises(ConnectionError, match="connection refused"):
            transport.send(self._make_req())
        # Second call succeeds
        resp = transport.send(self._make_req())
        assert resp.status_code == 200

    def test_default_response_when_queue_empty(self) -> None:
        transport = FakeTransport(
            responses=[make_response(500)],
            default_response=make_response(200),
        )
        transport.send(self._make_req())  # consumes the 500
        # Subsequent calls use the default
        resp = transport.send(self._make_req())
        assert resp.status_code == 200
        resp2 = transport.send(self._make_req())
        assert resp2.status_code == 200

    def test_no_responses_raises_runtime_error(self) -> None:
        transport = FakeTransport()
        with pytest.raises(RuntimeError, match="no more scripted responses"):
            transport.send(self._make_req())

    def test_request_is_recorded(self) -> None:
        transport = FakeTransport(default_response=make_response(200))
        req = self._make_req("https://api.example.com/orders")
        transport.send(req)
        assert len(transport.requests) == 1
        assert transport.requests[0].url == "https://api.example.com/orders"

    def test_last_request(self) -> None:
        transport = FakeTransport(default_response=make_response(200))
        transport.send(self._make_req("https://api.example.com/a"))
        transport.send(self._make_req("https://api.example.com/b"))
        assert transport.last_request is not None
        assert transport.last_request.url == "https://api.example.com/b"

    def test_last_request_none_when_no_calls(self) -> None:
        transport = FakeTransport()
        assert transport.last_request is None

    def test_request_body_attached_to_response(self) -> None:
        transport = FakeTransport(default_response=make_response(200))
        req = TransportRequest(method="POST", url="https://api.example.com")
        resp = transport.send(req)
        assert resp.request is req

    def test_call_delay_applied(self) -> None:
        transport = FakeTransport(
            default_response=make_response(200, elapsed_ms=10.0),
            call_delay_ms=50.0,
        )
        resp = transport.send(self._make_req())
        assert resp.elapsed_ms == 60.0  # 10 + 50

    def test_url_specific_queue(self) -> None:
        transport = FakeTransport(
            url_responses={
                "/orders": [make_response(201)],
                "/data": [make_response(200)],
            },
        )
        r1 = transport.send(self._make_req("https://api.example.com/orders"))
        r2 = transport.send(self._make_req("https://api.example.com/data"))
        assert r1.status_code == 201
        assert r2.status_code == 200

    def test_close_is_noop(self) -> None:
        transport = FakeTransport()
        transport.close()  # must not raise

    def test_reset_clears_state(self) -> None:
        transport = FakeTransport(default_response=make_response(200))
        transport.send(self._make_req())
        transport.send(self._make_req())
        transport.reset()
        assert transport.call_count == 0
        assert transport.requests == []

    def test_add_response_at_runtime(self) -> None:
        transport = FakeTransport()
        transport.add_response(make_response(204))
        resp = transport.send(self._make_req())
        assert resp.status_code == 204

    def test_assert_request_count_passes(self) -> None:
        transport = FakeTransport(default_response=make_response(200))
        transport.send(self._make_req())
        transport.send(self._make_req())
        transport.assert_request_count(2)  # must not raise

    def test_assert_request_count_fails(self) -> None:
        transport = FakeTransport(default_response=make_response(200))
        transport.send(self._make_req())
        with pytest.raises(AssertionError):
            transport.assert_request_count(5)

    def test_assert_last_method(self) -> None:
        transport = FakeTransport(default_response=make_response(200))
        transport.send(TransportRequest(method="DELETE", url="https://api.example.com/x"))
        transport.assert_last_method("DELETE")

    def test_context_manager(self) -> None:
        with FakeTransport(default_response=make_response(200)) as transport:
            resp = transport.send(self._make_req())
        assert resp.status_code == 200

    def test_assert_header_sent(self) -> None:
        transport = FakeTransport(default_response=make_response(200))
        transport.send(TransportRequest(
            method="GET",
            url="https://api.example.com/x",
            headers={"X-Test": "123"},
        ))
        transport.assert_header_sent("X-Test", "123")

    def test_url_queue_empty_fallback(self) -> None:
        transport = FakeTransport(
            url_responses={"/empty": []},
            default_response=make_response(200),
        )
        resp = transport.send(TransportRequest(method="GET", url="https://api.example.com/empty"))
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_fake_async_transport_exhausted_and_exception(self) -> None:
        from self_healing_api.transport.fake_transport import FakeAsyncTransport

        async_t = FakeAsyncTransport(responses=[ValueError("Async error")])
        req = TransportRequest(method="GET", url="https://api.example.com/async")
        with pytest.raises(ValueError, match="Async error"):
            await async_t.send(req)

        # Now empty queue without default response
        with pytest.raises(RuntimeError, match="has no more scripted responses"):
            await async_t.send(req)


# ── Utils tests ───────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestClock:
    def test_system_clock_monotonic_increases(self) -> None:
        from self_healing_api.utils.clock import SystemClock
        clock = SystemClock()
        t1 = clock.monotonic()
        t2 = clock.monotonic()
        assert t2 >= t1

    def test_fake_clock_starts_at_zero(self) -> None:
        from self_healing_api.utils.clock import FakeClock
        clock = FakeClock()
        assert clock.monotonic() == 0.0

    def test_fake_clock_advance(self) -> None:
        from self_healing_api.utils.clock import FakeClock
        clock = FakeClock(start=100.0)
        clock.advance(30.0)
        assert clock.monotonic() == 130.0

    def test_fake_clock_advance_negative_raises(self) -> None:
        from self_healing_api.utils.clock import FakeClock
        clock = FakeClock()
        with pytest.raises(ValueError, match="non-negative"):
            clock.advance(-1.0)

    def test_fake_clock_now_returns_datetime(self) -> None:

        from self_healing_api.utils.clock import FakeClock
        clock = FakeClock()
        dt = clock.now()
        assert dt.tzinfo == UTC

    def test_system_clock_now(self) -> None:
        from self_healing_api.utils.clock import SystemClock
        clock = SystemClock()
        assert clock.now().tzinfo == UTC

    def test_fake_clock_set_monotonic_and_repr(self) -> None:
        from self_healing_api.utils.clock import FakeClock
        clock = FakeClock(start=5.0)
        clock.set_monotonic(42.0)
        assert clock.monotonic() == 42.0
        assert "FakeClock" in repr(clock)


@pytest.mark.unit
class TestIds:
    def test_generate_request_id_is_uuid(self) -> None:
        from self_healing_api.utils.ids import generate_request_id, is_valid_uuid
        rid = generate_request_id()
        assert is_valid_uuid(rid)

    def test_request_ids_are_unique(self) -> None:
        from self_healing_api.utils.ids import generate_request_id
        ids = {generate_request_id() for _ in range(100)}
        assert len(ids) == 100

    def test_idempotency_key_is_valid_uuid(self) -> None:
        from self_healing_api.utils.ids import generate_idempotency_key, is_valid_uuid
        key = generate_idempotency_key()
        assert is_valid_uuid(key)

    def test_is_valid_uuid_rejects_invalid(self) -> None:
        from self_healing_api.utils.ids import is_valid_uuid
        assert is_valid_uuid("not-a-uuid") is False
        assert is_valid_uuid("") is False


@pytest.mark.unit
class TestSecretMasker:
    def test_masks_authorization_header(self) -> None:
        from self_healing_api.utils.masking import SecretMasker
        masker = SecretMasker()
        result = masker.mask_headers({"Authorization": "Bearer secret123"})
        assert result["Authorization"] == "***MASKED***"

    def test_preserves_non_sensitive_headers(self) -> None:
        from self_healing_api.utils.masking import SecretMasker
        masker = SecretMasker()
        result = masker.mask_headers({"Content-Type": "application/json"})
        assert result["Content-Type"] == "application/json"

    def test_case_insensitive_header_matching(self) -> None:
        from self_healing_api.utils.masking import SecretMasker
        masker = SecretMasker()
        result = masker.mask_headers({"authorization": "token abc"})
        assert result["authorization"] == "***MASKED***"

    def test_custom_masked_header(self) -> None:
        from self_healing_api.utils.masking import SecretMasker
        masker = SecretMasker(masked_headers={"X-Custom-Secret"})
        result = masker.mask_headers({"X-Custom-Secret": "myvalue"})
        assert result["X-Custom-Secret"] == "***MASKED***"

    def test_mask_body_fields(self) -> None:
        from self_healing_api.utils.masking import SecretMasker
        masker = SecretMasker(masked_body_fields={"password", "secret"})
        result = masker.mask_body({"username": "alice", "password": "hunter2"})
        assert result["username"] == "alice"
        assert result["password"] == "***MASKED***"

    def test_mask_url_query_param(self) -> None:
        from self_healing_api.utils.masking import SecretMasker
        masker = SecretMasker()
        url = "https://api.example.com/data?api_key=supersecret&page=1"
        masked = masker.mask_url(url)
        assert "supersecret" not in masked
        assert "page=1" in masked

    def test_mask_url_no_query(self) -> None:
        from self_healing_api.utils.masking import SecretMasker
        masker = SecretMasker()
        url = "https://api.example.com/data"
        assert masker.mask_url(url) == url

    def test_is_header_masked(self) -> None:
        from self_healing_api.utils.masking import SecretMasker
        masker = SecretMasker()
        assert masker.is_header_masked("Authorization") is True
        assert masker.is_header_masked("Content-Type") is False

    def test_mask_body_empty_fields(self) -> None:
        from self_healing_api.utils.masking import SecretMasker
        masker = SecretMasker(masked_body_fields=frozenset())
        payload = {"data": 123}
        assert masker.mask_body(payload) == payload


@pytest.mark.unit
class TestHttpxTransportLayers:
    def test_httpx_sync_and_async_transport(self) -> None:
        import httpx

        from self_healing_api.transport.httpx_transport import HttpxTransport

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"mock": True})

        mock_mount = httpx.MockTransport(handler)

        sync_t = HttpxTransport(base_url="https://mock.local")
        sync_t._client = httpx.Client(transport=mock_mount)
        req = TransportRequest(method="GET", url="https://mock.local/test")
        res = sync_t.send(req)
        assert res.status_code == 200
        assert res.json() == {"mock": True}
        sync_t.close()

    @pytest.mark.asyncio
    async def test_httpx_async_transport(self) -> None:
        import httpx

        from self_healing_api.transport.httpx_transport import AsyncHttpxTransport

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"async_mock": True})

        mock_mount = httpx.MockTransport(handler)

        async_t = AsyncHttpxTransport()
        async_t._client = httpx.AsyncClient(transport=mock_mount)
        req = TransportRequest(method="POST", url="https://mock.local/test", json={"k": "v"})
        res = await async_t.send(req)
        assert res.status_code == 200
        assert res.json() == {"async_mock": True}
        await async_t.close()


@pytest.mark.unit
class TestBaseTransport:
    def test_raise_for_status_success(self) -> None:
        resp = make_response(200)
        resp.raise_for_status()  # no-op, must not raise

    def test_raise_for_status_without_httpx(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys
        monkeypatch.setitem(sys.modules, "httpx", None)
        resp = make_response(500)
        with pytest.raises(ValueError, match="HTTP 500 error"):
            resp.raise_for_status()

    @pytest.mark.asyncio
    async def test_abstract_async_transport_context_manager(self) -> None:
        from self_healing_api.transport.base import AbstractAsyncTransport

        class DummyAsyncTransport(AbstractAsyncTransport):
            def __init__(self) -> None:
                self.closed = False

            async def send(self, request: TransportRequest) -> TransportResponse:
                return make_response(200)

            async def close(self) -> None:
                self.closed = True

        dummy = DummyAsyncTransport()
        async with dummy as t:
            assert t is dummy
        assert dummy.closed is True
