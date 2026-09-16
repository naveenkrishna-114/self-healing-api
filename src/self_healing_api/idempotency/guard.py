"""
guard.py — Idempotency enforcement for retries of non-idempotent operations.

Prevents unsafe retries of POST/PATCH requests without an explicit idempotency key.
"""

from __future__ import annotations

import logging
import warnings

from self_healing_api.config.models import IdempotencyConfig
from self_healing_api.errors.exceptions import IdempotencyError
from self_healing_api.utils.ids import generate_idempotency_key

logger = logging.getLogger(__name__)


class IdempotencyGuard:
    """
    Enforces idempotency rules prior to retrying HTTP requests.

    Parameters
    ----------
    config : IdempotencyConfig
    """

    IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})

    def __init__(self, config: IdempotencyConfig) -> None:
        self._config = config

    def is_idempotent_method(self, method: str) -> bool:
        """Return True if HTTP method is inherently idempotent according to RFC 9110."""
        return method.upper() in self.IDEMPOTENT_METHODS

    def check_or_inject_key(
        self, method: str, headers: dict[str, str], attempt: int = 1
    ) -> dict[str, str]:
        """
        Validate presence of idempotency key before attempting request/retry.

        Parameters
        ----------
        method : str
            HTTP method (e.g. "POST").
        headers : dict[str, str]
            Request headers.
        attempt : int
            Attempt sequence number (1 = initial attempt, >1 = retry).

        Returns
        -------
        dict[str, str]
            Updated headers.

        Raises
        ------
        IdempotencyError
            If retry of a non-idempotent operation is attempted without a key
            and auto_generate=False.
        """
        if not self._config.enabled:
            return dict(headers)

        new_headers = dict(headers)
        method_upper = method.upper()

        if self.is_idempotent_method(method_upper):
            return new_headers

        # Check if idempotency key header is present
        header_key = self._config.header_name
        has_key = any(k.lower() == header_key.lower() for k in new_headers)

        if has_key:
            return new_headers

        # If it's a retry attempt for non-idempotent method without key:
        if attempt > 1:
            if self._config.auto_generate:
                generated_key = generate_idempotency_key()
                new_headers[header_key] = generated_key
                warnings.warn(
                    f"Auto-generated idempotency key {generated_key!r} for non-idempotent "
                    f"{method_upper} retry. Set '{header_key}' explicitly for strict safety.",
                    stacklevel=2,
                )
                logger.warning(
                    "Auto-generated idempotency key for %s retry", method_upper
                )
                return new_headers
            else:
                raise IdempotencyError(
                    f"Cannot retry non-idempotent operation {method_upper} without "
                    f"an idempotency key. Set '{header_key}' header or enable "
                    f"IdempotencyConfig.auto_generate=True.",
                    http_method=method_upper,
                )

        return new_headers
