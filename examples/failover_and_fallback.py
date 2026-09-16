"""
failover_and_fallback.py — Multi-endpoint failover and custom fallback handler example.
"""

from self_healing_api import SelfHealingClient
from self_healing_api.config import FallbackConfig, HealthConfig, RoutingConfig
from self_healing_api.fallback import FallbackContext
from self_healing_api.transport.fake_transport import FakeTransport, make_response


def custom_fallback(ctx: FallbackContext) -> dict:
    print(f"[Fallback Triggered] Original error: {ctx.error}")
    return {"status": "degraded", "cached_user": "Guest"}


def main() -> None:
    transport = FakeTransport(
        responses=[
            make_response(503),  # Primary fails
            make_response(503),  # Secondary fails
        ]
    )

    client = SelfHealingClient(
        base_url="https://primary.api.com",
        endpoints=["https://secondary.api.com"],
        routing=RoutingConfig(strategy="priority", failover_enabled=True),
        health=HealthConfig(enabled=True, unhealthy_threshold=1),
        fallback=FallbackConfig(handler=custom_fallback),
        transport=transport,
    )

    response = client.get("/user/profile")
    print(f"Response Status Code: {response.status_code}")
    print(f"Response Payload: {response.json()}")


if __name__ == "__main__":
    main()
