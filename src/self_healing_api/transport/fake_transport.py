"""
fake_transport.py — Deterministic FakeTransport for testing.

FakeTransport is the most important test tool in this package.
Because the package changes network behaviour, every test that
exercises resilience logic (retry, circuit breaker, failover, etc.)
uses FakeTransport to inject scripted responses — no real network,
no flaky tests, fully deterministic.

Features
--------
- Script a sequence of responses (success, error, exception) per URL or globally.
- Record all requests sent so tests can assert what was called and how.
- Raise exceptions on demand (connection errors, timeouts).
- Simulate delays (without real sleep — just records elapsed_ms).
- Async variant (FakeAsyncTransport) for Phase 14 tests.

Usage
-----
::

    # Always return 200
    transport = FakeTransport(default_response=make_response(200))

    # Return 503 twice, then 200
    transport = FakeTransport(responses=[
        make_response(503),
        make_response(503),
        make_response(200, body=b'{"ok": true}'),
    ])

    # Raise connection error on first call, succeed on second
    transport = FakeTransport(responses=[
        ConnectionError("refused"),
        make_response(200),
    ])

    client.get("/data")   # uses transport — no network

    assert len(transport.requests) == 2   # two attempts made
    assert transport.requests[0].url.endswith("/data")
"""

from __future__ import annotations

import json as _json
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from self_healing_api.transport.base import (
    AbstractAsyncTransport,
    AbstractTransport,
    TransportRequest,
    TransportResponse,
)

# ── Response builder helper ───────────────────────────────────────────────────

def make_response(
    status_code: int = 200,
    body: bytes | None = None,
    json_body: Any = None,
    headers: dict[str, str] | None = None,
    elapsed_ms: float = 10.0,
    degraded: bool = False,
) -> TransportResponse:
    """
    Build a TransportResponse for use in FakeTransport scripts.

    Parameters
    ----------
    status_code : int
        HTTP status code. Default: 200.
    body : bytes | None
        Raw response body. If json_body is provided, this is ignored.
    json_body : Any
        Python object to serialise as JSON body.
    headers : dict[str, str] | None
        Response headers. Default: {"content-type": "application/json"}.
    elapsed_ms : float
        Simulated response time in milliseconds. Default: 10.0.

    Returns
    -------
    TransportResponse
        A scripted response suitable for FakeTransport.
    """
    if json_body is not None:
        content = _json.dumps(json_body).encode("utf-8")
        default_headers = {"content-type": "application/json"}
    else:
        content = body or b""
        default_headers = {"content-type": "application/octet-stream"}

    # Placeholder request — will be replaced with the real request when sent
    placeholder_request = TransportRequest(method="GET", url="")

    return TransportResponse(
        status_code=status_code,
        headers=headers if headers is not None else default_headers,
        content=content,
        request=placeholder_request,
        elapsed_ms=elapsed_ms,
        degraded=degraded,
    )


# ── Response script entry ─────────────────────────────────────────────────────

# A script entry is either a TransportResponse (returned as-is)
# or an Exception (raised when the transport is called).
ResponseEntry = TransportResponse | Exception


