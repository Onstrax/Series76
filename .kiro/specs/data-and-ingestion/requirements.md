# Requirements Document

## Introduction

**Data and Ingestion (Spec 1 of 6).**

This specification defines the **foundational data slice** of the *Series 76 Technical Assistant* (Konecto technical assessment). It governs how the official Series 76 catalog is extracted from source PDFs, manually audited, stored in PostgreSQL with full per-cell provenance, versioned as immutable editions, published atomically, and exposed as a reproducible **golden dataset artifact**.

This spec is **Spec 1 of 6** and is the dependency root for the remaining specs:
`domain-and-tools` (Spec 2), `backend-api-auth-jobs-crypto` (Spec 3), `agent-orchestration-response` (Spec 4), `android-app` (Spec 5), and `evaluation-and-reproducibility` (Spec 6). Those specs read the published catalog and consume the golden dataset; they do not re-derive technical numbers.

> **Important status note:** Nothing in this document asserts that any extraction, audit, benchmark, or ingestion run has been executed. Every statement below is an **acceptance criterion to be met during implementation**, not a claim of completed work. The counts "7 tables / 68 rows / 4 N/A in T03" are treated as an **expected inventory oracle to be confirmed by the manual audit**, never as a pre-verified fact.

### Legend of Requirement Classes

Each requirement is tagged with one or more classes, following the F0/F1 handoff distinction:

- **[ASSESS]** — Mandatory requirement from the Konecto assessment (`assessment-en.pdf`).
- **[APPROVED]** — Approved addition or decision beyond the raw assessment, ratified in the F0–F6 handoff.
- **[DELEGATED]** — Delegated technical detail that Kiro may concretize (exact types, index microstructure, library choices) while preserving the approved invariants.
- **[EXPERIMENT]** — Requires real execution, extraction, audit, or measurement to satisfy; cannot be satisfied by design alone.

### Source-of-Truth Precedence

When sources conflict, the following precedence governs this spec:

1. **`assessment-en.pdf`** — authoritative for external obligations.
2. **`series_76_electric_data.pdf`** — the **only** permitted source of technical numbers and technical conditions for the catalog (pages 1–4, seven tables).
3. **Approved decisions** — the explicitly approved F0–F6 handoff decisions and canonical addenda.
4. **`series_76_summary.pdf`** — business/narrative **context only**; never a source of technical values.

No number may be invented, inferred from part-number substrings, or sourced from the summary PDF or the LLM.

### Non-Goals (Out of Scope for This Spec)

- **No conversation encryption.** AES-256-GCM encryption of conversations, messages, states, checkpoints, and traces is owned by `backend-api-auth-jobs-crypto` (Spec 3). Public technical catalog figures and minimal structural indexes may remain unencrypted here.
- **No agent, LLM orchestration, or LangChain tools.** Domain operations and tools belong to `domain-and-tools` (Spec 2).
- **No HTTP API, authentication, authorization, or job queue.** These belong to Spec 3.
- **No Android UI, caching, or presentation.** These belong to `android-app` (Spec 5).
- **No evaluation/eval-harness thresholds.** These belong to `evaluation-and-reproducibility` (Spec 6), which consumes the golden dataset produced here.

### Traceability Summary

| This spec traces to | Items |
|---|---|
| User stories | US-010, US-011, US-016, US-024, US-031 |
| QA scenarios | QA-01, QA-12, QA-14, QA-15 |
| F1 source-based acceptance tests | F1 §6 (10 tests) and F1 §11 matrix |
| F0 acceptance tests | AT-07 (N/A), AT-12 (24V ingest) |

## Glossary

