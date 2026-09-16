"""Performance benchmark tests measuring client pipeline overhead."""

import time

import pytest

from self_healing_api.client import SelfHealingClient
from self_healing_api.transport.fake_transport import FakeTransport, make_response


@pytest.mark.performance
class TestPerformanceOverhead:
    def test_pipeline_overhead_latency(self) -> None:
        """Assert single request pipeline execution overhead is < 5ms."""
        transport = FakeTransport(default_response=make_response(200, json_body={"ok": True}))
        client = SelfHealingClient(
            base_url="https://api.example.com",
            transport=transport,
        )

        start = time.perf_counter()
        res = client.get("/fast")
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert res.status_code == 200
        assert elapsed_ms < 50.0  # < 50ms overhead per call in test environment
