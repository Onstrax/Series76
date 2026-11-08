# Requirements Document

## Introduction

**Domain and Tools (Spec 2 of 6).**

This specification defines the **deterministic domain and tools layer** of the *Series 76 Technical Assistant* (Konecto technical assessment). It sits directly on top of the published catalog produced by `data-and-ingestion` (Spec 1) and exposes a set of **pure domain model types**, **read-only typed repositories**, **domain operations** (`get_part`, `search_parts`, `get_source_notes`), **deterministic services** (`rank_candidates`, `compare_parts`, `convert_units`), and **custom LangChain Tools** that make tabular catalog data queryable by an agent — without the agent ever generating SQL or dictating a technical number.

Every technical value this layer returns is read from the published catalog or produced by a deterministic derivation over published values. **This layer never invents a number.** It is the authoritative source of the "same verified figures" that the final `answer` and the structured response blocks will later share (a contract consumed by `agent-orchestration-response`, Spec 4).

This spec is **Spec 2 of 6**. It **depends on** `data-and-ingestion` (Spec 1) — specifically the published `Catalog_Store` surface, the `Runtime_Reader_Role`, the immutable `Catalog_Edition` facts, the per-cell evidence links, and the `Golden_Dataset_Artifact`. It is **consumed by** `backend-api-auth-jobs-crypto` (Spec 3, which wraps these operations in HTTP/auth/jobs) and `agent-orchestration-response` (Spec 4, which drives the agent, interpretation, confirmation, and response composition). It is **evaluated by** `evaluation-and-reproducibility` (Spec 6), which resolves the empirical tool-set A/B comparison.

> **Important status note:** Nothing in this document asserts that any benchmark, A/B tool comparison, model evaluation, or empirical measurement has been executed. The A/B comparison between tool set A (generic) and tool set B (specialized) is an **acceptance criterion / experiment to be run in Spec 6**, never a pre-decided result. No winner is declared here.

### Legend of Requirement Classes

Each requirement is tagged with one or more classes, following the F0–F6 handoff distinction:

- **[ASSESS]** — Mandatory requirement from the Konecto assessment (`assessment-en.pdf`).
- **[APPROVED]** — Approved addition or decision beyond the raw assessment, ratified in the F0–F6 handoff.
- **[DELEGATED]** — Delegated technical detail that Kiro may concretize (exact types, library choices, index microstructure, DTO shape) while preserving the approved invariants.
- **[EXPERIMENT]** — Requires real execution, benchmark, or measurement to satisfy; cannot be satisfied by design alone.

### Source-of-Truth Precedence

When sources conflict, the following precedence governs this spec:

1. **`assessment-en.pdf`** — authoritative for external obligations (mandatory custom LangChain tool, PostgreSQL, no free text-to-SQL).
2. **Published Catalog (Spec 1)** — the catalog surface published by `data-and-ingestion`, which itself derives technical numbers **only** from `series_76_electric_data.pdf`. This layer treats the published catalog as the single source of technical numbers and conditions.
3. **Approved decisions** — the explicitly approved F0–F6 handoff decisions and canonical addenda (F2 §4 AST, §5 tools, §6 verification).
4. **`series_76_summary.pdf`** — business/narrative **context only**; never a source of technical values.

No number returned by this layer may be invented, inferred from part-number substrings, sourced from the summary PDF, or produced by an LLM.

### Non-Goals (Out of Scope for This Spec)