- **Electric_Data_PDF**: `series_76_electric_data.pdf`, the single authoritative source of technical numbers.
- **Summary_PDF**: `series_76_summary.pdf`, business context only.
- **Assessment_PDF**: `assessment-en.pdf`, external obligations.
- **Ingestion_Pipeline**: The system component that reads source documents, extracts, reconciles, normalizes, verifies, and prepares catalog editions. Operates in `verified_replay` or `fresh_extraction` mode.
- **Verified_Replay_Mode**: Reproducible ingestion mode that reconstructs a catalog edition from approved, versioned artifacts and a manifest, verifies hashes, and makes **no** external AI calls.
- **Fresh_Extraction_Mode**: Ingestion mode that runs local OCR plus Gemini extraction, requires an evaluator-provided `GEMINI_API_KEY`, and reconciles extractor outputs.
- **Catalog_Store**: The PostgreSQL database holding catalog, provenance, ingestion staging, and publication data under logical schemas `catalog`, `provenance`, `ingestion`, `publication`.
- **Catalog_Edition**: An immutable, versioned set of published catalog facts, identified by `edition_id` and a canonical `manifest_digest`.
- **Active_Edition_Pointer**: The single pointer identifying which published edition is currently active for new recommendations.
- **Part_Number (PN)**: A canonical part number within an edition.
- **Service_Performance**: Performance facts (torque, duty, cycles/starts per hour) attributed to a service type.
- **Unqualified_Performance**: Performance facts whose service attribution is not specified in the source (e.g., T03 rows).
- **Operating_Condition**: A frequency context (50 Hz, 60 Hz, explicit/not-specified/not-applicable) for electrical measurements.
- **Per_Cell_Evidence**: A link from a published technical field to the exact source cell(s) and covered row(s) that support it.
- **Manual_Audit**: Human verification of 100% of relevant cells, notes, and N/A values against the Electric_Data_PDF for the initial edition.
- **Golden_Dataset_Artifact**: A versioned artifact enumerating each published technical value with its printed value, unit, source row, and source cell reference, consumed by downstream specs and evaluations.
- **Publisher_Role**: The privileged DB role that activates editions.
- **Ingest_Editor_Role**: The DB role that writes staging and correction data during ingestion.
- **Runtime_Reader_Role**: The DB role used by downstream runtime reads; it has no UPDATE/DELETE on catalog and no staging access.
- **Ingestion_Error**: One of the taxonomy codes: `INPUT_UNREADABLE`, `HASH_MISMATCH`, `TEMPLATE_UNKNOWN`, `SECTION_MISSING`, `ROW_COUNT_MISMATCH`, `CELL_COORDINATE_AMBIGUOUS`, `EXTRACTOR_DISAGREEMENT`, `UNSUPPORTED_UNIT`, `DUPLICATE_IDENTITY`, `SOURCE_CONFLICT`, `EVIDENCE_MISSING`, `CORRECTION_STALE`, `PUBLICATION_FAILED`.

## Requirements

### Requirement 1: Reproducible Pipeline from the Official PDF

**User Story:** As a data owner, I want a versioned ingestion pipeline that processes the official Series 76 electric-data PDF, so that the catalog is reproducible and traceable to its source. *(Traces: US-031, QA-12, QA-14, F1 §6.7, F1 §11 "US-031 ingesta". Classes: [ASSESS], [EXPERIMENT])*

#### Acceptance Criteria

1. THE Ingestion_Pipeline SHALL accept `series_76_electric_data.pdf` as the sole authorized source of technical numbers for catalog values, and SHALL reject any catalog technical value that does not trace to an extracted cell of `series_76_electric_data.pdf`.
2. WHERE context values originate from Summary_PDF, THE Ingestion_Pipeline SHALL store them labeled as non-technical business context and SHALL NOT use Summary_PDF as a source of technical numbers.
3. WHEN a source document is registered, THE Ingestion_Pipeline SHALL record, for that document, a SHA-256 digest, a unique document identifier, the page count, the declared template, and the documentary role (authorized-technical-source or context-only).
4. WHEN the Ingestion_Pipeline processes `series_76_electric_data.pdf` for the initial Catalog_Edition, THE Ingestion_Pipeline SHALL extract 7 source tables, 68 data rows, and 4 N/A values, preserving N/A markers and notes as distinct from numeric values.
5. WHEN the Ingestion_Pipeline runs with an identical input set, an identical manifest, and run mode `verified_replay`, THE Ingestion_Pipeline SHALL NOT create a duplicate Catalog_Edition, SHALL make no external AI model invocation, AND SHALL record one auditable run record identifying the execution, its inputs, and their SHA-256 digests.
6. IF the computed SHA-256 of a registered document does not match its recorded digest, THEN THE Ingestion_Pipeline SHALL report `HASH_MISMATCH` identifying the affected document, SHALL halt publication for that run, AND SHALL leave any previously published Catalog_Edition unchanged.

