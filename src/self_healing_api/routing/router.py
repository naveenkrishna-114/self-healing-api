"""
router.py — Health-aware endpoint router and failover.

Selects target endpoint based on configured strategy ("priority", "round_robin", "random")
and current endpoint health status.
"""

from __future__ import annotations

import random
import threading
from collections.abc import Sequence

from self_healing_api.config.models import RoutingConfig
from self_healing_api.errors.exceptions import AllEndpointsUnavailableError
from self_healing_api.health.health import HealthTracker


class HealthAwareRouter:
    """
    Selects destination endpoints and manages failover.

    Parameters
    ----------
    config : RoutingConfig
    endpoints : Sequence[str]
        Ordered list of candidate base URLs.
    health_tracker : HealthTracker | None
    """

    def __init__(
        self,
        config: RoutingConfig,
        endpoints: Sequence[str],
        health_tracker: HealthTracker | None = None,
    ) -> None:
        self._config = config
        self._endpoints: tuple[str, ...] = tuple(ep for ep in endpoints if ep)
        self._health_tracker = health_tracker
        self._rr_index = 0
        self._lock = threading.Lock()

    @property
    def endpoints(self) -> tuple[str, ...]:
        """All configured endpoints."""
        return self._endpoints

    def select_endpoint(self) -> str:
        """
        Select an endpoint according to routing strategy and health state.

        Returns
        -------
        str
            Selected base URL endpoint.

        Raises
        ------
        AllEndpointsUnavailableError
            If failover is enabled and all configured endpoints are unhealthy.
        """
        if not self._endpoints:
            raise AllEndpointsUnavailableError("No endpoints configured for router.")

        candidates = list(self._endpoints)
        if self._config.failover_enabled and self._health_tracker:
            healthy = [ep for ep in candidates if self._health_tracker.is_healthy(ep)]
            if not healthy:
                raise AllEndpointsUnavailableError(
                    f"All {len(candidates)} endpoint(s) are marked UNHEALTHY.",
                    endpoints=candidates,
                )
            candidates = healthy

        if self._config.strategy == "priority":
            return candidates[0]
        elif self._config.strategy == "round_robin":
            with self._lock:
                idx = self._rr_index % len(candidates)
                self._rr_index += 1
                return candidates[idx]
        elif self._config.strategy == "random":
            return random.choice(candidates)
        else:
            return candidates[0]