- **No LLM interpretation, reasoning, or agent orchestration.** Intent interpretation, filter-AST authoring from natural language, plan versioning/confirmation, multi-turn context, and response composition belong to `agent-orchestration-response` (Spec 4). This layer only *executes* a typed, already-validated request and returns typed facts.
- **No HTTP API, authentication, authorization logic, job queue, or cryptography.** Endpoints, JWT/session, RBAC/ownership enforcement, durable per-session queues, and AES-256-GCM belong to `backend-api-auth-jobs-crypto` (Spec 3). This layer *receives* a server-injected authorized edition and permission context; it does not establish identity or trust.
- **No presentation or Android.** The "maximum 3 full cards" chat payload rule, dual-of-two comparison view, bar charts, highlights, and local caching belong to `android-app` (Spec 5). This layer *exposes* the full matched set, totals, and comparable conditions; it does not decide rendering limits.
- **No eval harness, golden-set thresholds, or benchmark conclusions.** The A/B tool comparison, model selection, accuracy thresholds, and cost gates belong to `evaluation-and-reproducibility` (Spec 6). This layer *provides* the deterministic oracle behavior those evals measure.
- **No ingestion, extraction, audit, or publication.** Extraction, manual audit, edition publication, and the golden dataset artifact belong to `data-and-ingestion` (Spec 1). This layer only *reads* the published surface.

### Traceability Summary

| This spec traces to | Items |
|---|---|
| User stories | US-010, US-011, US-014, US-015, US-016, US-017, US-018, US-019, US-020, US-024 |
| QA scenarios | QA-01, QA-02, QA-03 |
| F0 acceptance tests | AT-01 (contextual lookup), AT-02 (logical filters), AT-03 (delegation), AT-04 (ranking priority), AT-06 (comparison), AT-07 (N/A), AT-08 (out of document) |
| F1 contracts | F1 §5 (domain operations), F1 §10 (operation contract), F1 §11 (matrix) |
| F2 contracts | F2 §4 (AST and query capabilities), F2 §5 (tool contract A/B), F2 §6 (verification of visible output as it pertains to deterministic facts) |

## Glossary

- **Published_Catalog**: The read surface published by `data-and-ingestion` (Spec 1), comprising the active and historical immutable `Catalog_Edition` facts, their per-cell evidence, and the golden dataset. The sole source of technical numbers for this layer.
- **Catalog_Edition**: An immutable, versioned set of published catalog facts identified by `edition_id` and a canonical `manifest_digest` (defined by Spec 1).
- **Runtime_Reader_Role**: The least-privilege PostgreSQL role (defined by Spec 1) used by this layer's repositories; it has no UPDATE/DELETE on catalog data and no access to the ingestion staging schema.
- **Domain_Model**: The set of pure, in-memory domain types (part number, configuration, service performance, unqualified performance, operating condition, measurement, note, evidence reference, data status) exposed by this layer.
- **Typed_Repository**: A read-only data-access component that serves catalog reads exclusively through parameterized, typed SQL bound to a single pinned edition.
- **Pinned_Edition**: The `edition_id` supplied by the caller (server-injected) that scopes every read of a single operation to exactly one `Catalog_Edition`.
- **Domain_Operation**: A business operation over the Published_Catalog: `get_part`, `search_parts`, or `get_source_notes`.
- **Deterministic_Service**: A pure computation over already-retrieved facts: `rank_candidates`, `compare_parts`, or `convert_units`. Not necessarily exposed as an LLM tool.
- **Filter_AST**: A typed, validated filter expression with `AND`/`OR`/`NOT` grouping, field predicates over an allowlist, typed operators, ranges (inclusive/exclusive), and units. Raw SQL is never accepted.
- **Service_Performance**: A performance fact (torque, duty, cycles/starts per hour) attributed to a specific service type (defined by Spec 1).
- **Unqualified_Performance**: A performance fact whose service attribution is not specified in the source (e.g., T03 rows) (defined by Spec 1).
- **Operating_Condition**: A frequency context (50 Hz, 60 Hz, not-specified, not-applicable) for electrical measurements (defined by Spec 1).
- **Data_Status**: The documented state of a technical fact: one of `AVAILABLE`, `NOT_APPLICABLE` (N/A), `NOT_DOCUMENTED`, `NOT_LISTED`, or `UNVERIFIED`.
- **Requirement_Group**: One of the four physical requirement groups needed for a verified recommendation: environment/enclosure, power/supply, service type, required torque.
- **Coverage_Status**: The per-group recommendation-completeness state derived from a request: one of `SPECIFIED`, `NO_PREFERENCE`, `UNKNOWN`, `DELEGATED`, `UNSPECIFIED`, or `CONFLICTING`.
- **Evidence_Reference**: A reference linking a returned technical fact to its source cell(s) and covered row(s) in the Published_Catalog.
- **Custom_Tool**: A LangChain tool exposed to the agent that queries tabular catalog data through this layer. Includes model-visible typed inputs and server-injected inputs.
- **Tool_Set_A**: The baseline tool set — a single generic `query_parts` tool with a discriminated GET/SEARCH payload.
- **Tool_Set_B**: The candidate specialized tool set — `get_part_details`, `search_parts`, and a conditional `get_source_notes`.
- **Server_Injected_Input**: An input supplied by the server (Spec 3), never by the model: the authorized `edition_id`, permission context, result limits, and `trace_id`.
- **Semantic_Failure_Code**: A typed non-exception business outcome: one of `INVALID_PN`, `PART_NOT_LISTED`, `N_A`, `NO_RESULTS`, `NOT_COMPARABLE`, `SOURCE_WITHDRAWN`, or `INVALID_FILTER`.
- **Derived_Value**: A value produced by a deterministic computation (e.g., a unit conversion) over documented values, labeled as derived with its formula and precision, and never substituted for an official documented figure.

