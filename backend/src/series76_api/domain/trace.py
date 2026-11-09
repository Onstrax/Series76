"""Pure debug-trace sanitization policy (Spec 3, Req 10).

A debug trace returned to a developer-owner must contain ONLY sanitized tool
arguments, sanitized tool results, and non-negative timing durations. It must
never contain credentials, tokens, secret-bearing headers, the KEK, the DEK,
the system prompt, or provider secrets (Property 44, 46). This module owns the
pure sanitization rules; the adapter that reads/writes the encrypted trace
lives in infrastructure/application.
"""

from __future__ import annotations

from typing import Any

# Key substrings (case-insensitive) whose values are always stripped.
_FORBIDDEN_KEY_MARKERS: tuple[str, ...] = (
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
    "wrapped_dek",
    "nonce",
    "prompt",
    "system_prompt",
    "private_key",
    "credential",
    "header",
    "bearer",
)

# The stable, byte-for-byte identical denial body for every non-authorized case
# (non-developer, non-owner, developer A vs B, nonexistent, deleted). It
# discloses nothing about existence or content (Property 46).
IDENTICAL_DENIAL: dict[str, str] = {"error": "not_found"}


def _is_forbidden_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _FORBIDDEN_KEY_MARKERS)


def sanitize_value(value: Any) -> Any:
    """Recursively strip forbidden keys from a trace fragment.

    Dicts drop forbidden-named keys entirely; lists recurse; scalars pass
    through. The result contains no secret-named field at any depth.
    """

    if isinstance(value, dict):
        return {
            k: sanitize_value(v)
            for k, v in value.items()
            if not _is_forbidden_key(str(k))
        }
    if isinstance(value, list):
        return [sanitize_value(v) for v in value]
    return value


def sanitize_duration_ms(duration_ms: int | None) -> int | None:
    """Clamp a timing duration to a non-negative integer (or ``None``).

    Negative durations are meaningless and are dropped to ``None`` so the trace
    only ever exposes non-negative timing (Req 10.2).
    """

    if duration_ms is None:
        return None
    return max(0, int(duration_ms))


def sanitize_trace(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a sanitized trace: tool args/results + non-negative timings only.

    Keeps only the ``tool_args``, ``tool_results``, and ``steps`` structures
    (recursively stripped of forbidden keys) plus a non-negative
    ``duration_ms``; everything else (and any secret-named field) is dropped.
    """

    out: dict[str, Any] = {}
    if "tool_args" in raw:
        out["tool_args"] = sanitize_value(raw["tool_args"])
    if "tool_results" in raw:
        out["tool_results"] = sanitize_value(raw["tool_results"])
    if "steps" in raw:
        out["steps"] = sanitize_value(raw["steps"])
    if "duration_ms" in raw:
        out["duration_ms"] = sanitize_duration_ms(raw.get("duration_ms"))
    return out


__all__ = [
    "IDENTICAL_DENIAL",
    "sanitize_value",
    "sanitize_duration_ms",
    "sanitize_trace",
]
