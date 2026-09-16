"""
async_client.py — Asynchronous AsyncSelfHealingClient interface and pipeline orchestration.

Asynchronous counterpart to SelfHealingClient for asyncio applications.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from self_healing_api.circuit_breaker.breaker import CircuitBreaker
from self_healing_api.circuit_breaker.state import CircuitState
from self_healing_api.compatibility.engine import CompatibilityEngine
from self_healing_api.config.models import (
    CircuitBreakerConfig,
    ClientConfig,
    FallbackConfig,
    HealthConfig,
    IdempotencyConfig,
    ObservabilityConfig,
    RateLimitConfig,
    RetryConfig,
    RoutingConfig,
    TimeoutConfig,
)
from self_healing_api.config.validator import ConfigValidator
from self_healing_api.errors.exceptions import (
    CircuitOpenError,
    RetryExhaustedError,
)
from self_healing_api.fallback.handler import FallbackContext, FallbackHandler
from self_healing_api.health.health import HealthTracker
from self_healing_api.idempotency.guard import IdempotencyGuard
from self_healing_api.observability.manager import ObservabilityManager
from self_healing_api.rate_limit.handler import RateLimitHandler
from self_healing_api.retry.engine import RetryEngine
from self_healing_api.routing.router import HealthAwareRouter
from self_healing_api.timeout.policy import TimeoutPolicy
from self_healing_api.transport.base import (
    AbstractAsyncTransport,
    TransportRequest,
    TransportResponse,
)
from self_healing_api.transport.httpx_transport import HTTPXAsyncTransport
from self_healing_api.utils.clock import Clock, SystemClock
from self_healing_api.utils.ids import generate_request_id


class AsyncSelfHealingClient:
    """
    Asynchronous resilience client for asyncio HTTP requests.
    """

    def __init__(
        self,
        config: ClientConfig | None = None,
        *,
        base_url: str = "",
        endpoints: tuple[str, ...] | list[str] = (),
        timeout: TimeoutConfig | None = None,
        retry: RetryConfig | None = None,
        circuit_breaker: CircuitBreakerConfig | None = None,
        health: HealthConfig | None = None,
        routing: RoutingConfig | None = None,
        rate_limit: RateLimitConfig | None = None,
        fallback: FallbackConfig | None = None,
        observability: ObservabilityConfig | None = None,
        idempotency: IdempotencyConfig | None = None,
        default_headers: dict[str, str] | None = None,
        verify_ssl: bool = True,
        transport: AbstractAsyncTransport | None = None,
        clock: Clock | None = None,
    ) -> None:
        if config is None:
            config = ClientConfig(
                base_url=base_url,
                endpoints=tuple(endpoints),
                timeout=timeout or TimeoutConfig(),
                retry=retry or RetryConfig(),
                circuit_breaker=circuit_breaker or CircuitBreakerConfig(),
                health=health or HealthConfig(),
                routing=routing or RoutingConfig(),
                rate_limit=rate_limit or RateLimitConfig(),
                fallback=fallback or FallbackConfig(),
                observability=observability or ObservabilityConfig(),
                idempotency=idempotency or IdempotencyConfig(),
                default_headers=default_headers or {},
                verify_ssl=verify_ssl,
            )

        ConfigValidator().validate(config)
        self._config = config
        self._clock = clock or SystemClock()

        self._health_tracker = HealthTracker(config.health, clock=self._clock)
        urls = [config.base_url, *config.endpoints] if config.base_url else list(config.endpoints)
        self._router = HealthAwareRouter(config.routing, urls, self._health_tracker)
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        for url in urls:
            self._circuit_breakers[url] = CircuitBreaker(
                config.circuit_breaker, endpoint=url, clock=self._clock
            )

        self._retry_engine = RetryEngine(config.retry)
        self._fallback_handler = FallbackHandler(config.fallback)
        self._rate_limit_handler = RateLimitHandler(config.rate_limit)
        self._idempotency_guard = IdempotencyGuard(config.idempotency)
        self._observability = ObservabilityManager(config.observability)
        self.compatibility = CompatibilityEngine()

        self._transport: AbstractAsyncTransport = transport or HTTPXAsyncTransport(
            verify_ssl=config.verify_ssl,
        )

    def _get_breaker(self, endpoint: str) -> CircuitBreaker:
        if endpoint not in self._circuit_breakers:
            self._circuit_breakers[endpoint] = CircuitBreaker(
                self._config.circuit_breaker, endpoint=endpoint, clock=self._clock
            )
        return self._circuit_breakers[endpoint]

    async def _sleep(self, delay: float) -> None:
        if delay <= 0:
            return
        if hasattr(self._clock, "advance"):
            self._clock.advance(delay)
        else:
            await asyncio.sleep(delay)

    def _build_url(self, endpoint: str, path_or_url: str) -> str:
        if path_or_url.startswith("http"):
            return path_or_url
        return f"{endpoint.rstrip('/')}/{path_or_url.lstrip('/')}"

    def _failover_target(self, tried: set[str]) -> str | None:
        """Return the next healthy, non-open endpoint, or None if failover is exhausted."""
        if not self._config.routing.failover_enabled:
            return None
        for ep in self._router.endpoints:
            if ep in tried:
                continue
            if not self._health_tracker.is_healthy(ep):
                continue
            if self._get_breaker(ep).state == CircuitState.OPEN:
                continue
            return ep
        return None

    async def request(
        self,
        method: str,
        path_or_url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        json: Any = None,
        content: bytes | None = None,
        timeout: TimeoutConfig | None = None,
    ) -> TransportResponse:
        """
        Send asynchronous HTTP request through the resilience pipeline.
        """
        request_id = generate_request_id()
        timeout_cfg = timeout or self._config.timeout
        timeout_policy = TimeoutPolicy(timeout_cfg, clock=self._clock)
        timeout_policy.start()
        self._retry_engine.start()

        endpoint = self._router.select_endpoint()
        url = self._build_url(endpoint, path_or_url)
        breaker = self._get_breaker(endpoint)
        tried: set[str] = set()

        req_headers = dict(self._config.default_headers)
        if headers:
            req_headers.update(headers)

        attempt = 1
        last_exception: Exception | None = None

        while True:
            while attempt <= self._config.retry.max_attempts:
                timeout_policy.check_total_budget()

                try:
                    breaker.before_request(request_id=request_id)
                except CircuitOpenError as exc:
                    self._observability.log_circuit_open(endpoint)
                    tried.add(endpoint)
                    next_endpoint = self._failover_target(tried)
                    if next_endpoint is not None:
                        endpoint = next_endpoint
                        url = self._build_url(endpoint, path_or_url)
                        breaker = self._get_breaker(endpoint)
                        attempt = 1
                        self._retry_engine.start()
                        continue
                    return self._handle_fallback(endpoint, method, url, exc, attempt)

                req_headers = self._idempotency_guard.check_or_inject_key(
                    method, req_headers, attempt=attempt
                )

                req = TransportRequest(
                    method=method,
                    url=url,
                    headers=req_headers,
                    params=dict(params) if params else {},
                    json=json,
                    content=content,
                    timeout_connect=timeout_policy.connect_timeout,
                    timeout_read=timeout_policy.read_timeout,
                    request_id=request_id,
                )

                self._observability.log_request(req, attempt=attempt)

                span_attrs = {
                    "http.method": req.method,
                    "http.url": req.url,
                    "retry.attempt": attempt,
                    "request.id": request_id,
                }
                try:
                    span_name = f"HTTP {req.method}"
                    with self._observability.start_span(span_name, attributes=span_attrs):
                        response = await self._transport.send(req)

                    if response.status_code == 429:
                        rate_limit_delay = self._rate_limit_handler.process_rate_limit(response)
                        if rate_limit_delay is not None:
                            self._observability.log_retry(
                                req, attempt, rate_limit_delay, "HTTP 429 Rate Limited"
                            )
                            await self._sleep(rate_limit_delay)
                            attempt += 1
                            continue

                    decision = self._retry_engine.evaluate(
                        exc=ValueError(f"HTTP status {response.status_code}"),
                        attempt=attempt - 1,
                        http_status=response.status_code,
                        is_idempotent=self._idempotency_guard.is_idempotent_method(method),
                    )

                    if not decision.should_retry:
                        if response.is_success:
                            self._health_tracker.record_success(endpoint)
                            breaker.record_success()
                            self._fallback_handler.cache_response(
                                f"{method.upper()}:{url}", response
                            )
                            self._observability.log_response(req, response)
                            return response
                        self._health_tracker.record_failure(
                            endpoint, f"HTTP {response.status_code}"
                        )
                        breaker.record_failure()
                        response.raise_for_status()
                        return response

                    self._health_tracker.record_failure(
                        endpoint, f"HTTP {response.status_code}"
                    )
                    breaker.record_failure()
                    self._observability.log_retry(
                        req, attempt, decision.delay, decision.reason
                    )
                    await self._sleep(decision.delay)
                    attempt += 1

                except Exception as exc:
                    last_exception = exc
                    import httpx
                    if not isinstance(exc, (httpx.HTTPStatusError, ValueError)):
                        self._health_tracker.record_failure(endpoint, exc)
                        breaker.record_failure()

                    translated_exc = timeout_policy.translate(
                        exc, endpoint=endpoint, request_id=request_id
                    )
                    decision = self._retry_engine.evaluate(
                        exc=translated_exc,
                        attempt=attempt - 1,
                        is_idempotent=self._idempotency_guard.is_idempotent_method(method),
                    )

                    if not decision.should_retry:
                        exhausted = RetryExhaustedError(
                            f"Request failed after {attempt} attempt(s): {translated_exc}",
                            max_attempts=self._config.retry.max_attempts,
                            last_exception=translated_exc,
                            endpoint=endpoint,
                            request_id=request_id,
                        )
                        tried.add(endpoint)
                        next_endpoint = self._failover_target(tried)
                        if next_endpoint is not None:
                            endpoint = next_endpoint
                            url = self._build_url(endpoint, path_or_url)
                            breaker = self._get_breaker(endpoint)
                            last_exception = exhausted
                            attempt = 1
                            self._retry_engine.start()
                            continue
                        return self._handle_fallback(
                            endpoint, method, url, exhausted, attempt
                        )

                    self._observability.log_retry(
                        req, attempt, decision.delay, decision.reason
                    )
                    await self._sleep(decision.delay)
                    attempt += 1

            exhausted_err = RetryExhaustedError(
                f"All {self._config.retry.max_attempts} retry attempts exhausted.",
                max_attempts=self._config.retry.max_attempts,
                last_exception=last_exception,
                endpoint=endpoint,
                request_id=request_id,
            )
            tried.add(endpoint)
            next_endpoint = self._failover_target(tried)
            if next_endpoint is None:
                return self._handle_fallback(
                    endpoint, method, url, exhausted_err, attempt - 1
                )
            endpoint = next_endpoint
            url = self._build_url(endpoint, path_or_url)
            breaker = self._get_breaker(endpoint)
            attempt = 1
            self._retry_engine.start()

    def _handle_fallback(
        self,
        endpoint: str,
        method: str,
        url: str,
        error: Exception,
        attempt_count: int,
    ) -> TransportResponse:
        ctx = FallbackContext(
            endpoint=endpoint,
            method=method,
            url=url,
            error=error,
            attempt_count=attempt_count,
        )
        return self._fallback_handler.execute_fallback(ctx, route_key=f"{method.upper()}:{url}")

    async def get(self, path_or_url: str, **kwargs: Any) -> TransportResponse:
        """Send asynchronous GET request."""
        return await self.request("GET", path_or_url, **kwargs)

    async def post(self, path_or_url: str, **kwargs: Any) -> TransportResponse:
        """Send asynchronous POST request."""
        return await self.request("POST", path_or_url, **kwargs)

    async def put(self, path_or_url: str, **kwargs: Any) -> TransportResponse:
        """Send asynchronous PUT request."""
        return await self.request("PUT", path_or_url, **kwargs)

    async def delete(self, path_or_url: str, **kwargs: Any) -> TransportResponse:
        """Send asynchronous DELETE request."""
        return await self.request("DELETE", path_or_url, **kwargs)

    async def patch(self, path_or_url: str, **kwargs: Any) -> TransportResponse:
        """Send asynchronous PATCH request."""
        return await self.request("PATCH", path_or_url, **kwargs)

    async def aclose(self) -> None:
        """Release underlying async transport connections."""
        await self._transport.close()

    async def __aenter__(self) -> AsyncSelfHealingClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()