## Requirements

### Requirement 1: Read-Only Typed Repositories over the Published Catalog

**User Story:** As a backend integrator, I want domain reads served only through least-privilege, parameterized, edition-pinned SQL, so that catalog data can never be mutated, cross-contaminated, or queried by model-generated SQL. *(Traces: US-010, US-011, F1 §2–§3, F2 §3, QA-01. Classes: [ASSESS], [APPROVED], [DELEGATED])*

#### Acceptance Criteria

1. THE Typed_Repository SHALL serve every catalog read through parameterized, typed SQL only, AND SHALL NOT execute any SQL string generated by a language model.
2. IF a read request carries a non-parameterized SQL string or any SQL string originating from a language model, THEN THE Typed_Repository SHALL reject the request without executing it, SHALL return a typed error indicating a disallowed-SQL violation, AND SHALL leave the Published_Catalog unchanged.
3. THE Typed_Repository SHALL connect to the Published_Catalog using the Runtime_Reader_Role, which has no UPDATE or DELETE privilege on catalog data and no read or write access to the ingestion staging tables (`ingestion_run`, `staging_extraction_candidate`, `staging_discrepancy`).
4. WHEN a Domain_Operation is invoked, THE Typed_Repository SHALL scope every read of that invocation to exactly one Pinned_Edition resolved from the caller's validated session, AND SHALL NOT accept a Pinned_Edition supplied as a language-model argument.
5. IF a Domain_Operation is invoked without exactly one resolvable Pinned_Edition, or references a withdrawn or non-published edition, THEN THE Typed_Repository SHALL reject the read, SHALL return a typed error indicating an unavailable or unresolved edition, AND SHALL NOT return any catalog facts.
6. IF a read within a single Domain_Operation would combine facts from more than one Catalog_Edition, THEN THE Typed_Repository SHALL reject the read AND SHALL NOT return a value set mixing editions.
7. THE Domain_Model SHALL represent every returned technical fact together with its Data_Status, drawn from exactly one of AVAILABLE, NOT_APPLICABLE, NOT_DOCUMENTED, NOT_LISTED, or UNVERIFIED, AND its Evidence_Reference, such that a documented value (AVAILABLE), an N/A state (NOT_APPLICABLE), and an absent state (NOT_DOCUMENTED or NOT_LISTED) are distinguishable by direct inspection of the returned type.
8. THE Typed_Repository SHALL NOT read from, write to, or expose the ingestion staging tables or any edition that is not in a published state.

### Requirement 2: Exact Part-Number Lookup (`get_part`)