### Requirement 2: Two Ingestion Modes (verified_replay and fresh_extraction)

**User Story:** As an evaluator, I want a default reproducible mode that needs no external API and an optional fresh-extraction mode, so that I can reconstruct the catalog cleanly or re-derive it from the PDF. *(Traces: US-031, QA-12, F1 §4 "two reconstruction paths", F1 §9.3. Classes: [ASSESS], [APPROVED], [EXPERIMENT])*

#### Acceptance Criteria

1. WHERE the Ingestion_Pipeline runs in Verified_Replay_Mode, THE Ingestion_Pipeline SHALL reconstruct the Catalog_Edition exclusively from the approved, versioned artifacts and the canonical manifest referenced for the run, AND SHALL make zero network calls to any external AI, OCR-as-a-service, or LLM inference endpoint (including Gemini) during the entire run.
2. WHILE running in Verified_Replay_Mode, THE Ingestion_Pipeline SHALL, before reconstruction begins, recompute and compare each artifact's recorded SHA-256 hash and SHALL confirm each declared transformation against the manifest.
3. IF, while running in Verified_Replay_Mode, any recomputed artifact hash does not match its recorded hash or any declared transformation cannot be confirmed, THEN THE Ingestion_Pipeline SHALL halt reconstruction before producing a Catalog_Edition and SHALL report an error indicating the hash or transformation mismatch, leaving any prior published edition unchanged.
4. WHERE the Ingestion_Pipeline runs in Fresh_Extraction_Mode, THE Ingestion_Pipeline SHALL require an evaluator-provided `GEMINI_API_KEY` supplied through the process environment, AND SHALL run local OCR extraction and Gemini extraction followed by reconciliation of their candidates.
5. IF Fresh_Extraction_Mode is requested and no non-empty `GEMINI_API_KEY` is present in the process environment, THEN THE Ingestion_Pipeline SHALL report a configuration error indicating the missing credential and SHALL NOT perform any OCR or Gemini extraction.
6. WHEN a Fresh_Extraction_Mode run completes, THE Ingestion_Pipeline SHALL assign the run exactly one status from the set {`REJECTED`, `QUARANTINED`, `VERIFIED_READY`}, AND SHALL NOT publish OCR or LLM candidates directly as a Catalog_Edition.
7. WHEN a Fresh_Extraction_Mode run reaches status `VERIFIED_READY`, THE Ingestion_Pipeline SHALL hold the run as a publication candidate without activating a Catalog_Edition, AND SHALL activate an edition only through the privileged publication step.
8. THE Ingestion_Pipeline SHALL exclude all secrets, including `GEMINI_API_KEY`, from every produced artifact, manifest, and diagnostic log, AND SHALL provide a `.env.example` that lists required variable names with placeholder values and no real secret values.

### Requirement 3: One-Hundred-Percent Manual Audit of the Initial Edition

**User Story:** As a data owner, I want every relevant cell, note, and N/A of the initial edition verified by hand against the PDF, so that the catalog is trustworthy and not reliant on extractor confidence. *(Traces: US-031, QA-01, QA-14, F1 §4 "initial audit", F1 §9.3, F1 §11 "US-031 ingesta". Classes: [ASSESS], [EXPERIMENT])*

#### Acceptance Criteria

