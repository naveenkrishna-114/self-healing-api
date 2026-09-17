#!/usr/bin/env python3
"""
Self-Healing API Resilience Mesh — Live Website & API Tester CLI
Author: Naveen Krishna

Usage:
    python test_website.py <URL> [options]

Examples:
    python test_website.py https://httpbin.org/get
    python test_website.py https://httpbin.org/status/503 --retries 3
    python test_website.py https://api.github.com --timeout 2.0
"""

import argparse
import sys
import time

# Ensure safe output encoding on Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from self_healing_api import SelfHealingClient
    from self_healing_api.config.models import (
        CircuitBreakerConfig,
        RetryConfig,
        TimeoutConfig,
    )
except ImportError:
    import os
    sys.path.insert(0, os.path.abspath("src"))
    from self_healing_api import SelfHealingClient
    from self_healing_api.config.models import (
        CircuitBreakerConfig,
        RetryConfig,
        TimeoutConfig,
    )


def test_url(url: str, method: str = "GET", retries: int = 3, timeout: float = 3.0, iterations: int = 1):
    print("=" * 70)
    print("[*] SELF-HEALING API RESILIENCE MESH -- LIVE TARGET TESTER")
    print("    Author: Naveen Krishna | Package: self-healing-api v0.1.0")
    print("=" * 70)
    print(f"Target URL : {url}")
    print(f"Method     : {method.upper()}")
    print(f"Retries    : {retries} max attempts (AWS Full Jitter)")
    print(f"Timeout    : {timeout}s connect / read")
    print(f"Iterations : {iterations}")
    print("-" * 70)

    # Initialize the SelfHealingClient with configured resilience policies
    client = SelfHealingClient(
        base_url=url,
        retry=RetryConfig(
            max_attempts=max(1, retries),
            base_delay=0.3,
            jitter=True,
            jitter_strategy="full",
        ),
        timeout=TimeoutConfig(
            connect=timeout,
            read=timeout,
            total=timeout * (retries + 1),
        ),
        circuit_breaker=CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=5.0,
        ),
    )

    success_count = 0
    failure_count = 0
    latencies = []

    for i in range(1, iterations + 1):
        print(f"\n[Test #{i}/{iterations}] Dispatched request to {url}...")
        start = time.perf_counter()
        try:
            # Execute request through the resilience mesh pipeline
            resp = client.request(method=method, path_or_url=url)
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)
            success_count += 1
            print(f"  [+] SUCCESS | HTTP {resp.status_code} | Latency: {elapsed:.2f}ms")
            print(f"      Headers: Server={resp.headers.get('server', 'N/A')}, Content-Type={resp.headers.get('content-type', 'N/A')}")
            preview = resp.text()[:120].replace("\n", " ").replace("\r", "")
            print(f"      Payload Preview: {preview}...")
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            latencies.append(elapsed)
            failure_count += 1
            print(f"  [-] RESILIENCE INTERCEPTION: {type(exc).__name__}")
            print(f"      Details: {exc}")
            print(f"      Mesh applied retries/failover policies before reporting final state.")

    print("\n" + "=" * 70)
    print("RESILIENCE TEST SUMMARY")
    print("=" * 70)
    print(f"Total Requests Dispatched : {iterations}")
    print(f"Successful Requests       : {success_count} ({(success_count/iterations)*100:.1f}%)")
    print(f"Failed / Intercepted      : {failure_count}")
    if latencies:
        avg_lat = sum(latencies) / len(latencies)
        print(f"Average Round-Trip Latency: {avg_lat:.2f}ms (Min: {min(latencies):.2f}ms, Max: {max(latencies):.2f}ms)")
    print("=" * 70)
    print("To protect your own project with this mesh, add to your code:")
    print("    from self_healing_api import SelfHealingClient")
    print("    client = SelfHealingClient()")
    print(f"    response = client.get('{url}')")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Test any website or API with the Self-Healing API Mesh")
    parser.add_argument("url", help="Target website or API URL (e.g. https://api.github.com)")
    parser.add_argument("-m", "--method", default="GET", help="HTTP Method (default: GET)")
    parser.add_argument("-r", "--retries", type=int, default=3, help="Max retries (default: 3)")
    parser.add_argument("-t", "--timeout", type=float, default=3.0, help="Timeout in seconds (default: 3.0)")
    parser.add_argument("-n", "--iterations", type=int, default=1, help="Number of test requests (default: 1)")

    args = parser.parse_args()
    test_url(
        url=args.url,
        method=args.method,
        retries=args.retries,
        timeout=args.timeout,
        iterations=args.iterations,
    )


if __name__ == "__main__":
    main()