**User Story:** As a technical user, I want an exact part-number lookup that is service- and frequency-aware and never silently substitutes a similar part, so that I see the documented facts for exactly the part I asked about. *(Traces: US-010, US-024, AT-01, QA-01. Classes: [ASSESS], [APPROVED])*

#### Acceptance Criteria

1. WHEN `get_part` is invoked with an exact part number that resolves to a single canonical part number present in the Pinned_Edition, THE Domain_Operation SHALL return status `PART_FOUND` with the documented configurations, Service_Performance records, Unqualified_Performance records, Operating_Condition-bound measurements, and notes, each fact carrying its Data_Status and Evidence_Reference.
2. WHEN `get_part` is invoked with an explicit service type or frequency, THE Domain_Operation SHALL return the facts bound to that service type or to that explicit Operating_Condition, with each returned measurement labeled with its service and frequency.
3. WHEN `get_part` is invoked without a service type or frequency and multiple documented measurements remain applicable, THE Domain_Operation SHALL return each applicable measurement labeled with its service and frequency AND SHALL NOT select one measurement silently.
4. IF `get_part` is invoked with a part number that does not conform to the canonical part-number format of the Pinned_Edition, THEN THE Domain_Operation SHALL return the Semantic_Failure_Code `INVALID_PN` identifying the offending input AND SHALL NOT return facts for any other part number.
5. IF `get_part` is invoked with a well-formed part number absent from the Pinned_Edition, THEN THE Domain_Operation SHALL return the Semantic_Failure_Code `PART_NOT_LISTED` AND SHALL NOT assert that the product does not exist commercially AND SHALL NOT substitute or suggest a similar part number.
6. WHERE a requested technical field of a listed part carries an N/A state in the Published_Catalog, THE Domain_Operation SHALL return that field with Data_Status `NOT_APPLICABLE` AND SHALL NOT return the field as zero, empty, or any documented numeric value, and SHALL NOT convert the N/A state into a value for sorting, comparison, or display.
7. WHERE a requested technical field of a listed part has no documented value, THE Domain_Operation SHALL return that field with Data_Status `NOT_DOCUMENTED`, held as a distinct state that is not collapsible into `NOT_APPLICABLE`.

### Requirement 3: Filtered Search (`search_parts`)

**User Story:** As a technical user, I want to search actuators with grouped boolean filters, ranges, and units, so that only parts matching my logical criteria are returned without altering the intended meaning. *(Traces: US-011, US-018, AT-02, QA-01, QA-02, F2 §4. Classes: [ASSESS], [APPROVED], [DELEGATED])*

#### Acceptance Criteria

