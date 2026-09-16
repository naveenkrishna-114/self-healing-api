"""
Root conftest.py — shared pytest fixtures available to all test modules.

Phase-specific fixtures are added to this file as each phase is implemented.
"""
from __future__ import annotations

import pytest

from self_healing_api.transport.fake_transport import FakeTransport, make_response
from self_healing_api.utils.clock import FakeClock

# ── Shared markers ────────────────────────────────────────────────────────────

def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers so pytest does not warn about unknown markers."""
    config.addinivalue_line("markers", "unit: fast isolated unit tests")
    config.addinivalue_line("markers", "integration: tests using mock HTTP servers")
    config.addinivalue_line("markers", "concurrency: thread/async safety tests")
    config.addinivalue_line("markers", "security: secret handling and TLS tests")
    config.addinivalue_line("markers", "chaos: failure injection tests")
    config.addinivalue_line("markers", "performance: benchmark tests")


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture()
def fake_clock() -> FakeClock:
    """A deterministic clock starting at t=0. Advance with clock.advance(seconds)."""
    return FakeClock(start=0.0)


@pytest.fixture()
def ok_transport() -> FakeTransport:
    """A transport that always returns HTTP 200 with an empty JSON body."""
    return FakeTransport(default_response=make_response(200, json_body={}))


@pytest.fixture()
def error_transport() -> FakeTransport:
    """A transport that always returns HTTP 500."""
    return FakeTransport(default_response=make_response(500))