1. FOR the initial Catalog_Edition, THE Manual_Audit SHALL verify one hundred percent of relevant cells, notes, and N/A values against the Electric_Data_PDF, with zero unverified relevant cells, and SHALL record a source cell reference for each verified item.
2. WHEN the Manual_Audit completes, THE Ingestion_Pipeline SHALL record the audited counts of tables, rows, and N/A values as audit-confirmed results rather than assumed values, and SHALL mark the initial edition as audit-complete.
3. THE Ingestion_Pipeline SHALL treat the counts of seven tables, sixty-eight rows, and four N/A values in T03 as an expected audit oracle to confirm; IF the audited counts differ from this oracle, THEN THE Ingestion_Pipeline SHALL report `ROW_COUNT_MISMATCH` or `SECTION_MISSING` as applicable, record the discrepancy for human resolution, and SHALL NOT auto-resolve it.
4. WHEN each audited fact is confirmed or corrected, THE Ingestion_Pipeline SHALL record the reviewer identity, the prior value, the verified value, the justification, the source cell reference, and the source document hash for that fact.
5. IF a recorded correction references a document hash that differs from the current source document hash, THEN THE Ingestion_Pipeline SHALL report `CORRECTION_STALE`, SHALL NOT apply the correction automatically, and SHALL leave the affected edition unchanged.
6. THE initial Catalog_Edition SHALL NOT be eligible for publication until manual-audit coverage is one hundred percent and zero open critical discrepancies remain.

### Requirement 4: Faithful Technical Semantics Preservation

**User Story:** As a technical user, I want the catalog to preserve dual torque units, per-service and per-frequency distinctions, supply-mode distinctions, and notes exactly as printed, so that no technical meaning is lost or fabricated. *(Traces: US-010, US-011, US-016, US-024, AT-12, F1 §6.1–§6.6, QA-01. Classes: [ASSESS], [APPROVED])*

#### Acceptance Criteria

1. THE Ingestion_Pipeline SHALL store each official torque value in both the printed in-lbs figure and the printed Nm figure as two separately retrievable fields, AND SHALL NOT overwrite, round, or replace either printed figure with a value derived by converting the other.
2. WHERE torque or duty is attributed to a specific service type in the source, THE Ingestion_Pipeline SHALL store that performance as a Service_Performance record keyed by that service type, AND SHALL store a distinct Service_Performance record for each distinct service type printed for the same part number.
3. WHERE the source does not attribute torque or duty to any service type (T03), THE Ingestion_Pipeline SHALL store that performance as an Unqualified_Performance record, SHALL store the printed cycles-per-hour and starts-per-hour values as two separately retrievable fields, SHALL NOT create any Service_Performance record for that performance, AND SHALL NOT split the record by On/Off or Modulating supply mode absent printed evidence.
4. WHERE speed, FLA, or LRA is printed for a given frequency, THE Ingestion_Pipeline SHALL store each such value bound to exactly one Operating_Condition whose frequency state is 50 Hz or 60 Hz exactly as printed, AND SHALL NOT bind a value printed under one frequency to the other frequency.
5. IF a speed, FLA, or LRA value is printed without an explicit frequency, THEN THE Ingestion_Pipeline SHALL bind it to an Operating_Condition whose frequency state is not-specified or not-applicable as printed, AND SHALL NOT assign it a 50 Hz or 60 Hz value.
6. THE Ingestion_Pipeline SHALL store the On/Off 24V AC/DC configuration (T04) and the Modulating 24V DC configuration (T05) as two distinct configuration records, AND SHALL NOT merge, deduplicate, or substitute one for the other.
7. THE Ingestion_Pipeline SHALL preserve each certification note and asterisk marker with its original printed text unchanged, AND SHALL associate each note and marker with exactly the set of source rows it covers in the source, without extending it to uncovered rows by forward-fill.
8. IF a value carries a unit that the Ingestion_Pipeline does not recognize, THEN THE Ingestion_Pipeline SHALL report `UNSUPPORTED_UNIT`, SHALL NOT coerce or convert the value, AND SHALL retain the printed value and unit as recorded for human resolution.

### Requirement 5: N/A, NULL, and Merged-Cell Integrity

**User Story:** As a technical user, I want absent values represented honestly and merged cells scoped precisely, so that missing data is never read as zero and coverage is not faked. *(Traces: AT-07, US-024, F1 §6.3, F1 §6.5, QA-01. Classes: [ASSESS], [APPROVED])*

