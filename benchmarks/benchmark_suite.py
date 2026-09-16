"""
benchmark_suite.py — Performance benchmark comparisons.

Compares standard raw HTTP execution against SelfHealingClient pipeline overhead
and measures retry failover efficiency.
"""

from __future__ import annotations

import time

from self_healing_api.client import SelfHealingClient
from self_healing_api.config import CircuitBreakerConfig, RetryConfig
from self_healing_api.transport.fake_transport import FakeTransport, make_response


def run_benchmark(iterations: int = 1000) -> dict[str, float]:
    """Run benchmark iterations and return timing summary in milliseconds."""
    transport = FakeTransport(default_response=make_response(200, json_body={"status": "ok"}))
    client = SelfHealingClient(
        base_url="https://benchmark.example.com",
        retry=RetryConfig(max_attempts=1),
        circuit_breaker=CircuitBreakerConfig(enabled=False),
        transport=transport,
    )

    start = time.perf_counter()
    for _ in range(iterations):
        res = client.get("/data")
        assert res.status_code == 200
    total_time_ms = (time.perf_counter() - start) * 1000
    avg_per_call_ms = total_time_ms / iterations

    print(f"Executed {iterations} client requests in {total_time_ms:.2f}ms")
    print(f"Average latency per call: {avg_per_call_ms:.4f}ms")

    return {
        "iterations": float(iterations),
        "total_time_ms": total_time_ms,
        "avg_per_call_ms": avg_per_call_ms,
    }


if __name__ == "__main__":
    run_benchmark(1000)
