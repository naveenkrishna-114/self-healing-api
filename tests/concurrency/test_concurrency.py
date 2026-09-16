"""Concurrency tests verifying thread and async safety."""

import concurrent.futures

import pytest

from self_healing_api.client import SelfHealingClient
from self_healing_api.transport.fake_transport import FakeTransport, make_response


@pytest.mark.concurrency
class TestConcurrencySafety:
    def test_multithreaded_client_requests(self) -> None:
        """Verify thread-safe execution across 10 concurrent threads."""
        transport = FakeTransport(default_response=make_response(200, json_body={"ok": True}))
        client = SelfHealingClient(
            base_url="https://api.example.com",
            transport=transport,
        )

        def make_call(i: int) -> int:
            res = client.get(f"/item/{i}")
            return res.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(make_call, range(20)))

        assert results == [200] * 20
        assert len(transport.requests) == 20
