"""ManifestBuilder: the stable canonical digest for an edition (Task 13).

Design reference: data-and-ingestion/design.md § Components and Interfaces /
ManifestBuilder.

Builds a :class:`VerificationManifestData` from source hashes, engine/rule/
extractor versions, canonical facts, corrections, and the verification report,
and computes a **stable canonical digest** that identifies the edition and
enables verified_replay reproduction and non-duplication (Req 1.5, 2.2, 10.4).

The digest is a SHA-256 over a canonical JSON serialization with sorted keys and
no insignificant whitespace, so:

* identical approved artifacts always produce an identical digest; and
* any change to any input produces a different digest.

The same digest is wired into the Publisher (which stores it on the edition and
the pointer-flip event) and the verified_replay Extractor (which binds its
reconstruction to one edition via the manifest digest).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class VerificationManifestData:
    """The deterministic package an edition is built from.

    Every field feeds the canonical digest. ``source_shas`` keys are source
    filenames mapped to their recorded SHA-256; ``canonical_facts`` is the typed
    fact payload; ``corrections`` are applied verification corrections; and
    ``verification_report`` is the gate's PASS report.
    """

    source_shas: dict[str, str]
    normalization_version: str
    rules_version: str
    extractor_version: str
    canonical_facts: list[dict[str, Any]]
    corrections: list[dict[str, Any]]
    verification_report: dict[str, Any]


def _canonicalize(value: Any) -> Any:
    """Return a JSON-serializable, order-stable form of ``value``.

    ``Decimal`` is serialized via its exact string form (never a lossy float),
    mappings get sorted keys, and sequences keep their order. This guarantees
    the same logical content always serializes to the same bytes.
    """

    if isinstance(value, Decimal):
        return {"__decimal__": format(value, "f")}
    if isinstance(value, dict):
        return {str(k): _canonicalize(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list | tuple)):
        return [_canonicalize(v) for v in value]
    return value


def canonical_json(data: VerificationManifestData) -> str:
    """Serialize ``data`` to the canonical JSON string the digest is taken over."""

    payload = {
        "source_shas": _canonicalize(data.source_shas),
        "normalization_version": data.normalization_version,
        "rules_version": data.rules_version,
        "extractor_version": data.extractor_version,
        "canonical_facts": _canonicalize(data.canonical_facts),
        "corrections": _canonicalize(data.corrections),
        "verification_report": _canonicalize(data.verification_report),
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def compute_manifest_digest(data: VerificationManifestData) -> str:
    """Compute the stable canonical SHA-256 digest of a manifest (hex)."""

    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class BuiltManifest:
    """A manifest plus its computed canonical digest."""

    data: VerificationManifestData
    manifest_digest: str

    @property
    def source_shas(self) -> dict[str, str]:
        return self.data.source_shas


class ManifestBuilder:
    """Build a verification manifest and bind it to its canonical digest."""

    def build(self, data: VerificationManifestData) -> BuiltManifest:
        """Return the manifest with its stable canonical digest attached."""

        return BuiltManifest(data=data, manifest_digest=compute_manifest_digest(data))
