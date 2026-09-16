"""
benchmarks/run_comprehensive_benchmarks.py

Comprehensive performance benchmarking suite for self-healing-api:
1. Pure Pipeline Latency Overhead vs Raw Transport
2. Latency Distribution & Percentiles (P50, P90, P95, P99, P99.9)
3. Circuit Breaker Fast-Fail Rejection Latency
4. Asynchronous High-Concurrency Throughput (RPS)
5. Multi-Threaded Sync Client Contention & Throughput
6. Memory Allocation & Heap Profile (tracemalloc)
7. Fallback Routing Execution Latency
"""

from __future__ import annotations

import asyncio
import gc
import logging
import statistics
import threading
import time
import tracemalloc
from typing import Any

logging.disable(logging.CRITICAL)

from self_healing_api.client import AsyncSelfHealingClient, SelfHealingClient
from self_healing_api.config import (
    CircuitBreakerConfig,
    FallbackConfig,
    HealthConfig,
    RateLimitConfig,
    RetryConfig,
)
from self_healing_api.errors.exceptions import CircuitOpenError
from self_healing_api.transport.fake_transport import (
    FakeAsyncTransport,
    FakeTransport,
    make_response,
)


def benchmark_pipeline_overhead(iterations: int = 5000) -> dict[str, Any]:
    """Compare raw transport vs SelfHealingClient to calculate net overhead."""
    ok_resp = make_response(200, json_body={"status": "ok"})
    raw_transport = FakeTransport(default_response=ok_resp)

    from self_healing_api.transport.base import TransportRequest
    req = TransportRequest(method="GET", url="https://benchmark.example.com/data")

    # 1. Raw transport time
    start_raw = time.perf_counter()
    for _ in range(iterations):
        resp = raw_transport.send(req)
        assert resp.status_code == 200
    raw_total_ms = (time.perf_counter() - start_raw) * 1000
    raw_avg_ms = raw_total_ms / iterations

    # 2. SelfHealingClient full pipeline (with Breaker, Rate Limit, Retry logic active)
    client_transport = FakeTransport(default_response=ok_resp)
    client = SelfHealingClient(
        base_url="https://benchmark.example.com",
        retry=RetryConfig(max_attempts=3),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=5),
        rate_limit=RateLimitConfig(respect_retry_after=True),
        transport=client_transport,
    )

    latencies: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        resp = client.get("/data")
        t1 = time.perf_counter()
        assert resp.status_code == 200
        latencies.append((t1 - t0) * 1000)

    total_client_ms = sum(latencies)
    avg_client_ms = total_client_ms / iterations
    net_overhead_ms = avg_client_ms - raw_avg_ms

    latencies.sort()
    p50 = latencies[int(iterations * 0.50)]
    p90 = latencies[int(iterations * 0.90)]
    p95 = latencies[int(iterations * 0.95)]
    p99 = latencies[int(iterations * 0.99)]
    p999 = latencies[int(iterations * 0.999)]

    return {
        "iterations": iterations,
        "raw_avg_ms": raw_avg_ms,
        "client_avg_ms": avg_client_ms,
        "net_overhead_ms": net_overhead_ms,
        "min_ms": latencies[0],
        "max_ms": latencies[-1],
        "p50_ms": p50,
        "p90_ms": p90,
        "p95_ms": p95,
        "p99_ms": p99,
        "p999_ms": p999,
        "std_dev_ms": statistics.stdev(latencies),
    }


def benchmark_circuit_breaker_fast_fail(iterations: int = 5000) -> dict[str, Any]:
    """Measure how fast an OPEN circuit breaker rejects requests without hitting the network."""
    client_transport = FakeTransport(default_response=make_response(500))
    client = SelfHealingClient(
        base_url="https://benchmark.example.com",
        retry=RetryConfig(max_attempts=1),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=2, recovery_timeout=60.0),
        transport=client_transport,
    )

    # Trip breaker into OPEN state
    for _ in range(2):
        try:
            client.get("/fail")
        except Exception:
            pass

    latencies: list[float] = []
    rejected = 0
    start = time.perf_counter()
    for _ in range(iterations):
        t0 = time.perf_counter()
        try:
            client.get("/fail")
        except CircuitOpenError:
            rejected += 1
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000)

    total_ms = (time.perf_counter() - start) * 1000
    avg_rejection_ms = total_ms / iterations

    return {
        "iterations": iterations,
        "rejected": rejected,
        "total_ms": total_ms,
        "avg_rejection_ms": avg_rejection_ms,
        "p99_rejection_ms": sorted(latencies)[int(iterations * 0.99)],
        "rejections_per_sec": int(iterations / (total_ms / 1000)),
    }


