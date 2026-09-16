"""
handler.py — Explicit developer-configured fallback handler.

Supports developer custom handler callables, last-known-good response caching,
and static responses.
"""

from __future__ import annotations

import inspect
import threading
from dataclasses import dataclass

from self_healing_api.config.models import FallbackConfig
from self_healing_api.errors.exceptions import FallbackError
from self_healing_api.transport.base import TransportResponse
from self_healing_api.transport.fake_transport import make_response


@dataclass
class FallbackContext:
    """Context object passed to custom developer fallback handler callables."""

    endpoint: str
    method: str
    url: str
    error: Exception
    attempt_count: int


class FallbackHandler:
    """
    Evaluates fallback options when request retries/recovery are exhausted.

    Parameters
    ----------
    config : FallbackConfig
    """

    def __init__(self, config: FallbackConfig) -> None:
        self._config = config
        self._cache: dict[str, TransportResponse] = {}
        self._lock = threading.Lock()

    def cache_response(self, route_key: str, response: TransportResponse) -> None:
        """Cache a successful 2xx response if cache_last_success is enabled."""
        if not self._config.cache_last_success or not response.is_success:
            return
        with self._lock:
            self._cache[route_key] = response

    def execute_fallback(
        self, context: FallbackContext, route_key: str = ""
    ) -> TransportResponse:
        """
        Execute configured fallback strategy.

        Returns
        -------
        TransportResponse
            Fallback response.

        Raises
        ------
        FallbackError
            If fallback handler itself fails.
        Exception
            Re-raises original_error if no fallback strategy is enabled.
        """
        # Strategy 1: Custom callable handler
        if self._config.handler is not None:
            try:
                sig = inspect.signature(self._config.handler)
                if len(sig.parameters) == 0:
                    res = self._config.handler()
                else:
                    res = self._config.handler(context)

                if isinstance(res, TransportResponse):
                    res.degraded = True
                    return res
                elif isinstance(res, (dict, list)):
                    headers = {
                        "content-type": "application/json",
                        "x-self-healing-fallback": "true",
                    }
                    return make_response(
                        status_code=200,
                        json_body=res,
                        headers=headers,
                        degraded=True,
                    )
                elif isinstance(res, (str, bytes)):
                    body_bytes = res if isinstance(res, bytes) else res.encode("utf-8")
                    return make_response(
                        status_code=200,
                        body=body_bytes,
                        headers={"x-self-healing-fallback": "true"},
                        degraded=True,
                    )
                elif res is not None:
                    return make_response(
                        status_code=200,
                        body=str(res).encode("utf-8"),
                        headers={"x-self-healing-fallback": "true"},
                        degraded=True,
                    )
            except Exception as exc:
                if isinstance(exc, FallbackError):
                    raise
                raise FallbackError(
                    f"Fallback handler raised exception: {exc}",
                    original_error=context.error,
                    fallback_error=exc,
                    endpoint=context.endpoint,
                ) from exc

        # Strategy 2: Cached last successful response
        if self._config.cache_last_success:
            key = route_key or f"{context.method}:{context.url}"
            with self._lock:
                cached = self._cache.get(key)
                if cached is not None:
                    headers = dict(cached.headers)
                    headers["x-self-healing-stale"] = "true"
                    return make_response(
                        status_code=cached.status_code,
                        headers=headers,
                        body=cached.content,
                        elapsed_ms=cached.elapsed_ms,
                        degraded=True,
                    )

        # Strategy 3: Static fallback response
        if self._config.static_response is not None:
            static_val = self._config.static_response
            if isinstance(static_val, TransportResponse):
                static_val.degraded = True
                return static_val
            if isinstance(static_val, (dict, list)):
                return make_response(
                    status_code=200,
                    json_body=static_val,
                    headers={"content-type": "application/json", "x-self-healing-fallback": "true"},
                    degraded=True,
                )
            body_bytes = (
                static_val
                if isinstance(static_val, bytes)
                else str(static_val).encode("utf-8")
            )
            return make_response(
                status_code=200,
                headers={"x-self-healing-fallback": "true"},
                body=body_bytes,
                degraded=True,
            )

        # No fallback handled — re-raise original error
        raise context.error