#### Acceptance Criteria

1. WHERE a source cell contains N/A, THE Ingestion_Pipeline SHALL store an explicit not-applicable state for that field AND SHALL NOT store the value as zero, as empty, or as any documented numeric value.
2. WHERE a technical field has no documented value, THE Ingestion_Pipeline SHALL store an explicit absence state that is distinguishable, by direct query of the stored state, from a documented zero and from a not-applicable state.
3. THE Ingestion_Pipeline SHALL record a reason-of-absence indicator for an absent field so that distinct absence reasons are not collapsed into a single undifferentiated null.
4. WHEN a merged source cell covers multiple rows, THE Ingestion_Pipeline SHALL record one explicit coverage link per covered row, AND SHALL NOT propagate the shared value to any row by row-to-row forward-fill outside the recorded coverage links.
5. IF the row scope of a cell cannot be determined unambiguously, THEN THE Ingestion_Pipeline SHALL report `CELL_COORDINATE_AMBIGUOUS`, SHALL NOT assign the value to any row, AND SHALL record the cell coordinates and candidate rows for human resolution.

### Requirement 6: Per-Cell Evidence for Every Published Fact

**User Story:** As an auditor, I want each published technical fact linked to its exact source cell and covered rows, so that any value can be traced back to the PDF. *(Traces: US-031, QA-01, QA-15, F1 §6, F1 §11 "QA integridad". Classes: [ASSESS], [APPROVED])*

#### Acceptance Criteria

1. THE Ingestion_Pipeline SHALL record Per_Cell_Evidence for 100% of published technical facts, where each Per_Cell_Evidence link identifies the one or more source cells and every covered row supporting the fact, together with any source notes associated with those cells.
2. THE Catalog_Store SHALL represent field-to-evidence links through typed bridge tables whose columns are declared foreign keys to the referenced field and evidence records with referential integrity enforced by the store, AND SHALL NOT use a generic `entity_type`/`entity_id` reference that is not constrained by an enforced foreign key.
3. IF a published technical fact has no Per_Cell_Evidence link, THEN THE Ingestion_Pipeline SHALL report `EVIDENCE_MISSING` identifying the unlinked fact, SHALL reject publication of that edition, AND SHALL NOT make that edition available as a Catalog_Edition.
4. WHEN two extractors produce differing normalized values for the same field during Fresh_Extraction_Mode, THE Ingestion_Pipeline SHALL report `EXTRACTOR_DISAGREEMENT` identifying that field, AND SHALL NOT assign the value a verified state or publish it on the basis of extractor confidence alone.

### Requirement 7: PostgreSQL Schemas, Roles, and SQL Safety

**User Story:** As a data architect, I want segregated schemas and least-privilege database roles with no free SQL, so that runtime reads cannot mutate the catalog or see staging. *(Traces: US-031, QA-15, F1 §2, F1 §3 "Seguridad", F1 §11 "QA seguridad". Classes: [ASSESS], [APPROVED], [DELEGATED])*

#### Acceptance Criteria

1. THE Catalog_Store SHALL be PostgreSQL AND SHALL organize data under the logical schemas `catalog`, `provenance`, `ingestion`, and `publication`.
2. THE Catalog_Store SHALL define a Publisher_Role, an Ingest_Editor_Role, and a Runtime_Reader_Role as distinct database roles.
3. THE Runtime_Reader_Role SHALL have no UPDATE or DELETE privilege on catalog data AND SHALL have no read or write access to the ingestion staging schema.
4. THE Catalog_Store SHALL serve runtime reads only through parameterized, typed SQL AND SHALL NOT execute SQL generated freely by a language model.
5. THE Catalog_Store SHALL permit only the Publisher_Role to activate a Catalog_Edition; IF a non-Publisher role attempts to activate an edition, THEN THE Catalog_Store SHALL reject the operation and leave the Active_Edition_Pointer unchanged.
6. IF the edition-validation gate does not complete successfully, THEN THE Ingestion_Pipeline SHALL roll back the activation so that no partially activated edition is left in place.

### Requirement 8: Immutable Editions, Atomic Publication, and Retirement