async def _async_worker(client: AsyncSelfHealingClient, count: int) -> list[float]:
    times: list[float] = []
    for _ in range(count):
        t0 = time.perf_counter()
        resp = await client.get("/async-data")
        t1 = time.perf_counter()
        assert resp.status_code == 200
        times.append((t1 - t0) * 1000)
    return times


def benchmark_async_throughput(total_requests: int = 5000, concurrency: int = 50) -> dict[str, Any]:
    """Measure asynchronous concurrency throughput and RPS."""
    async def runner() -> tuple[float, list[float]]:
        transport = FakeAsyncTransport(
            default_response=make_response(200, json_body={"status": "ok"})
        )
        client = AsyncSelfHealingClient(
            base_url="https://async.benchmark.example.com",
            retry=RetryConfig(max_attempts=1),
            transport=transport,
        )
        reqs_per_coro = total_requests // concurrency
        start = time.perf_counter()
        tasks = [_async_worker(client, reqs_per_coro) for _ in range(concurrency)]
        results = await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start
        all_times: list[float] = []
        for r in results:
            all_times.extend(r)
        return total_time, all_times

    total_time, all_times = asyncio.run(runner())
    rps = len(all_times) / total_time
    avg_latency = (total_time * 1000) / len(all_times)

    return {
        "total_requests": len(all_times),
        "concurrency": concurrency,
        "total_time_s": total_time,
        "requests_per_second": rps,
        "avg_latency_ms": avg_latency,
        "p99_latency_ms": sorted(all_times)[int(len(all_times) * 0.99)],
    }


def benchmark_multithreaded_contention(
    threads_count: int = 10, requests_per_thread: int = 500
) -> dict[str, Any]:
    """Measure thread safety and lock contention across multiple threads."""
    client = SelfHealingClient(
        base_url="https://thread.benchmark.example.com",
        retry=RetryConfig(max_attempts=1),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=100),
        transport=FakeTransport(default_response=make_response(200)),
    )

    errors = 0
    lock = threading.Lock()

    def worker() -> None:
        nonlocal errors
        for _ in range(requests_per_thread):
            try:
                r = client.get("/thread-data")
                if r.status_code != 200:
                    with lock:
                        errors += 1
            except Exception:
                with lock:
                    errors += 1

    threads = [threading.Thread(target=worker) for _ in range(threads_count)]
    total_reqs = threads_count * requests_per_thread

    start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    duration = time.perf_counter() - start
    rps = total_reqs / duration

    return {
        "threads": threads_count,
        "total_requests": total_reqs,
        "duration_s": duration,
        "requests_per_second": rps,
        "errors": errors,
        "avg_ms_per_request": (duration * 1000) / total_reqs,
    }


def benchmark_memory_profile(iterations: int = 10000) -> dict[str, Any]:
    """Measure memory allocation and check for memory leaks across thousands of requests."""
    gc.collect()
    tracemalloc.start()

    client = SelfHealingClient(
        base_url="https://mem.benchmark.example.com",
        retry=RetryConfig(max_attempts=2),
        circuit_breaker=CircuitBreakerConfig(failure_threshold=5),
        rate_limit=RateLimitConfig(respect_retry_after=True),
        transport=FakeTransport(default_response=make_response(200, json_body={"data": "x" * 100})),
    )

    snapshot_start = tracemalloc.take_snapshot()

    for _ in range(iterations):
        client.get("/mem-test")

    snapshot_end = tracemalloc.take_snapshot()
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Memory growth
    top_stats = snapshot_end.compare_to(snapshot_start, "lineno")
    total_growth_bytes = sum(stat.size_diff for stat in top_stats)

    return {
        "iterations": iterations,
        "peak_memory_kb": peak_mem / 1024.0,
        "current_memory_kb": current_mem / 1024.0,
        "memory_growth_kb": total_growth_bytes / 1024.0,
        "bytes_per_request": total_growth_bytes / iterations,
    }


