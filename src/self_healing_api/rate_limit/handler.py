"""
handler.py — HTTP 429 and Retry-After rate-limit handling logic.

Parses Retry-After headers (seconds or HTTP date format) and enforces
maximum wait limits to prevent indefinite thread blocking.
"""

from __future__ import annotations

import email.utils
from datetime import UTC, datetime

from self_healing_api.config.models import RateLimitConfig
from self_healing_api.errors.exceptions import RateLimitError
from self_healing_api.transport.base import TransportResponse


class RateLimitHandler:
    """
    Handles HTTP 429 rate limit response parsing and policy enforcement.

    Parameters
    ----------
    config : RateLimitConfig
    """

    def __init__(self, config: RateLimitConfig) -> None:
        self._config = config

    def parse_retry_after(self, response: TransportResponse) -> float | None:
        """
        Extract and parse Retry-After header value in seconds.

        Supports both integer/float seconds and RFC 2822 / RFC 1123 HTTP date strings.
        """
        header_val: str | None = None
        for k, v in response.headers.items():
            if k.lower() == "retry-after":
                header_val = v.strip()
                break

        if not header_val:
            return None

        # Format 1: Seconds as numeric string
        try:
            val = float(header_val)
            return max(0.0, val)
        except ValueError:
            pass

        # Format 2: HTTP-date string
        try:
            dt = email.utils.parsedate_to_datetime(header_val)
            if dt is not None:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                now = datetime.now(tz=UTC)
                delta = (dt - now).total_seconds()
                return max(0.0, delta)
        except Exception:
            pass

        return None

    def process_rate_limit(self, response: TransportResponse) -> float | None:
        """
        Process a 429 response and return the wait delay in seconds.

        Returns
        -------
        float | None
            Wait delay in seconds if Retry-After is specified and valid.
            None if backoff should fall back to default RetryEngine logic.

        Raises
        ------
        RateLimitError
            If Retry-After header exceeds max_retry_after_wait limit.
        """
        if response.status_code != 429:
            return 0.0

        if self._config.respect_retry_after:
            retry_after = self.parse_retry_after(response)
            if retry_after is not None:
                if retry_after > self._config.max_retry_after_wait:
                    raise RateLimitError(
                        f"Retry-After header ({retry_after:.1f}s) exceeds "
                        f"max allowed wait ({self._config.max_retry_after_wait:.1f}s).",
                        retry_after=retry_after,
                    )
                return retry_after

        return None
