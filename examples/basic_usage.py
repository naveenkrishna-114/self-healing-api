"""
basic_usage.py — Minimal example showing sync and async client usage.
"""

import asyncio

from self_healing_api import AsyncSelfHealingClient, SelfHealingClient
from self_healing_api.config import CircuitBreakerConfig, RetryConfig, TimeoutConfig
from self_healing_api.transport.fake_transport import FakeAsyncTransport, FakeTransport, make_response


def main_sync() -> None:
    print("--- Synchronous SelfHealingClient Example ---")
    transport = FakeTransport(
        responses=[
            make_response(503),  # Attempt 1 fails
            make_response(200, json_body={"message": "Success after retry!"}),  # Attempt 2 succeeds
        ]
    )

    client = SelfHealingClient(
        base_url="https://api.example.com",
        timeout=TimeoutConfig(connect=3.0, read=5.0, total=15.0),
        retry=RetryConfig(max_attempts=3, backoff="exponential", jitter=True),
        circuit_breaker=CircuitBreakerConfig(enabled=True, failure_threshold=3),
        transport=transport,
    )

    response = client.get("/data")
    print(f"Status: {response.status_code}")
    print(f"Payload: {response.json()}")


async def main_async() -> None:
    print("\n--- Asynchronous AsyncSelfHealingClient Example ---")
    transport = FakeAsyncTransport(
        responses=[make_response(200, json_body={"message": "Async Success!"})]
    )

    async with AsyncSelfHealingClient(
        base_url="https://api.example.com",
        transport=transport,
    ) as client:
        response = await client.get("/async-data")
        print(f"Async Status: {response.status_code}")
        print(f"Async Payload: {response.json()}")


if __name__ == "__main__":
    main_sync()
    asyncio.run(main_async())