1. WHEN `search_parts` is invoked with a Filter_AST, THE Domain_Operation SHALL evaluate every `AND`, `OR`, and `NOT` node strictly according to the explicit parenthetical grouping encoded in the Filter_AST, such that a part is included if and only if it satisfies the fully grouped expression; for an expression of the form `A AND (B OR C)` the returned set SHALL equal exactly `{ part : A ∧ (B ∨ C) }`, and each `NOT` node SHALL exclude exactly the parts satisfying its negated subexpression, with no implicit re-association or precedence substitution.
2. WHEN a Filter_AST predicate specifies a numeric range, THE Domain_Operation SHALL treat an inclusive bound as satisfied when the candidate value equals the bound and an exclusive bound as not satisfied when the candidate value equals the bound, applying each bound exactly as typed in the predicate.
3. WHEN a Filter_AST predicate specifies a value carrying a unit, THE Domain_Operation SHALL match the candidate value only under the predicate's declared unit and SHALL reject comparison against a candidate field whose documented unit is non-convertible to that declared unit rather than matching it.
4. WHERE a filtered field of a candidate carries an N/A state or has no documented value, THE Domain_Operation SHALL treat that field as not satisfying any numeric predicate, SHALL NOT coerce an N/A or absent value to zero or any default to satisfy a filter, and SHALL keep the N/A state and the absent (not-documented) state distinguishable from each other in the candidate's returned metadata.
5. WHEN `search_parts` returns results, THE Domain_Operation SHALL return a `total_matches` count equal to the exact number of parts in the Pinned_Edition satisfying the Filter_AST, AND SHALL make every matched part number retrievable through the cursor- or page-based transport such that iterating the transport to exhaustion enumerates all `total_matches` part numbers with none silently omitted and none fabricated.
6. WHEN `search_parts` returns results, THE Domain_Operation SHALL place a candidate in the verified set only if it satisfies every verifiable hard constraint of the Filter_AST, AND SHALL place in a separate preliminary-or-indeterminate set every candidate that is otherwise matched but has at least one relevant constraint field that is missing, N/A, or non-comparable, such that no indeterminate candidate appears in the verified set.
7. WHEN the Filter_AST matches no part in the Pinned_Edition, THE Domain_Operation SHALL return `NO_RESULTS` as a successful business result that reports the applied filters and a `total_matches` of zero, distinct and separately identifiable from any technical failure.
8. IF a Filter_AST is structurally invalid, references a field outside the allowlist, or carries a unit or operator incompatible with its referenced field, THEN THE Domain_Operation SHALL return the Semantic_Failure_Code `INVALID_FILTER` with an indication identifying the offending predicate, SHALL NOT execute the search, and SHALL return no `total_matches` and no matched part numbers.
9. THE Domain_Operation SHALL expose the complete matched set and `total_matches` without applying any chat payload card limit, AND the "maximum three full cards" presentation rule SHALL remain owned by `android-app` (Spec 5) and SHALL NOT be enforced by this layer.

### Requirement 4: Deterministic Ranking (`rank_candidates`)

**User Story:** As an engineer, I want a reproducible lexicographic ranking by my explicit priorities with a stable tiebreak, so that recommendations are justifiable and never ordered by a non-comparable or fabricated metric. *(Traces: US-016, US-017, AT-04, QA-01, QA-03, F2 §4. Classes: [APPROVED])*

#### Acceptance Criteria

1. WHEN `rank_candidates` is invoked with an eligible candidate set and an explicit, confirmed priority ordering, THE Deterministic_Service SHALL order candidates lexicographically by those priorities in the order given, applying each priority's specified comparison direction, AND SHALL be reproducible such that identical inputs produce an identical ordering on every invocation.
2. WHEN two candidates compare equal across all applied priorities, THE Deterministic_Service SHALL resolve the tie deterministically by Base Part Number using a single fixed ascending lexical ordering, such that the resulting relative order of the tied candidates is identical on every invocation with identical inputs.
3. WHERE a candidate's value for a priority metric carries an N/A or absent state, THE Deterministic_Service SHALL exclude that value from the ordering comparison for that priority, SHALL NOT coerce the N/A or absent value to zero or any substitute numeric value for ranking, AND SHALL place every candidate whose value is excluded for a given priority after all candidates that have a comparable value for that priority in the ordering.
4. IF a priority metric is not comparable across the candidate set because of differing service, frequency, supply, or unit context, THEN THE Deterministic_Service SHALL NOT rank candidates by that metric, SHALL NOT declare a winner on the basis of that metric, AND SHALL return the affected candidates in a distinct indeterminate group that is identified separately from the ranked candidates in the output.
5. WHEN `rank_candidates` is invoked in top-1 mode, THE Deterministic_Service SHALL return the single winning candidate together with the total count of eligible candidates only, AND SHALL NOT return the nominal list of the other eligible part numbers in that mode.
6. WHEN `rank_candidates` is invoked in top-1 mode, THE Deterministic_Service SHALL return a winner identical to the first element of the full ranking computed from the same candidate set and priorities.
7. THE Deterministic_Service SHALL NOT accept a model-provided `sort_hint` as an authoritative priority, AND SHALL treat ranking priorities as authoritative only when supplied as explicit, confirmed input.
8. IF `rank_candidates` is invoked with an empty eligible candidate set or without an explicit, confirmed priority ordering, THEN THE Deterministic_Service SHALL NOT produce a ranking or declare a winner, SHALL return an indication that ranking could not be performed identifying the unmet precondition, AND SHALL leave the input candidate set unmodified.

