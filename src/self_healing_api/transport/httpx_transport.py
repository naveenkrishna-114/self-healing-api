"""
httpx_transport.py — Production HTTP transport backed by httpx.

httpx is the only required runtime dependency of this package.
It provides both sync and async clients with consistent APIs,
fine-grained timeout controls, and a clean transport abstraction
that maps well to AbstractTransport.

Both HttpxTransport (sync) and AsyncHttpxTransport (async) are
thin wrappers. They translate between our TransportRequest /
TransportResponse value objects and httpx's internal types.

No resilience logic lives here — only raw HTTP I/O.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from self_healing_api.transport.base import (
    AbstractAsyncTransport,
    AbstractTransport,
    TransportRequest,
    TransportResponse,
)


def _build_httpx_timeout(request: TransportRequest) -> httpx.Timeout:
    """Convert our timeout fields to an httpx.Timeout object."""
    return httpx.Timeout(
        connect=request.timeout_connect,
        read=request.timeout_read,
        write=request.timeout_read,   # use read timeout for writes
        pool=request.timeout_connect,
    )


def _build_response(
    httpx_response: httpx.Response,
    request: TransportRequest,
    elapsed_ms: float,
) -> TransportResponse:
    """Convert an httpx.Response to our TransportResponse."""
    return TransportResponse(
        status_code=httpx_response.status_code,
        headers=dict(httpx_response.headers),
        content=httpx_response.content,
        request=request,
        elapsed_ms=elapsed_ms,
    )


class HttpxTransport(AbstractTransport):
    """
    Synchronous HTTP transport using httpx.Client.

    A single httpx.Client instance is reused across requests for
    connection pooling efficiency.

    Parameters
    ----------
    verify_ssl : bool
        Whether to verify TLS certificates. Must be True in production.
        Default: True.
    default_headers : dict[str, str]
        Headers added to every request at the transport level.
    limits : httpx.Limits | None
        Connection pool limits. Defaults to httpx defaults.

    Example
    -------
    ::

        transport = HttpxTransport(verify_ssl=True)
        with transport:
            response = transport.send(request)
    """

    def __init__(
        self,
        verify_ssl: bool = True,
        default_headers: dict[str, str] | None = None,
        limits: Any | None = None,
        base_url: str = "",
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            verify=verify_ssl,
            headers=default_headers or {},
            limits=limits or httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=30.0,
            ),
            follow_redirects=True,
        )

    def send(self, request: TransportRequest) -> TransportResponse:
        """
        Send a synchronous HTTP request.

        Parameters
        ----------
        request : TransportRequest
            The request to send.

        Returns
        -------
        TransportResponse
            The HTTP response (never raises for HTTP error status codes —
            the resilience pipeline calls raise_for_status() when needed).

        Raises
        ------
        httpx.ConnectTimeout
            If the connection timeout is exceeded.
        httpx.ReadTimeout
            If the read timeout is exceeded.
        httpx.ConnectError
            If the connection cannot be established.
        httpx.NetworkError
            For other network-level failures.
        """
        timeout = _build_httpx_timeout(request)
        start = time.monotonic()

        httpx_response = self._client.request(
            method=request.method,
            url=request.url,
            headers=request.headers,
            params=request.params or None,
            json=request.json,
            content=request.content,
            timeout=timeout,
        )

        elapsed_ms = (time.monotonic() - start) * 1000
        return _build_response(httpx_response, request, elapsed_ms)

    def close(self) -> None:
        """Close the underlying httpx.Client and release connections."""
        self._client.close()


class AsyncHttpxTransport(AbstractAsyncTransport):
    """
    Asynchronous HTTP transport using httpx.AsyncClient.

    Used by AsyncSelfHealingClient (Phase 14).

    Parameters
    ----------
    verify_ssl : bool
        Whether to verify TLS certificates. Default: True.
    default_headers : dict[str, str]
        Headers added to every request at the transport level.
    limits : httpx.Limits | None
        Connection pool limits.
    """

    def __init__(
        self,
        verify_ssl: bool = True,
        default_headers: dict[str, str] | None = None,
        limits: Any | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            verify=verify_ssl,
            headers=default_headers or {},
            limits=limits or httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=30.0,
            ),
            follow_redirects=True,
        )

    async def send(self, request: TransportRequest) -> TransportResponse:
        """
        Send an asynchronous HTTP request.

        Same semantics as HttpxTransport.send() but non-blocking.
        """
        timeout = _build_httpx_timeout(request)
        start = time.monotonic()

        httpx_response = await self._client.request(
            method=request.method,
            url=request.url,
            headers=request.headers,
            params=request.params or None,
            json=request.json,
            content=request.content,
            timeout=timeout,
        )

        elapsed_ms = (time.monotonic() - start) * 1000
        return _build_response(httpx_response, request, elapsed_ms)

    async def close(self) -> None:
        """Close the underlying httpx.AsyncClient."""
        await self._client.aclose()


# Aliases for consistent naming
HTTPXTransport = HttpxTransport
HTTPXAsyncTransport = AsyncHttpxTransport

