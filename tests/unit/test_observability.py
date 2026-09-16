"""Unit tests for ObservabilityManager."""

import pytest

from self_healing_api.config.models import ObservabilityConfig
from self_healing_api.observability import ObservabilityManager
from self_healing_api.transport.base import TransportRequest
from self_healing_api.transport.fake_transport import make_response


@pytest.mark.unit
class TestObservabilityManager:
    def test_log_request_and_event_listener(self) -> None:
        mgr = ObservabilityManager(ObservabilityConfig())
        events = []

        def listener(req: TransportRequest, attempt: int) -> None:
            events.append((req.method, attempt))

        mgr.add_listener("on_request", listener)
        req = TransportRequest(method="GET", url="https://api.example.com/data")
        mgr.log_request(req, attempt=1)

        assert len(events) == 1
        assert events[0] == ("GET", 1)

    def test_log_retry_listener(self) -> None:
        mgr = ObservabilityManager(ObservabilityConfig())
        retries = []

        def listener(req: TransportRequest, attempt: int, delay: float, reason: str) -> None:
            retries.append((attempt, delay, str(reason)))

        mgr.add_listener("on_retry", listener)
        req = TransportRequest(method="POST", url="https://api.example.com/data")
        mgr.log_retry(req, attempt=2, delay=1.5, reason="HTTP 500")

        assert len(retries) == 1
        assert retries[0] == (2, 1.5, "HTTP 500")

    def test_log_response_does_not_raise(self) -> None:
        mgr = ObservabilityManager(ObservabilityConfig(metrics_enabled=True))
        req = TransportRequest(method="GET", url="https://api.example.com/data")
        res = make_response(200)
        mgr.log_response(req, res)  # must not raise even if optional packages missing

    def test_start_span_context_manager(self) -> None:
        mgr = ObservabilityManager(ObservabilityConfig(tracing_enabled=True))
        with mgr.start_span("HTTP GET", attributes={"http.method": "GET"}):
            pass

    def test_circuit_open_listener_and_exception_handling(self) -> None:
        mgr = ObservabilityManager(ObservabilityConfig())
        opened = []

        def broken_listener(ep: str) -> None:
            raise RuntimeError("Boom")

        def good_listener(ep: str) -> None:
            opened.append(ep)

        mgr.add_listener("on_circuit_open", broken_listener)
        mgr.add_listener("on_circuit_open", good_listener)
        mgr.log_circuit_open("https://broken.com")

        assert opened == ["https://broken.com"]

    def test_unknown_event_listener_ignored(self) -> None:
        mgr = ObservabilityManager(ObservabilityConfig())
        mgr.add_listener("nonexistent_event", lambda: None)

    def test_listener_exceptions_swallowed(self) -> None:
        mgr = ObservabilityManager(ObservabilityConfig())

        def broken(*args: object, **kwargs: object) -> None:
            raise RuntimeError("listener failure")

        mgr.add_listener("on_request", broken)
        mgr.add_listener("on_retry", broken)
        req = TransportRequest(method="GET", url="https://api.com")
        mgr.log_request(req)
        mgr.log_retry(req, 1, 1.0, "reason")

    def test_prometheus_integration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys
        from unittest.mock import MagicMock

        mock_prom = MagicMock()
        monkeypatch.setitem(sys.modules, "prometheus_client", mock_prom)
        mgr = ObservabilityManager(ObservabilityConfig(metrics_enabled=True))
        assert mgr._prometheus_counter is not None

        req = TransportRequest(method="GET", url="https://api.com")
        res = make_response(200)
        mgr.log_response(req, res)

        # Exception branch in prometheus counter inc
        mgr._prometheus_counter.labels.return_value.inc.side_effect = RuntimeError("prom err")
        mgr.log_response(req, res)

    def test_opentelemetry_integration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys
        from unittest.mock import MagicMock

        mock_trace = MagicMock()
        monkeypatch.setitem(sys.modules, "opentelemetry", MagicMock())
        monkeypatch.setitem(sys.modules, "opentelemetry.trace", mock_trace)

        mgr = ObservabilityManager(ObservabilityConfig(tracing_enabled=True))
        assert mgr._tracer is not None
        mgr.start_span("test_span")

        # Exception branch in start_as_current_span
        mgr._tracer.start_as_current_span.side_effect = RuntimeError("span err")
        mgr.start_span("test_span_err")