### Requirement 5: Deterministic Comparison (`compare_parts`)

**User Story:** As a user, I want to compare up to three parts side by side with their conditions and units exposed, so that I never see heterogeneous metrics presented as an equivalent comparison. *(Traces: US-019, US-020, AT-06, QA-01. Classes: [APPROVED])*

#### Acceptance Criteria

1. WHEN `compare_parts` is invoked with between two and three distinct part numbers that all belong to the same Catalog_Edition and are all listed in that edition, THE Deterministic_Service SHALL return their documented facts side by side with each fact's Operating_Condition, service context, and unit exposed.
2. IF `compare_parts` is invoked with part numbers from more than one Catalog_Edition, THEN THE Deterministic_Service SHALL reject the comparison AND SHALL return an indication of the edition mismatch, AND SHALL NOT return any side-by-side fact set.
3. WHERE two metrics belong to compatible service, frequency, supply, and unit contexts, THE Deterministic_Service SHALL present them as a comparable pair, AND WHERE those contexts are not compatible, THE Deterministic_Service SHALL mark the pair `NOT_COMPARABLE` and attach a condition-mismatch warning.
4. WHEN FLA values originate from heterogeneous supply configurations, THE Deterministic_Service SHALL present each value with its supply condition AND SHALL NOT present the comparison as a lower-energy-consumption or efficiency claim.
5. WHERE a compared field carries an N/A or absent state, THE Deterministic_Service SHALL present that field with its explicit state AND SHALL NOT render it as zero AND SHALL NOT consider it a comparison winner.
6. THE Deterministic_Service SHALL NOT declare a winner for any pair marked `NOT_COMPARABLE`, AND the dual-selection-of-two comparison view is a presentation concern owned by `android-app` (Spec 5).
7. IF `compare_parts` is invoked with fewer than two part numbers, with more than three part numbers, with duplicate part numbers, or with any part number not listed in the pinned Catalog_Edition, THEN THE Deterministic_Service SHALL reject the comparison AND SHALL return a typed failure indication identifying the offending input, AND SHALL NOT return a partial side-by-side fact set.
8. WHEN `compare_parts` is invoked more than once with the same set of part numbers against the same Catalog_Edition, THE Deterministic_Service SHALL return identical comparison results, including identical pair comparability states, identical warnings, and identical ordering of parts and fields.

### Requirement 6: Deterministic Unit Conversion (`convert_units`)

**User Story:** As a user, I want derived unit conversions computed deterministically and clearly labeled, so that converted figures never overwrite or masquerade as official documented values. *(Traces: US-024, QA-01, F1 §10 "convert_units". Classes: [APPROVED], [DELEGATED])*

#### Acceptance Criteria

1. WHEN `convert_units` converts a documented value between a compatible unit pair, THE Deterministic_Service SHALL compute the result using Decimal arithmetic AND SHALL return it as a Derived_Value labeled with its conversion formula and with its applied rounding precision expressed as a fixed number of decimal places.
2. WHERE a value is documented in two official units (for example the printed in-lbs and Nm torque figures), THE Deterministic_Service SHALL preserve both original documented figures AND SHALL NOT overwrite, round, or replace either documented figure with a value derived by converting the other.
3. THE Deterministic_Service SHALL NOT substitute a Derived_Value for an official documented value in any returned fact.
4. IF `convert_units` is invoked with an incompatible unit pair, or with a source magnitude that is missing, non-numeric, or outside the conversion's defined domain, THEN THE Deterministic_Service SHALL return an explicit conversion error indicating the cause, SHALL NOT return a converted value, AND SHALL leave the source value unchanged.

### Requirement 7: Recommendation Completeness Primitives (Four Requirement Groups)

**User Story:** As an engineer, I want the layer to report per-group coverage of the four physical requirements, so that a recommendation is marked verified only when environment, supply, service type, and torque are all satisfied. *(Traces: US-014, US-015, US-016, AT-03, QA-03, F2 §1(6). Classes: [APPROVED])*

