"""
utils — Shared utilities: clock abstraction, ID generation, secret masking.
"""

from self_healing_api.utils.clock import Clock, FakeClock, SystemClock
from self_healing_api.utils.ids import (
    generate_idempotency_key,
    generate_request_id,
    is_valid_uuid,
)
from self_healing_api.utils.masking import MASK_VALUE, SecretMasker

__all__ = [
    # Clock
    "Clock",
    "SystemClock",
    "FakeClock",
    # IDs
    "generate_request_id",
    "generate_idempotency_key",
    "is_valid_uuid",
    # Masking
    "SecretMasker",
    "MASK_VALUE",
]