def benchmark_fallback_latency(iterations: int = 2000) -> dict[str, Any]:
    """Measure fallback execution latency when primary endpoints fail."""
    client = SelfHealingClient(
        base_url="https://fallback.benchmark.example.com",
        retry=RetryConfig(max_attempts=1),
        circuit_breaker=CircuitBreakerConfig(enabled=False),
        health=HealthConfig(enabled=False),
        fallback=FallbackConfig(
            static_response={"cached": True, "source": "fallback"},
        ),
        transport=FakeTransport(default_response=make_response(503)),
    )

    latencies: list[float] = []
    start = time.perf_counter()
    for _ in range(iterations):
        t0 = time.perf_counter()
        resp = client.get("/primary-failing")
        t1 = time.perf_counter()
        assert resp.status_code == 200
        assert resp.json()["source"] == "fallback"
        latencies.append((t1 - t0) * 1000)
    total_ms = (time.perf_counter() - start) * 1000

    return {
        "iterations": iterations,
        "total_ms": total_ms,
        "avg_fallback_ms": total_ms / iterations,
        "p99_fallback_ms": sorted(latencies)[int(iterations * 0.99)],
    }


def main() -> None:
    print("=" * 70)
    print("RUNNING COMPREHENSIVE PERFORMANCE BENCHMARK SUITE")
    print("=" * 70)

    print("\n[1/6] Benchmarking Pipeline Latency Overhead (5,000 iterations)...")
    res_overhead = benchmark_pipeline_overhead(5000)
    print(f"  Raw Transport Avg:       {res_overhead['raw_avg_ms']:.4f} ms")
    print(f"  SelfHealingClient Avg:   {res_overhead['client_avg_ms']:.4f} ms")
    print(f"  Net Added Overhead:      {res_overhead['net_overhead_ms']:.4f} ms")
    print(f"  P50: {res_overhead['p50_ms']:.4f} ms | P90: {res_overhead['p90_ms']:.4f} ms | P99: {res_overhead['p99_ms']:.4f} ms")

    print("\n[2/6] Benchmarking Circuit Breaker Fast-Fail (5,000 rejections)...")
    res_cb = benchmark_circuit_breaker_fast_fail(5000)
    print(f"  Avg Fast-Fail Time:      {res_cb['avg_rejection_ms']:.4f} ms ({res_cb['avg_rejection_ms']*1000:.1f} microseconds)")
    print(f"  Rejection Throughput:    {res_cb['rejections_per_sec']:,} req/sec")

    print("\n[3/6] Benchmarking Async High-Concurrency Throughput (5,000 requests, 50 concurrency)...")
    res_async = benchmark_async_throughput(5000, 50)
    print(f"  Throughput:              {res_async['requests_per_second']:,.0f} req/sec")
    print(f"  Avg Latency:             {res_async['avg_latency_ms']:.4f} ms")
    print(f"  P99 Latency:             {res_async['p99_latency_ms']:.4f} ms")

    print("\n[4/6] Benchmarking Multi-Threaded Contention (10 threads, 5,000 requests)...")
    res_threads = benchmark_multithreaded_contention(10, 500)
    print(f"  Multi-Thread Throughput: {res_threads['requests_per_second']:,.0f} req/sec")
    print(f"  Errors / Contention:     {res_threads['errors']}")

    print("\n[5/6] Benchmarking Memory & Heap Profile (10,000 requests)...")
    res_mem = benchmark_memory_profile(10000)
    print(f"  Peak Memory Traced:      {res_mem['peak_memory_kb']:.2f} KB")
    print(f"  Net Growth over 10k:     {res_mem['memory_growth_kb']:.2f} KB ({res_mem['bytes_per_request']:.2f} bytes/req)")

    print("\n[6/6] Benchmarking Fallback Handler Latency (2,000 requests)...")
    res_fb = benchmark_fallback_latency(2000)
    print(f"  Avg Fallback Exec Time:  {res_fb['avg_fallback_ms']:.4f} ms")
    print(f"  P99 Fallback Latency:    {res_fb['p99_fallback_ms']:.4f} ms")

    print("\n" + "=" * 70)
    print("BENCHMARK EXECUTION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