**User Story:** As a data owner, I want published editions to be immutable and activated atomically, with retirement that preserves history, so that corrections never mutate past data and clients see consistent editions. *(Traces: US-031, QA-14, F1 §3 "Gate transaccional", F1 §6.7, F1 §6.8, F1 §11 "QA inmutabilidad". Classes: [APPROVED], [EXPERIMENT])*

#### Acceptance Criteria

1. WHEN a Catalog_Edition is published, THE Ingestion_Pipeline SHALL treat every fact in that edition as immutable such that no published figure is modified, deleted, or overwritten after publication, AND SHALL require creation of a new edition for any subsequent correction.
2. WHEN publication succeeds, THE Ingestion_Pipeline SHALL promote the Active_Edition_Pointer to the new edition as a single all-or-nothing transition, such that any concurrent reader observes either exactly the prior active edition or exactly the new active edition and never a partial, mixed, or absent pointer state.
3. IF publication fails for any reason, THEN THE Ingestion_Pipeline SHALL report `PUBLICATION_FAILED` AND SHALL leave the prior active edition and its Active_Edition_Pointer unchanged, with no facts from the failed edition becoming active or queryable.
4. WHEN an edition is retired, THE Ingestion_Pipeline SHALL block generation of new recommendations based on that edition AND SHALL retain the retired edition, its facts, and its event history unchanged for already-pinned sessions and audit.
5. IF an edition's transactional validation gate detects one or more unresolved critical inconsistencies, THEN THE Ingestion_Pipeline SHALL NOT activate that edition AND SHALL leave the currently active edition unchanged.
6. IF a recommendation is requested against a retired edition, THEN THE Ingestion_Pipeline SHALL return an indication that the edition is retired AND SHALL NOT fabricate or emit a new recommendation from that edition, while still permitting read access to previously recorded historical responses pinned to that edition.
7. WHEN an ingestion run reproduces inputs identical to those of an already-published edition (same source document fingerprints and manifest), THE Ingestion_Pipeline SHALL record the new run without creating a duplicate edition AND SHALL leave the existing published edition and the Active_Edition_Pointer unchanged.

### Requirement 9: Reconciliation and Ingestion Error Taxonomy

**User Story:** As a data owner, I want a defined set of ingestion error states, so that extraction and publication failures are classified consistently and never silently ignored. *(Traces: US-031, QA-15, F1 §9.4, F1 §9.2. Classes: [APPROVED], [DELEGATED])*

#### Acceptance Criteria

1. THE Ingestion_Pipeline SHALL classify ingestion failures using the taxonomy `INPUT_UNREADABLE`, `HASH_MISMATCH`, `TEMPLATE_UNKNOWN`, `SECTION_MISSING`, `ROW_COUNT_MISMATCH`, `CELL_COORDINATE_AMBIGUOUS`, `EXTRACTOR_DISAGREEMENT`, `UNSUPPORTED_UNIT`, `DUPLICATE_IDENTITY`, `SOURCE_CONFLICT`, `EVIDENCE_MISSING`, `CORRECTION_STALE`, and `PUBLICATION_FAILED`.
2. WHEN any ingestion failure occurs, THE Ingestion_Pipeline SHALL assign exactly one taxonomy code from criterion 1 to that failure and SHALL NOT discard, suppress, or complete the affected unit as successful.
3. IF a source document cannot be opened or parsed into its declared format, THEN THE Ingestion_Pipeline SHALL report `INPUT_UNREADABLE`, halt processing of that document, and leave any previously published edition unchanged.
4. IF the declared template identifier of a source document does not match any template in the recognized template set, THEN THE Ingestion_Pipeline SHALL report `TEMPLATE_UNKNOWN` and halt processing of that document.
5. IF two canonical part numbers resolve to the same identity value within one edition, THEN THE Ingestion_Pipeline SHALL report `DUPLICATE_IDENTITY` and reject the affected edition build.
6. IF reconciliation finds a conflict between sources for the same fact that remains unresolved after the reconciliation step completes, THEN THE Ingestion_Pipeline SHALL report `SOURCE_CONFLICT` AND SHALL quarantine the fact rather than publish it.
7. IF an edition activation does not complete atomically, THEN THE Ingestion_Pipeline SHALL report `PUBLICATION_FAILED` and leave the previously active edition intact.
8. WHEN any ingestion error is reported, THE Ingestion_Pipeline SHALL record diagnostic detail identifying the error code, the affected unit, and the trigger condition, without recording secrets.

