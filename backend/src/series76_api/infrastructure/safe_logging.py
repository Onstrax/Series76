"""Secret-redacting logging helpers (Spec 3, Property 44).

No token, password, secret-bearing header, KEK, DEK, system prompt, or
provider secret may appear in any log, trace, or observability output — whether
encrypted or not. These helpers provide a central, auditable redaction seam so
log sites never interpolate secret values directly.
"""

from __future__ import annotations

from typing import Any

# Substrings (case-insensitive) of keys whose values must be redacted.
_SECRET_KEY_MARKERS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "kek",
    "dek",
    "api_key",
    "apikey",
    "verifier",
    "ciphertext",
    "wrapped_dek",
    "nonce",
    "prompt",
    "private_key",
)

REDACTED = "***REDACTED***"


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SECRET_KEY_MARKERS)


def redact_mapping(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``data`` with secret-bearing values redacted.

    Recurses into nested dicts and lists so a secret nested in a structured log
    record is still masked.
    """

    result: dict[str, Any] = {}
    for key, value in data.items():
        if _is_secret_key(key):
            result[key] = REDACTED
        elif isinstance(value, dict):
            result[key] = redact_mapping(value)
        elif isinstance(value, list):
            result[key] = [redact_mapping(v) if isinstance(v, dict) else v for v in value]
        else:
            result[key] = value
    return result


def safe_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return request headers with ``Authorization``/cookie values redacted."""

    return {k: (REDACTED if _is_secret_key(k) else v) for k, v in headers.items()}


__all__ = ["redact_mapping", "safe_headers", "REDACTED"]
