"""
ids.py — Request ID and idempotency key generation.

Every request that flows through SelfHealingClient receives a unique
request_id. This ID is attached to all log entries, metrics, and events
emitted during that request's lifecycle, allowing full traceability.

Idempotency keys are also generated here. A key generated for a request
is reused across all retry attempts for that same request — this is what
allows providers to deduplicate retried operations.
"""

from __future__ import annotations

import uuid


def generate_request_id() -> str:
    """
    Generate a unique request ID using UUID v4.

    Returns
    -------
    str
        A lowercase hyphenated UUID string, e.g.
        ``"3fa85f64-5717-4562-b3fc-2c963f66afa6"``.
    """
    return str(uuid.uuid4())


def generate_idempotency_key() -> str:
    """
    Generate a unique idempotency key using UUID v4.

    This key is stable for the lifetime of a single request attempt group
    (i.e. all retries of the same logical request use the same key).

    Returns
    -------
    str
        A lowercase hyphenated UUID string.
    """
    return str(uuid.uuid4())


def is_valid_uuid(value: str) -> bool:
    """
    Return True if ``value`` is a valid UUID string (any version).

    Used to validate caller-supplied idempotency keys.

    Parameters
    ----------
    value : str
        The string to validate.

    Returns
    -------
    bool
    """
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False