### Requirement 10: Golden Dataset Artifact

**User Story:** As a downstream consumer (domain tools and evaluations), I want a versioned golden dataset enumerating each published value with its printed value, unit, row, and cell reference, so that I can verify answers against source truth without re-reading the PDF. *(Traces: US-010, US-011, US-016, US-024, QA-01, QA-12, F1 §6 "golden data", F1 §11 "US-018/QA reproducibilidad". Classes: [APPROVED], [EXPERIMENT])*

#### Acceptance Criteria

1. WHEN a Catalog_Edition is published, THE Ingestion_Pipeline SHALL produce exactly one versioned Golden_Dataset_Artifact for that edition and assign it a monotonically increasing version identifier unique within the edition.
2. WHEN the Golden_Dataset_Artifact is produced, THE Ingestion_Pipeline SHALL record, for 100% of the published technical values of the edition, four non-null attributes per value: the printed value, the unit, the source row reference, and the source cell reference.
3. WHEN recording a value whose state is N/A or absent, THE Ingestion_Pipeline SHALL store the N/A state and the absent state as two distinct explicit state markers AND SHALL NOT store either state as the numeric value zero or as an empty or missing attribute.
4. WHEN the Golden_Dataset_Artifact is produced, THE Ingestion_Pipeline SHALL bind the artifact to exactly one edition by recording that edition's `edition_id` and `manifest_digest`, so that downstream specs consume a value set bound to a single specific edition.
5. WHEN the published edition is reconstructed through Verified_Replay_Mode using only approved artifacts, THE Ingestion_Pipeline SHALL yield a set of published values that is equal to the Golden_Dataset_Artifact set, where equality requires identical value count with no additions or omissions and, for every published value, identical printed value, unit, source row reference, and source cell reference (round-trip property).
6. IF the Verified_Replay_Mode reconstruction yields a value set that differs from the Golden_Dataset_Artifact in value count, printed value, unit, source row reference, or source cell reference, THEN THE Ingestion_Pipeline SHALL reject the reconstruction, report a round-trip mismatch indication identifying the differing values, and SHALL NOT alter or republish the existing Golden_Dataset_Artifact.

### Requirement 11: Edition Isolation Across Values

**User Story:** As a technical user, I want every measurement bound to a single edition and condition, so that values from different editions or conditions are never mixed. *(Traces: US-010, US-016, F1 §6.10, F1 §11. Classes: [APPROVED])*

#### Acceptance Criteria

1. WHEN a Service_Performance, Unqualified_Performance, or electrical_measurement record is created or updated, THE Catalog_Store SHALL bind that record to exactly one Catalog_Edition (via its `edition_id`) and, for electrical_measurement, to exactly one operating_condition (via its `condition_id`).
2. WHEN assembling a published value set, THE Ingestion_Pipeline SHALL include only measurements whose `edition_id` matches a single target Catalog_Edition and whose operating_condition belongs to that same edition.
3. IF, while assembling a published value set, a measurement with an `edition_id` or operating_condition differing from the target edition is encountered, THEN THE Ingestion_Pipeline SHALL exclude that measurement from the value set and record an error indicating the edition or condition mismatch, leaving the target edition's existing records unchanged.
4. WHERE a part number appears in more than one Catalog_Edition, THE Catalog_Store SHALL maintain a unique canonical part number per edition by enforcing the constraint `UNIQUE(edition_id, canonical_pn)`.
5. IF an insert or update would create a duplicate `(edition_id, canonical_pn)` pair, THEN THE Catalog_Store SHALL reject the operation and return an error indicating the uniqueness violation, preserving the previously stored canonical part number.
