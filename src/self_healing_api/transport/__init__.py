"""
transport — HTTP transport abstraction layer.
"""

from self_healing_api.transport.base import (
    AbstractAsyncTransport,
    AbstractTransport,
    TransportRequest,
    TransportResponse,
)
from self_healing_api.transport.fake_transport import (
    FakeAsyncTransport,
    FakeTransport,
    make_response,
)
from self_healing_api.transport.httpx_transport import (
    AsyncHttpxTransport,
    HTTPXAsyncTransport,
    HTTPXTransport,
    HttpxTransport,
)

__all__ = [
    # Abstract base
    "AbstractTransport",
    "AbstractAsyncTransport",
    # Value objects
    "TransportRequest",
    "TransportResponse",
    # Production transport
    "HttpxTransport",
    "AsyncHttpxTransport",
    "HTTPXTransport",
    "HTTPXAsyncTransport",
    # Test transport
    "FakeTransport",
    "FakeAsyncTransport",
    "make_response",
]
