"""
base.py — Abstract HTTP transport interface.

The SelfHealingClient never calls httpx (or any HTTP library) directly.
It always goes through an AbstractTransport. This indirection gives us:

1. Testability   — FakeTransport returns scripted responses with no network.
2. Replaceability — swap httpx for another library without touching resilience logic.
3. Clean boundaries — transport concerns (connection pooling, TLS) stay isolated.

Both sync and async variants are defined here so the client can support
both execution modes with the same resilience pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

# ── Request / Response value objects ─────────────────────────────────────────

@dataclass
class TransportRequest:
    """
    A transport-layer HTTP request.

    Constructed by SelfHealingClient and passed to the transport.
    All headers must already be assembled (auth, idempotency key, etc.)
    before creating a TransportRequest.

    Parameters
    ----------
    method : str
        HTTP method in uppercase (GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS).
    url : str
        Full URL including scheme, host, path and query string.
    headers : dict[str, str]
        HTTP request headers.
    params : dict[str, str]
        URL query parameters to append (merged into the URL by the transport).
    json : Any
        Python object to be serialised as the JSON request body.
        Mutually exclusive with ``content``.
    content : bytes | None
        Raw request body bytes. Mutually exclusive with ``json``.
    timeout_connect : float
        Connection timeout in seconds.
    timeout_read : float
        Read timeout in seconds.
    request_id : str
        Unique request identifier for tracing.
    """

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    json: Any = None
    content: bytes | None = None
    timeout_connect: float = 5.0
    timeout_read: float = 30.0
    request_id: str = ""

    def __post_init__(self) -> None:
        self.method = self.method.upper()


@dataclass
class TransportResponse:
    """
    A transport-layer HTTP response.

    Returned by the transport to the resilience pipeline.

    Parameters
    ----------
    status_code : int
        HTTP response status code.
    headers : dict[str, str]
        HTTP response headers (lowercase keys preferred).
    content : bytes
        Raw response body bytes.
    request : TransportRequest
        The originating request (for logging and error context).
    elapsed_ms : float
        Time taken for the request in milliseconds.
    """

    status_code: int
    headers: dict[str, str]
    content: bytes
    request: TransportRequest
    elapsed_ms: float = 0.0
    degraded: bool = False

    def json(self) -> Any:
        """
        Parse the response body as JSON.

        Returns
        -------
        Any
            Parsed JSON value.

        Raises
        ------
        ValueError
            If the body is not valid JSON.
        """
        import json as _json

        return _json.loads(self.content)

    def text(self, encoding: str = "utf-8") -> str:
        """Decode the response body as text."""
        return self.content.decode(encoding)

    @property
    def is_success(self) -> bool:
        """Return True for 2xx status codes."""
        return 200 <= self.status_code < 300

    @property
    def is_client_error(self) -> bool:
        """Return True for 4xx status codes."""
        return 400 <= self.status_code < 500

    @property
    def is_server_error(self) -> bool:
        """Return True for 5xx status codes."""
        return 500 <= self.status_code < 600

    def raise_for_status(self) -> None:
        """
        Raise an httpx-compatible HTTPStatusError for non-2xx responses.

        The resilience pipeline calls this to normalise HTTP errors into
        exceptions that the ErrorClassifier can handle.
        """
        if not self.is_success:
            url = self.request.url or "https://placeholder.local/"
            method = self.request.method or "GET"
            try:
                import httpx

                # Attach a Request so httpx.Response.raise_for_status() works
                # on synthetic FakeTransport responses as well as live ones.
                httpx_request = httpx.Request(method, url)
                httpx_response = httpx.Response(
                    status_code=self.status_code,
                    headers=list(self.headers.items()),
                    content=self.content,
                    request=httpx_request,
                )
                httpx_response.raise_for_status()
            except ImportError:
                # httpx not available — raise a plain ValueError instead
                msg = f"HTTP {self.status_code} error for URL: {url!r}"
                raise ValueError(msg) from None

    def __repr__(self) -> str:
        return (
            f"TransportResponse(status_code={self.status_code}, "
            f"url={self.request.url!r}, "
            f"elapsed_ms={self.elapsed_ms:.1f})"
        )


# ── Abstract sync transport ───────────────────────────────────────────────────

class AbstractTransport(ABC):
    """
    Abstract base class for synchronous HTTP transports.

    Subclass this to implement a concrete transport (httpx, requests, etc.)
    or to create a FakeTransport for testing.

    The transport is responsible ONLY for sending HTTP requests and
    returning responses. All resilience logic (retry, circuit breaking,
    timeout policy) lives in the client pipeline, not here.
    """

    @abstractmethod
    def send(self, request: TransportRequest) -> TransportResponse:
        """
        Send an HTTP request and return the response.

        Parameters
        ----------
        request : TransportRequest
            The request to send.

        Returns
        -------
        TransportResponse
            The HTTP response.

        Raises
        ------
        httpx.TimeoutException | ConnectTimeoutError | ReadTimeoutError
            On timeout.
        httpx.NetworkError | ConnectionError
            On network-level failures.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Release underlying resources (connection pool, sockets)."""
        ...

    def __enter__(self) -> AbstractTransport:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


# ── Abstract async transport ──────────────────────────────────────────────────

class AbstractAsyncTransport(ABC):
    """
    Abstract base class for asynchronous HTTP transports.

    Mirror of AbstractTransport for the async client path.
    """

    @abstractmethod
    async def send(self, request: TransportRequest) -> TransportResponse:
        """Send an HTTP request asynchronously and return the response."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Release underlying async resources."""
        ...

    async def __aenter__(self) -> AbstractAsyncTransport:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