#### Acceptance Criteria

1. WHEN recommendation-completeness is evaluated for a request, THE Domain layer SHALL report exactly one Coverage_Status for each of the four Requirement_Groups (environment/enclosure, power/supply, service type, required torque), drawn from `SPECIFIED`, `NO_PREFERENCE`, `UNKNOWN`, `DELEGATED`, `UNSPECIFIED`, or `CONFLICTING`.
2. WHEN all four Requirement_Groups report a Coverage_Status of `SPECIFIED` and each group's constraint resolves against at least one catalog-backed attribute with a non-empty matching result in the Published_Catalog, THE Domain layer SHALL classify a resulting candidate set as eligible for a `verified` recommendation.
3. IF at least one Requirement_Group reports a Coverage_Status other than `SPECIFIED`, THEN THE Domain layer SHALL classify a resulting candidate set as `preliminary` AND SHALL report the set of Requirement_Groups whose Coverage_Status is not `SPECIFIED`.
4. IF any Requirement_Group reports a Coverage_Status of `CONFLICTING`, THEN THE Domain layer SHALL classify the resulting candidate set as `preliminary`, SHALL include that group in the reported unmet-group set, AND SHALL NOT classify the candidate set as eligible for a `verified` recommendation.
5. WHERE a Requirement_Group's Coverage_Status is `DELEGATED`, THE Domain layer SHALL treat the delegation as a preference input AND SHALL NOT synthesize a physical condition value that is not present in the source data for that Requirement_Group, even when the user delegates the choice.
6. THE Domain layer SHALL evaluate each of the four Requirement_Groups individually and independently AND SHALL NOT mark a candidate set `verified` unless all four groups report `SPECIFIED`.
7. THE Domain layer SHALL provide these completeness and eligibility primitives as deterministic outputs only, AND the final recommendation decision and its composition are owned by `agent-orchestration-response` (Spec 4).

### Requirement 8: Source Notes (`get_source_notes`)

**User Story:** As a user, I want literal source notes returned with their exact scope, so that certification notes are never inferred or extended beyond the rows they cover. *(Traces: US-023 context, AT-08, QA-01, F2 §5. Classes: [APPROVED], [DELEGATED])*

#### Acceptance Criteria

1. WHEN `get_source_notes` is invoked for a part number, configuration, fact, or section within the Pinned_Edition, THE Domain_Operation SHALL return the literal note text unchanged together with its Evidence_Reference, and with its covered scope equal to exactly the set of source rows the note covers in the Published_Catalog.
2. WHERE more than one note applies to the requested target, THE Domain_Operation SHALL return each applicable note as a separate item with its own literal text and covered scope AND SHALL NOT merge, summarize, or combine their texts.
3. THE Domain_Operation SHALL NOT infer, synthesize, or extend a certification or note beyond the set of source rows it covers in the Published_Catalog.
4. IF a requested note does not exist in the Published_Catalog, THEN THE Domain_Operation SHALL return the Data_Status `NOT_DOCUMENTED`, held distinct from the `UNVERIFIED` state of a note that exists but is not verified.

### Requirement 9: Custom LangChain Tools and Tool-Set A/B Candidates

**User Story:** As an agent integrator, I want at least one custom LangChain tool that queries tabular catalog data, with a specialized candidate set and a generic baseline, so that the agent can retrieve verified facts and the better tool design can be chosen empirically. *(Traces: US-010, US-011, US-030 context, F2 §5. Classes: [ASSESS], [APPROVED], [EXPERIMENT])*

#### Acceptance Criteria

