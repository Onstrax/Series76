"""verified_replay Extractor (Spec 1, Task 6).

Design reference: data-and-ingestion/design.md § Components and Interfaces /
Extractor (verified_replay) and § Two Ingestion Modes.

``verified_replay`` is the reproducible default. It loads approved, versioned
artifacts plus the canonical manifest, recomputes and compares **each** artifact
SHA-256 and confirms **each** declared transformation **before** reconstruction,
and makes **zero** external AI/OCR/LLM/network calls (Req 2.1, 2.2). On any hash
or transformation mismatch it reports ``HASH_MISMATCH`` and halts before
producing an edition, leaving any prior edition unchanged (Req 2.3). On success
it emits reconstructed typed facts.

This module deliberately imports **nothing** that could reach a network, an LLM,
or an OCR engine. It depends only on :mod:`hashlib`, the typed fact model, and
the error taxonomy. A test asserts the module's import graph contains no such
client (Property: replay makes zero external calls).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from series76_data.errors import IngestionErrorCode
from series76_data.pipeline.diagnostics import fail
from series76_data.pipeline.source_inventory import compute_sha256, digests_match

# A decoder is any callable from a verified manifest view to typed facts.
ArtifactDecoder = Callable[["ReplayManifestView"], Sequence[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class ReplayArtifact:
    """One approved, versioned artifact to be replayed.

    Attributes:
        name: a stable identifier for the artifact (e.g. a logical filename).
        payload: the exact bytes of the artifact as approved.
        recorded_sha256: the digest recorded in the canonical manifest.
        declared_transformations: ordered transformation ids the manifest
            declares were applied to produce this artifact; every one must be
            in the recognized/confirmable set before reconstruction.
    """

    name: str
    payload: bytes
    recorded_sha256: str
    declared_transformations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReplayManifestView:
    """The subset of the canonical manifest the Extractor needs.

    Attributes:
        manifest_digest: the stable canonical digest identifying the edition.
        artifacts: the approved artifacts keyed by name.
        confirmable_transformations: the set of transformation ids this replay
            engine knows how to confirm; a declared transformation outside it
            is treated as an unconfirmed transformation and halts the run.
    """

    manifest_digest: str
    artifacts: Mapping[str, ReplayArtifact]
    confirmable_transformations: frozenset[str]


@dataclass(slots=True)
class ReconstructedFacts:
    """Typed facts reconstructed by a successful verified_replay run.

    ``facts`` is the deterministic, ordered payload decoded from the approved
    artifacts; ``manifest_digest`` ties the reconstruction to exactly one
    edition for non-duplication (Req 2.2, 10.4).
    """

    manifest_digest: str
    facts: list[dict[str, Any]] = field(default_factory=list)
    confirmed_artifacts: list[str] = field(default_factory=list)


class VerifiedReplayExtractor:
    """Reconstruct an edition from approved artifacts with full hash/transform checks.

    The extractor performs **all** verification before it produces any fact, so a
    single mismatch halts the run with the prior edition untouched.
    """

    def extract(
        self,
        manifest: ReplayManifestView,
        decode: ArtifactDecoder | None = None,
    ) -> ReconstructedFacts:
        """Verify every artifact and transformation, then reconstruct facts.

        Args:
            manifest: the canonical manifest view with approved artifacts.
            decode: an optional callable turning verified artifacts into typed
                facts. When omitted, a built-in deterministic decoder is used.

        Raises:
            IngestionError: ``HASH_MISMATCH`` on the first artifact whose
                recomputed digest differs from the recorded one, or whose
                declared transformation cannot be confirmed. The run halts
                before any edition is produced.
        """

        confirmed: list[str] = []
        # Deterministic order so the "first mismatch halts" behaviour is stable.
        for name in sorted(manifest.artifacts):
            artifact = manifest.artifacts[name]
            self._verify_artifact(artifact, manifest.confirmable_transformations)
            confirmed.append(name)

        decoder = decode or _default_decoder
        facts = decoder(manifest)
        return ReconstructedFacts(
            manifest_digest=manifest.manifest_digest,
            facts=list(facts),
            confirmed_artifacts=confirmed,
        )

    @staticmethod
    def _verify_artifact(artifact: ReplayArtifact, confirmable: frozenset[str]) -> None:
        """Recompute+compare the artifact hash and confirm each transformation."""

        recomputed = compute_sha256(artifact.payload)
        if not digests_match(artifact.recorded_sha256, recomputed):
            fail(
                IngestionErrorCode.HASH_MISMATCH,
                affected_unit=f"artifact:{artifact.name}",
                trigger="replay artifact sha256 differs from recorded digest",
                detail={
                    "artifact": artifact.name,
                    "recorded_sha256": artifact.recorded_sha256,
                    "recomputed_sha256": recomputed,
                },
            )
        for transform in artifact.declared_transformations:
            if transform not in confirmable:
                fail(
                    IngestionErrorCode.HASH_MISMATCH,
                    affected_unit=f"artifact:{artifact.name}",
                    trigger="declared transformation could not be confirmed",
                    detail={
                        "artifact": artifact.name,
                        "unconfirmed_transformation": transform,
                    },
                )


def _default_decoder(manifest: ReplayManifestView) -> Sequence[dict[str, Any]]:
    """Deterministically decode verified artifacts into typed facts.

    Artifacts are consumed as UTF-8 JSON lines (one fact object per line) in
    sorted artifact-name order. This keeps reconstruction pure and reproducible;
    richer decoders can be supplied by the caller for a real artifact format.
    """

    facts: list[dict[str, Any]] = []
    for name in sorted(manifest.artifacts):
        payload = manifest.artifacts[name].payload
        if not payload:
            continue
        text = payload.decode("utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                facts.append(obj)
    return facts
