"""
manager.py — Observability manager providing logging, metrics, tracing, and event hooks.

Integrates credential masking via SecretMasker and optional Prometheus/OpenTelemetry
instrumentation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from self_healing_api.config.models import ObservabilityConfig
from self_healing_api.transport.base import TransportRequest, TransportResponse
from self_healing_api.utils.masking import SecretMasker

logger = logging.getLogger("self_healing_api")


class ObservabilityManager:
    """
    Central manager for logs, metrics, tracing, and custom event listeners.

    Parameters
    ----------
    config : ObservabilityConfig
    """

    def __init__(self, config: ObservabilityConfig) -> None:
        self._config = config
        self._masker = SecretMasker(
            masked_headers=config.mask_headers,
            masked_body_fields=config.mask_body_fields,
        )
        self._listeners: dict[str, list[Callable[..., None]]] = {
            "on_request": [],
            "on_retry": [],
            "on_circuit_open": [],
            "on_fallback": [],
            "on_error": [],
        }

        # Optional Prometheus metric handles
        self._prometheus_counter: Any = None
        self._prometheus_histogram: Any = None
        if config.metrics_enabled:
            self._init_prometheus()

        # Optional OpenTelemetry tracer handle
        self._tracer: Any = None
        if config.tracing_enabled:
            self._init_opentelemetry()

    def _init_prometheus(self) -> None:
        """Initialize Prometheus metrics if prometheus_client package is installed."""
        try:
            from importlib import import_module

            prometheus_client = import_module("prometheus_client")
            Counter = prometheus_client.Counter
            Histogram = prometheus_client.Histogram

            self._prometheus_counter = Counter(
                "self_healing_api_requests_total",
                "Total HTTP requests sent by self-healing API client",
                ["method", "endpoint", "status_code"],
            )
            self._prometheus_histogram = Histogram(
                "self_healing_api_request_duration_seconds",
                "HTTP request duration in seconds",
                ["method", "endpoint"],
            )
        except ImportError:
            logger.debug("prometheus_client package not installed; metrics disabled.")

    def _init_opentelemetry(self) -> None:
        """Initialize OpenTelemetry tracer if opentelemetry package is installed."""
        try:
            from importlib import import_module

            trace = import_module("opentelemetry.trace")

            self._tracer = trace.get_tracer("self_healing_api")
        except ImportError:
            logger.debug("opentelemetry package not installed; tracing disabled.")

    def add_listener(self, event_name: str, callback: Callable[..., None]) -> None:
        """Register a custom listener callback for resilience events."""
        if event_name in self._listeners:
            self._listeners[event_name].append(callback)

    def log_request(self, request: TransportRequest, attempt: int = 1) -> None:
        """Log outgoing request details with credentials redacted."""
        masked_headers = self._masker.mask_headers(request.headers)
        masked_url = self._masker.mask_url(request.url)
        logger.debug(
            "Sending HTTP %s request to %s (attempt %d) headers=%s",
            request.method,
            masked_url,
            attempt,
            masked_headers,
        )
        for cb in self._listeners["on_request"]:
            try:
                cb(request, attempt)
            except Exception as exc:
                logger.warning("Error in on_request event listener: %s", exc)

    def log_retry(
        self, request: TransportRequest, attempt: int, delay: float, reason: Exception | str
    ) -> None:
        """Log retry attempt with delay and cause."""
        masked_url = self._masker.mask_url(request.url)
        logger.info(
            "Retrying HTTP %s request to %s (attempt %d) after %.2fs delay. Reason: %s",
            request.method,
            masked_url,
            attempt,
            delay,
            reason,
        )
        for cb in self._listeners["on_retry"]:
            try:
                cb(request, attempt, delay, reason)
            except Exception as exc:
                logger.warning("Error in on_retry event listener: %s", exc)

    def log_circuit_open(self, endpoint: str) -> None:
        """Log circuit breaker OPEN state transition."""
        logger.warning("Circuit breaker opened for endpoint: %s", endpoint)
        for cb in self._listeners["on_circuit_open"]:
            try:
                cb(endpoint)
            except Exception as exc:
                logger.warning("Error in on_circuit_open event listener: %s", exc)

    def log_response(self, request: TransportRequest, response: TransportResponse) -> None:
        """Record response metrics and observability logs."""
        masked_url = self._masker.mask_url(request.url)
        logger.debug(
            "Received HTTP %d response for %s %s in %.1fms",
            response.status_code,
            request.method,
            masked_url,
            response.elapsed_ms,
        )
        if self._prometheus_counter is not None:
            try:
                self._prometheus_counter.labels(
                    method=request.method,
                    endpoint=request.url,
                    status_code=str(response.status_code),
                ).inc()
            except Exception:
                pass

    def start_span(self, name: str, attributes: dict[str, Any] | None = None) -> Any:
        """
        Start an OpenTelemetry span context if tracing is enabled,
        otherwise return a no-op context manager.
        """
        if self._tracer is not None:
            try:
                return self._tracer.start_as_current_span(name, attributes=attributes or {})
            except Exception as exc:
                logger.debug("Failed to start OpenTelemetry span: %s", exc)

        import contextlib
        from collections.abc import Iterator

        @contextlib.contextmanager
        def _noop_span() -> Iterator[None]:
            yield None

        return _noop_span()
