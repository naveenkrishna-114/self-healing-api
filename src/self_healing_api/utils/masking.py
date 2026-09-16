"""
masking.py — Credential and sensitive field masker.

SECURITY REQUIREMENT: API keys, passwords, bearer tokens and other
secrets must NEVER appear in logs, metrics, or telemetry events.

The SecretMasker scrubs configured header names and JSON body field
names before any data is passed to loggers or observability hooks.

Design rules
------------
- Masking is applied at the boundary — before data leaves the package.
- The original request/response objects are never mutated.
- Masking produces a safe copy for logging purposes only.
- The mask replacement string is intentionally obvious: "***MASKED***".
"""

from __future__ import annotations

from typing import Any

# The string that replaces sensitive values in logs and events.
MASK_VALUE = "***MASKED***"

# Default headers that are always masked regardless of configuration.
# Developers can add more via ObservabilityConfig.mask_headers.
DEFAULT_MASKED_HEADERS: frozenset[str] = frozenset(
    {
        "authorization",
        "x-api-key",
        "x-auth-token",
        "cookie",
        "set-cookie",
        "proxy-authorization",
        "x-forwarded-for",  # can contain internal IPs
    }
)


class SecretMasker:
    """
    Masks sensitive values in headers and JSON body dicts.

    All comparisons are case-insensitive for headers (HTTP headers are
    case-insensitive by specification).

    Parameters
    ----------
    masked_headers : frozenset[str] | set[str] | None
        Additional header names to mask, merged with DEFAULT_MASKED_HEADERS.
    masked_body_fields : frozenset[str] | set[str] | None
        JSON body field names whose values should be masked.

    Example
    -------
    ::

        masker = SecretMasker(
            masked_headers=frozenset({"X-Custom-Token"}),
            masked_body_fields=frozenset({"password", "secret"}),
        )

        safe_headers = masker.mask_headers({"Authorization": "Bearer tok123"})
        # → {"Authorization": "***MASKED***"}

        safe_body = masker.mask_body({"username": "alice", "password": "s3cr3t"})
        # → {"username": "alice", "password": "***MASKED***"}
    """

    def __init__(
        self,
        masked_headers: frozenset[str] | set[str] | None = None,
        masked_body_fields: frozenset[str] | set[str] | None = None,
    ) -> None:
        extra_headers: frozenset[str] = (
            frozenset(h.lower() for h in masked_headers)
            if masked_headers
            else frozenset()
        )
        self._masked_headers: frozenset[str] = DEFAULT_MASKED_HEADERS | extra_headers

        self._masked_body_fields: frozenset[str] = (
            frozenset(masked_body_fields) if masked_body_fields else frozenset()
        )

    def mask_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """
        Return a copy of ``headers`` with sensitive values replaced.

        Original dict is not mutated.

        Parameters
        ----------
        headers : dict[str, str]
            Raw request or response headers.

        Returns
        -------
        dict[str, str]
            Safe copy for logging.
        """
        return {
            k: MASK_VALUE if k.lower() in self._masked_headers else v
            for k, v in headers.items()
        }

    def mask_body(self, body: dict[str, Any]) -> dict[str, Any]:
        """
        Return a shallow copy of a JSON body dict with sensitive fields masked.

        Only top-level fields are masked. Nested structures are not
        recursively masked (to avoid deep-copy overhead on large payloads).

        Parameters
        ----------
        body : dict[str, Any]
            Parsed JSON body.

        Returns
        -------
        dict[str, Any]
            Safe copy for logging.
        """
        if not self._masked_body_fields:
            return body.copy()
        return {
            k: MASK_VALUE if k in self._masked_body_fields else v
            for k, v in body.items()
        }

    def mask_url(self, url: str) -> str:
        """
        Redact query-string parameters that may contain tokens.

        Replaces values of query parameters whose names match common
        credential patterns (api_key, token, secret, password, etc.).

        Parameters
        ----------
        url : str
            Full request URL potentially containing credentials in the
            query string.

        Returns
        -------
        str
            URL with sensitive query-parameter values redacted.
        """
        import urllib.parse

        sensitive_params: frozenset[str] = frozenset(
            {
                "api_key", "apikey", "key", "token", "access_token",
                "secret", "password", "passwd", "pwd", "auth",
                "authorization", "client_secret",
            }
        )

        parsed = urllib.parse.urlparse(url)
        if not parsed.query:
            return url

        params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        masked_params = [
            (k, MASK_VALUE if k.lower() in sensitive_params else v)
            for k, v in params
        ]
        safe_query = urllib.parse.urlencode(masked_params)
        return urllib.parse.urlunparse(parsed._replace(query=safe_query))

    def is_header_masked(self, header_name: str) -> bool:
        """Return True if this header name would be masked."""
        return header_name.lower() in self._masked_headers