@dataclass
class FakeTransport(AbstractTransport):
    """
    Deterministic synchronous transport for unit and integration tests.

    Parameters
    ----------
    responses : list[ResponseEntry] | None
        Ordered list of responses/exceptions to return. Each call to
        ``send()`` pops the next entry. If the list is exhausted and
        ``default_response`` is set, that is returned. If neither
        is available, raises ``RuntimeError``.
    default_response : TransportResponse | None
        Fallback response returned when ``responses`` is exhausted.
        If None and responses is empty, ``send()`` raises RuntimeError.
    url_responses : dict[str, list[ResponseEntry]] | None
        Per-URL response queues. Takes priority over the global queue
        when the request URL ends with (or equals) the dict key.
    call_delay_ms : float
        Simulated response time added to all responses. Default: 0.0.

    Attributes
    ----------
    requests : list[TransportRequest]
        All requests that were sent through this transport.
        Inspect in tests to verify what the client called.
    call_count : int
        Total number of ``send()`` calls.
    """

    responses: list[ResponseEntry] = field(default_factory=list)
    default_response: TransportResponse | None = None
    url_responses: dict[str, list[ResponseEntry]] = field(default_factory=dict)
    call_delay_ms: float = 0.0

    # Recorded for test assertions — not constructor args
    requests: list[TransportRequest] = field(default_factory=list, init=False)
    call_count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        # Convert to deque for efficient popleft
        self._queue: deque[ResponseEntry] = deque(self.responses)
        self._url_queues: dict[str, deque[ResponseEntry]] = {
            k: deque(v) for k, v in self.url_responses.items()
        }

    def send(self, request: TransportRequest) -> TransportResponse:
        """
        Return the next scripted response or raise the next scripted exception.

        Parameters
        ----------
        request : TransportRequest
            The request being sent (recorded for later assertion).

        Returns
        -------
        TransportResponse
            The next scripted response with ``request`` field populated.

        Raises
        ------
        Exception
            If the next scripted entry is an Exception.
        RuntimeError
            If no more scripted responses and no default_response.
        """
        self.requests.append(request)
        self.call_count += 1

        entry = self._get_next_entry(request.url)

        if isinstance(entry, Exception):
            raise entry

        # Attach the real request to the response copy
        response = TransportResponse(
            status_code=entry.status_code,
            headers=entry.headers,
            content=entry.content,
            request=request,
            elapsed_ms=entry.elapsed_ms + self.call_delay_ms,
        )
        return response

    def _get_next_entry(self, url: str) -> ResponseEntry:
        """Get the next entry, checking URL-specific queues first."""
        # Check URL-specific queues (match by suffix for path matching)
        for url_key, queue in self._url_queues.items():
            if url.endswith(url_key) or url_key in url:
                if queue:
                    return queue.popleft()

        # Fall back to global queue
        if self._queue:
            return self._queue.popleft()

        # Fall back to default response
        if self.default_response is not None:
            return self.default_response

        raise RuntimeError(
            f"FakeTransport has no more scripted responses for URL: {url!r}. "
            "Add more entries to `responses` or set `default_response`."
        )

    def close(self) -> None:
        """No-op — FakeTransport has no real resources to release."""

    def reset(self) -> None:
        """Clear recorded requests and reset call count. Useful between test cases."""
        self.requests.clear()
        self.call_count = 0

    def add_response(self, entry: ResponseEntry) -> None:
        """Append a response or exception to the global queue at runtime."""
        self._queue.append(entry)

    @property
    def last_request(self) -> TransportRequest | None:
        """Return the most recent request, or None if no requests have been sent."""
        return self.requests[-1] if self.requests else None

    def assert_request_count(self, expected: int) -> None:
        """Assert that exactly ``expected`` requests were sent."""
        assert self.call_count == expected, (
            f"Expected {expected} request(s), got {self.call_count}"
        )

    def assert_last_method(self, method: str) -> None:
        """Assert the last request used the given HTTP method."""
        assert self.last_request is not None, "No requests have been sent"
        assert self.last_request.method == method.upper(), (
            f"Expected method {method.upper()!r}, "
            f"got {self.last_request.method!r}"
        )

    def assert_header_sent(self, header_name: str, expected_value: str) -> None:
        """Assert the last request sent a specific header value."""
        assert self.last_request is not None, "No requests have been sent"
        actual = self.last_request.headers.get(header_name)
        assert actual == expected_value, (
            f"Expected header {header_name!r}={expected_value!r}, got {actual!r}"
        )


@dataclass
class FakeAsyncTransport(AbstractAsyncTransport):
    """
    Deterministic asynchronous transport for async client tests (Phase 14).

    Same API as FakeTransport but with async send().
    """

    responses: list[ResponseEntry] = field(default_factory=list)
    default_response: TransportResponse | None = None
    call_delay_ms: float = 0.0

    requests: list[TransportRequest] = field(default_factory=list, init=False)
    call_count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._queue: deque[ResponseEntry] = deque(self.responses)

    async def send(self, request: TransportRequest) -> TransportResponse:
        """Async version of FakeTransport.send()."""
        self.requests.append(request)
        self.call_count += 1

        if self._queue:
            entry = self._queue.popleft()
        elif self.default_response is not None:
            entry = self.default_response
        else:
            raise RuntimeError(
                f"FakeAsyncTransport has no more scripted responses for: {request.url!r}"
            )

        if isinstance(entry, Exception):
            raise entry

        return TransportResponse(
            status_code=entry.status_code,
            headers=entry.headers,
            content=entry.content,
            request=request,
            elapsed_ms=entry.elapsed_ms + self.call_delay_ms,
        )

    async def close(self) -> None:
        """No-op."""