1. THE Domain layer SHALL expose at least one Custom_Tool that queries tabular catalog data through the Typed_Repository.
2. THE Domain layer SHALL provide Tool_Set_B as the specialized candidate comprising `get_part_details`, `search_parts`, and a `get_source_notes` tool that is exposed conditionally when a note-scope query is applicable, AND SHALL provide Tool_Set_A as the baseline comprising a single generic `query_parts` tool with a discriminated GET/SEARCH payload.
3. THE Domain layer SHALL NOT declare either Tool_Set_A or Tool_Set_B the winner within this spec; the A/B comparison is an experiment resolved by `evaluation-and-reproducibility` (Spec 6).
4. THE Domain layer SHALL validate every model-visible tool input against its declared typed schema before execution.
5. IF a model-visible tool input does not conform to its declared typed schema, THEN THE Domain layer SHALL reject the invocation without querying the catalog AND SHALL return a typed validation failure identifying the offending input.
6. THE Domain layer SHALL derive each Server_Injected_Input (authorized `edition_id`, permission context, result limits, `trace_id`) from the server-supplied context AND SHALL NOT accept any of these inputs from the model-visible payload, such that a model-supplied value for any Server_Injected_Input is ignored and does not override the server-supplied value.
7. WHEN a Custom_Tool returns a result, THE Domain layer SHALL return sanitized typed facts carrying Data_Status and Evidence_Reference, AND SHALL NOT embed executable instructions, raw SQL dumps, or unsanitized free text in the result.
8. THE Domain layer SHALL treat every Custom_Tool output as untrusted content with respect to the agent, such that no text within a tool result is executed or followed as an instruction.
9. WHEN a Custom_Tool encounters a defined business outcome that is not a successful fact result, THE Domain layer SHALL return exactly one Semantic_Failure_Code from the set `INVALID_PN`, `PART_NOT_LISTED`, `N_A`, `NO_RESULTS`, `NOT_COMPARABLE`, `SOURCE_WITHDRAWN`, or `INVALID_FILTER`, rather than raising an undifferentiated error.
10. THE Domain layer SHALL provide `rank_candidates`, `compare_parts`, and `convert_units` as Deterministic_Services that are not required to be exposed as LLM tools.

### Requirement 10: Determinism and No Fabrication of Technical Numbers

**User Story:** As a data steward, I want every number this layer returns to come from the published catalog or a deterministic derivation, so that downstream answers and structured blocks share one verified figure set. *(Traces: US-010, US-016, US-018, US-020, US-024, QA-01, F2 §6. Classes: [ASSESS], [APPROVED])*

#### Acceptance Criteria

1. THE Domain layer SHALL return every technical number either as a value read directly from the Published_Catalog or as a Derived_Value computed deterministically from Published_Catalog values, AND SHALL NOT return a technical number that originates from a language model.
2. WHEN a technical fact is returned, THE Domain layer SHALL attach a non-empty Evidence_Reference identifying each contributing source cell (for a direct value) or each derivation input cell (for a Derived_Value) AND SHALL attach a Data_Status, such that every returned number resolves to at least one Published_Catalog source cell with no unresolved reference.
3. WHEN a Derived_Value is returned, THE Domain layer SHALL label it as derived AND SHALL attach the deterministic formula used and the applied rounding precision expressed as a fixed number of decimal places, AND SHALL NOT present it as an official documented value.
4. WHEN the same part, edition, service, and frequency are queried, THE Domain layer SHALL return technical numbers that are numerically equal to those returned by any prior invocation of the same query (equal to the attached precision for Derived_Values and exactly equal for direct values), on every repeated invocation, providing the single figure source that the `answer` and the structured response blocks of `agent-orchestration-response` (Spec 4) will share.
5. IF a requested technical fact has no supporting Published_Catalog value and no deterministic derivation, THEN THE Domain layer SHALL return an explicit machine-readable state indicating the fact is unavailable or not documented, carrying no technical number value, AND SHALL NOT fabricate a value to fill the gap.
6. WHERE a value belongs to a Catalog_Edition that has been withdrawn, THE Domain layer SHALL return the Semantic_Failure_Code `SOURCE_WITHDRAWN` for a new recommendation request against that edition AND SHALL NOT emit a fabricated value, while still permitting read access to previously recorded facts pinned to that edition.
