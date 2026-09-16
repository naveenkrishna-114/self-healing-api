"""
health.py — Passive and active endpoint health monitoring.

Tracks consecutive request successes and failures per endpoint to determine
endpoint health state (HEALTHY vs UNHEALTHY vs DEGRADED vs RECOVERING).

Thread Safety
-------------
All health state modifications are protected by threading.Lock.
"""

from __future__ import annotations

import enum
import threading
from dataclasses import dataclass
from typing import Any

from self_healing_api.config.models import HealthConfig
from self_healing_api.utils.clock import Clock, SystemClock


class HealthState(enum.Enum):
    """Possible health states for an endpoint."""

    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"


@dataclass
class EndpointHealth:
    """
    Mutable metrics and status tracking for a single endpoint.
    """

    endpoint: str
    state: HealthState = HealthState.HEALTHY
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_requests: int = 0
    total_failures: int = 0
    last_request_at: float = 0.0
    last_failure_at: float = 0.0
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return structured dict for observability."""
        return {
            "endpoint": self.endpoint,
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "last_request_at": self.last_request_at,
            "last_failure_at": self.last_failure_at,
            "last_error": self.last_error,
        }


class HealthTracker:
    """
    Tracks passive health state for all endpoints used by a client.

    Parameters
    ----------
    config : HealthConfig
    clock : Clock | None
    """

    def __init__(self, config: HealthConfig, clock: Clock | None = None) -> None:
        self._config = config
        self._clock: Clock = clock or SystemClock()
        self._lock = threading.Lock()
        self._endpoints: dict[str, EndpointHealth] = {}

    def _get_or_create(self, endpoint: str) -> EndpointHealth:
        """Get or initialize EndpointHealth for endpoint (must be inside lock)."""
        if endpoint not in self._endpoints:
            self._endpoints[endpoint] = EndpointHealth(endpoint=endpoint)
        return self._endpoints[endpoint]

    def record_success(self, endpoint: str) -> None:
        """
        Record a successful request outcome for an endpoint.

        Resets consecutive failure count. If state was UNHEALTHY or RECOVERING
        and consecutive successes reaches recovery_threshold, transitions to HEALTHY.
        """
        if not self._config.enabled or not endpoint:
            return

        with self._lock:
            info = self._get_or_create(endpoint)
            now = self._clock.monotonic()
            info.last_request_at = now
            info.total_requests += 1
            info.consecutive_failures = 0
            info.consecutive_successes += 1

            if info.state in (HealthState.UNHEALTHY, HealthState.RECOVERING):
                if info.consecutive_successes >= self._config.recovery_threshold:
                    info.state = HealthState.HEALTHY

    def record_failure(self, endpoint: str, error: Exception | str | None = None) -> None:
        """
        Record a request failure outcome for an endpoint.

        Resets consecutive success count. If consecutive failures reaches
        unhealthy_threshold, transitions to UNHEALTHY.
        """
        if not self._config.enabled or not endpoint:
            return

        with self._lock:
            info = self._get_or_create(endpoint)
            now = self._clock.monotonic()
            info.last_request_at = now
            info.last_failure_at = now
            info.total_requests += 1
            info.total_failures += 1
            info.consecutive_successes = 0
            info.consecutive_failures += 1
            info.last_error = str(error) if error is not None else None

            if info.consecutive_failures >= self._config.unhealthy_threshold:
                info.state = HealthState.UNHEALTHY

    def get_health(self, endpoint: str) -> EndpointHealth:
        """Get health data snapshot for an endpoint."""
        with self._lock:
            info = self._get_or_create(endpoint)
            return EndpointHealth(
                endpoint=info.endpoint,
                state=info.state,
                consecutive_failures=info.consecutive_failures,
                consecutive_successes=info.consecutive_successes,
                total_requests=info.total_requests,
                total_failures=info.total_failures,
                last_request_at=info.last_request_at,
                last_failure_at=info.last_failure_at,
                last_error=info.last_error,
            )

    def get_state(self, endpoint: str) -> HealthState:
        """Get current HealthState for an endpoint."""
        with self._lock:
            return self._get_or_create(endpoint).state

    def is_healthy(self, endpoint: str) -> bool:
        """Return True if endpoint state is HEALTHY or RECOVERING."""
        if not self._config.enabled or not endpoint:
            return True
        with self._lock:
            info = self._get_or_create(endpoint)
            return info.state in (HealthState.HEALTHY, HealthState.RECOVERING)

    def reset(self, endpoint: str | None = None) -> None:
        """Reset health state for a single endpoint or all endpoints."""
        with self._lock:
            if endpoint:
                if endpoint in self._endpoints:
                    del self._endpoints[endpoint]
            else:
                self._endpoints.clear()
