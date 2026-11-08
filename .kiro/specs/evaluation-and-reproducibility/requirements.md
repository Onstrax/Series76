# Requirements Document

## Introduction

**Evaluation & Reproducibility (Spec 6 of 6).**

This specification defines the **evaluation, quality-gate, and reproducibility layer** of the *Series 76 Technical Assistant* (Konecto technical assessment): the test taxonomy across all levels, the golden-dataset oracle and domain property matrix, the cost-gated model/tool A/B evaluation, the security and persistence adversarial suite, the Android QA and accessibility checks, the twelve end-to-end demo flows, the clean-clone reproducibility and README/delivery obligations, the evidence-and-honesty policy, the integral traceability closure across all six specs, and the committed AI-assistant configuration artifact.

This layer is the place where **real execution happens**: it exercises and measures the artifacts produced by Specs 1–5 and resolves the empirical questions those specs deliberately left open (model selection, tool-set A/B winner, cost measurement, accuracy against the golden set, cold-start reproducibility). It is the integration and judgment boundary; it **does not reimplement** any data, domain, backend, agent, or Android behavior.

> **Central honesty discipline (read first):** Nothing in this document asserts that any run, benchmark, A/B comparison, model evaluation, cost measurement, latency measurement, security probe, emulator session, or cold-start reproduction has **already been executed**. Every acceptance criterion below is a **to-be-run obligation** with honest evidence capture. No model winner, no tool-set winner, no accuracy number, no cost figure, and no "passed" verdict is claimed here as a historical fact. A result exists only once its defined evidence (command, date/commit, environment, sanitized log, case count and denominator, cumulative cost) is captured; until then it is a pending obligation, never a claim.

This spec is **Spec 6 of 6**. It **integrates and measures** (never reimplements):

- `data-and-ingestion` (Spec 1) — the published catalog, the immutable `Catalog_Edition` facts, edition-withdrawal semantics, the verified-replay publication path, and the **golden dataset** that is the single numeric oracle. This layer **verifies against** that dataset; it never invents a catalog number.
- `domain-and-tools` (Spec 2) — the pure domain operations, deterministic services (ranking, comparison, conversion), the custom LangChain tools, Tool_Set_A and Tool_Set_B, the `Semantic_Failure_Code` set, and the verified figure set. This layer **runs property tests and tool A/B comparisons against** these; it never reimplements a repository, a ranking, or a number.
- `backend-api-auth-jobs-crypto` (Spec 3) — the HTTP contracts, auth/ownership isolation, the durable job queue with leases/fencing/idempotency, AES-256-GCM crypto and key lifecycle, deletion/no-resurrection, and the Debug trace endpoint. This layer **exercises** these through contract, concurrency, and adversarial tests; it never establishes trust, opens a transaction, or encrypts data itself.
- `agent-orchestration-response` (Spec 4) — the agent harness-ready seams, the candidate `Model_Config` per `Model_Function`, the Turn_Budget and Cost_Ledger seams, the response-composition and claim-verification surface. This layer **runs the canary and A/B harness** against these candidates and **resolves** the selection Spec 4 declared open; it authors no agent logic.
- `android-app` (Spec 5) — the Compose UI, navigation, UiState rendering, offline behavior, and accessibility surface. This layer **runs the Android unit, UI, and instrumented/emulator tests**; it draws no UI.

> **Important status note:** Every model candidate, tool-set candidate, accuracy threshold, cost gate, promotion gate, and demo flow below is a **contract or harness obligation to be exercised**, never a claim that selection, measurement, or a winner has already been produced.

### Legend of Requirement Classes

Each requirement is tagged with one or more classes, following the F0–F6 handoff distinction:

- **[ASSESS]** — Mandatory requirement from the Konecto assessment (`assessment-en.pdf`).
- **[APPROVED]** — Approved addition or decision beyond the raw assessment, ratified in the F0–F6 handoff.
- **[DELEGATED]** — Delegated technical detail that Kiro may concretize (exact test runner flags, fixture layout, CI wiring, report file format) while preserving the approved invariants.
- **[EXPERIMENT]** — Requires real execution, benchmark, or measurement to satisfy; cannot be satisfied by design alone, and is **not** satisfied until its defined evidence is captured.

### Source-of-Truth Precedence

When sources conflict, the following precedence governs this spec:

1. **`assessment-en.pdf`** — authoritative for external obligations: Docker Compose reproducibility, the mandatory `POST /api/conversation` contract behavior, at least one real LangChain custom tool with no free text-to-SQL, Developer Debug scope, bilingual ES/EN, OpenRouter via environment-configured models with a bounded budget, the committed AI-assistant configuration, and one-week reproducibility from a clean clone.
2. **Golden dataset (Spec 1), derived only from `series_76_electric_data.pdf`** — the single numeric oracle. Every expected technical value used by any test originates from the golden dataset, which itself derives numbers only from the electric-data PDF. **No expected value is authored by a language model, inferred from a part-number substring, taken from the summary PDF, or reconstructed from generated prose.**
3. **Backend, domain, and agent contracts (Specs 2–4)** — the seams this layer exercises; this layer measures them and never alters or relaxes an approved guarantee to make a test pass.
4. **Approved F5 decisions** — the F5 quality/testing/delivery handoff (§1 priorities, §2 levels, §3 golden set and property matrix, §4 OpenRouter evaluation, §5 security/persistence, §6 Android QA/accessibility, §7 twelve e2e flows, §8 delivery/README, §9 close gate, §10 execution order) and the F5 v1.1 offline addendum (`F5-OFF-01..07`), plus F2 §9 model/tool selection plan.
5. **`series_76_summary.pdf`** — business/narrative **context only**; never a source of technical values.

**Source-of-truth reminder:** the golden dataset is the oracle for every expected number; fabricated benchmark, test, or measurement results are prohibited; and the USD 10.00 hard cap — at most USD 6.00 for development/evaluations and at least USD 4.00 reserved for the final demo — is respected at all times, with development/evaluation spend suspended before the demo reserve is touched.

### Non-Goals (Out of Scope for This Spec)

- **No reimplementation of Specs 1–5.** The data pipeline and catalog (Spec 1), domain operations and tools (Spec 2), backend endpoints/auth/jobs/crypto (Spec 3), agent reasoning and response composition (Spec 4), and Android UI (Spec 5) are **exercised and measured** here, never re-authored. A test that would require changing an approved guarantee to pass is out of scope; the correct outcome is a recorded defect, not a relaxed guarantee.
- **No invention of catalog numbers.** The Spec 1 golden dataset is the only oracle. This layer never computes, infers, or authors a technical value as an expected result.
- **No relaxation of any approved guarantee.** Numeric integrity, authorization/isolation, mandatory encryption, persistence/no-resurrection, and the mandatory `POST /api/conversation` contract are gates; they are verified, not weakened.
- **No asserted execution.** This document declares obligations and gates. It does not assert that any run, benchmark, measurement, or "passed" verdict has already occurred, and it declares no model or tool-set winner.
- **No new product features.** This layer adds no user-facing behavior beyond the evaluation, reporting, and reproducibility artifacts it produces.

### Traceability Summary

| This spec traces to | Items |
|---|---|
| User stories | US-016 (justifiable ranking), US-030 (debug inspection), US-031 (reproducible ingestion), US-032 (reproducible project) |
| QA scenarios | QA-01 (technical accuracy), QA-02 (ES/EN), QA-03 (functional safety), QA-04 (consistency), QA-05 (performance/responsiveness), QA-06 (authorization), QA-07 (authentication), QA-08 (privacy/encryption/deletion), QA-09 (accessibility), QA-10 (robustness), QA-11 (traceability), QA-12 (reproducibility), QA-13 (efficiency/cost), QA-14 (evolvability), QA-15 (artifact integrity) |
| F0 acceptance tests | AT-01..AT-18 (exercised through e2e and property suites) |
| Phase acceptance tests | F1 §6/§11 (ingestion/replay), F3-AT01..F3-AT12 (backend), F4-AT01..F4-AT19 (Android), F5-OFF-01..F5-OFF-07 (offline) |
| F-handoff contracts | F5 §1–§10 (quality/testing/delivery), F5 v1.1 offline addendum, F2 §9 (model/tool selection plan) |
| Enablers | EN-01 (ingestion/golden set), EN-02 (LangChain tools), EN-09 (observability/evals/pricing), EN-10 (reproducible delivery) |

## Glossary

- **Evaluation_Harness**: The suite and tooling that executes tests across levels, captures evidence, and reports results against defined gates; it exercises Specs 1–5 and authors no product behavior.
- **Test_Level**: One of the defined categories of verification: documental, unit/domain, ETL integration, DB integration, backend contract, agent-with-mock-tools, agent evals with real API, concurrency/failure, security adversarial, Android unit/UI, Android instrumented/emulator, and reproducibility cold-start.
- **Golden_Dataset**: The Spec 1 verified dataset derived solely from `series_76_electric_data.pdf`; the single numeric oracle for every expected technical value, including N/A states and notes.
- **Published_Value**: A technical value present in the published catalog that must match its Golden_Dataset source value, unit, row, and cell at the stored precision.
- **Field_Coverage**: The proportion of published catalog fields compared cell-by-cell against the Golden_Dataset; 100% means every published field is verified, including N/A cells and notes.
- **Domain_Property**: A property-based assertion over pure domain objects (filters, ranking, conversion, eligibility) evaluated with a property-testing engine (Hypothesis) and independent of FastAPI or any language model.
- **Model_Function**: One of the evaluated LLM roles: interpretation (bilingual intent + Filter_AST), tool-calling (agent), and explanation/answer; titles, ranking, and numbers are deterministic and excluded.
- **Model_Candidate**: One configured model assigned to a Model_Function for comparison; at least two candidates exist per evaluated function.
- **Tool_Set_A / Tool_Set_B**: The two custom-tool configurations defined by Spec 2 that the A/B comparison measures against identical scenarios.
- **Scenario_Suite**: The approximately 36 bilingual evaluation scenarios organized into eight families, each with an expected output taken from the Golden_Dataset and unseen by the agent during design.
- **Scenario_Family**: One of the eight categories of Scenario_Suite items: exact PN; torque dual service + 50/60 Hz; T03 N/A and unattributed; 24V AC/DC vs DC; boolean+range filters; follow-ups/corrections; ranking/abstention; prompt-injection/IDOR.
- **Canary_Smoke**: A cheap first pass of 1–2 turns per model per function used to confirm availability and basic correctness before any paired A/B run, incurring minimal cost.
- **Paired_AB_Run**: A comparison in which candidates receive identical prompts and scenarios on a subset, measured under identical conditions.
- **Cost_Ledger**: The cumulative record of OpenRouter provider/model usage and observed spend, measured across the whole evaluation rather than per model.
- **Budget_Rule**: The approved spend policy: a USD 10.00 hard cap, at most USD 6.00 consumable for development/evaluations, at least USD 4.00 reserved for the final demo, with development/evaluation spend suspended before the reserve is touched.
- **Promotion_Gate**: The pass condition a candidate must satisfy before selection: zero numeric discrepancies in verified cases, zero authorization leaks, 100% tool-parameter validation, and no missing mandatory scenario.
- **Critical_Defect**: A known defect in numeric integrity, authorization, isolation, mandatory encryption, persistence/no-resurrection, or the mandatory `POST /api/conversation` contract.
- **Release_Gate**: The delivery condition requiring zero known Critical_Defects before declaring the solution releasable.
- **Verified_Replay**: The Spec 1 publication path that reproduces a verified catalog edition from committed manifests **without** any Gemini API call.
- **Fresh_Extraction**: The optional Spec 1 ingestion path that performs a new extraction using an evaluator-supplied `GEMINI_API_KEY`.
- **Cold_Start_Reproduction**: Bringing the full system up from a clean clone using Docker Compose and the documented steps, with no implicit or "works on my machine" prerequisite.
- **Evidence_Record**: The set of facts captured for any "passed" claim: command, date/commit, environment, result, sanitized log, case count and denominator, absence of Critical_Defects, known limits, and real cumulative cost.
- **Traceability_Artifact**: The committed mapping from every user story, QA scenario, and phase acceptance test to the spec/task that implements it and the Evidence_Record that verifies it, flagging any gap.
- **Config_Artifact**: The committed `.kiro/` AI-assistant configuration directory, documented in the README and free of secrets.
- **Untrusted_Content**: Catalog data, tool outputs, document text, and model outputs, treated as data and never as an oracle for expected values or as instructions.

## Requirements

### Requirement 1: Test Taxonomy and Levels

**User Story:** As a quality lead, I want an explicit test taxonomy spanning every level from documental verification to cold-start reproducibility, so that each layer of Specs 1–5 is exercised by the appropriate kind of test and coverage is measured honestly. *(Traces: QA-01..QA-12, F5 §2. Classes: [APPROVED])*

#### Acceptance Criteria

1. THE Evaluation_Harness SHALL define and organize tests into exactly the following twelve Test_Levels, each present and non-empty: documental verification, unit/domain, ETL integration, DB integration, backend contract, agent-with-mock-tools, agent evals with real API, concurrency/failure, security adversarial, Android unit/UI, Android instrumented/emulator, and reproducibility cold-start.
2. THE Evaluation_Harness SHALL run the unit/domain level against pure domain objects using a property-testing engine (Hypothesis) with no import of or dependency on FastAPI, any database driver, or any language-model client.
3. THE Evaluation_Harness SHALL run the DB integration level against a real PostgreSQL instance provisioned in a container for testing AND SHALL NOT substitute an in-memory, SQLite, or mock database for that level.
4. THE Evaluation_Harness SHALL run the backend contract level against the FastAPI application using a test client or asynchronous HTTP client (TestClient/httpx), asserting every typed request/response contract of Spec 3 against a versioned contract snapshot.
5. THE Evaluation_Harness SHALL run the agent-with-mock-tools level deterministically in continuous integration using mocked tools, controlled model responses, and a fake clock, incurring zero external language-model cost and producing identical results across repeated runs with the same seed.
6. WHERE the agent-evals-with-real-API level is executed, THE Evaluation_Harness SHALL exercise at least 2 candidate models per agent function over a controlled blind set of approximately 36 scenarios, SHALL gate execution on the Budget_Rule using cumulative (not per-model) spend, SHALL cap evaluative spend at USD 6, AND SHALL NOT execute any scenario when doing so would reduce the preserved demo reserve below USD 4.
7. WHEN the reproducibility cold-start level is run from a clean clone using the documented Docker Compose and setup steps, THE Evaluation_Harness SHALL complete the documented startup, migration, seed, and replay checklist; IF any prerequisite required to complete that checklist is implicit or undocumented, THEN THE Evaluation_Harness SHALL record the level as failed.
8. THE Evaluation_Harness SHALL report code coverage and scenario coverage as two distinct, separately labeled measures AND SHALL NOT present code-line coverage as evidence of scenario coverage or of verified data guarantees; data guarantees SHALL be reported only as facts verified against the golden dataset.
9. THE Evaluation_Harness SHALL run the documental verification level by comparing the published catalog against the official PDF with a per-cell diff across all 7 tables and 68 rows, asserting 100% of published fields (including the 4 not-available cells, notes, certifications, part numbers, and frequency) match the SHA-256 manifest; IF any field diverges from the manifest, THEN THE Evaluation_Harness SHALL record the level as failed.
10. THE Evaluation_Harness SHALL run the concurrency/failure level against the PostgreSQL, API, and worker services with injected interruptions covering idempotency, per-session serialization, lease expiry, worker restart, and delete-during-job; IF a duplicated job, worker termination, or delete-during-job occurs, THEN THE Evaluation_Harness SHALL assert the persisted final state shows no duplicated, resurrected, or silently lost work.

### Requirement 2: Golden Dataset Oracle and Domain Property Matrix

**User Story:** As a data steward, I want every published value verified cell-by-cell against the golden dataset and the core domain behaviors asserted as properties, so that no technical number drifts from source and the deterministic logic holds across generated inputs. *(Traces: US-016, QA-01, QA-14, AT-01, AT-02, AT-04, AT-06, AT-07, AT-12, F5 §3. Classes: [ASSESS], [EXPERIMENT])*

#### Acceptance Criteria

1. THE Evaluation_Harness SHALL treat the Golden_Dataset, derived solely from `series_76_electric_data.pdf` and bound to that source by a recorded SHA-256 manifest, as the single numeric oracle for every expected technical value, AND SHALL NOT accept an expected value whose provenance is a language model, a part-number substring, the summary PDF, or generated prose.
2. WHEN the documental verification level runs, THE Evaluation_Harness SHALL compare every Published_Value against its Golden_Dataset source value, unit, row, and cell at the exact decimal precision recorded in the Golden_Dataset (no rounding, truncation, or normalization), covering all 7 source tables, all 68 rows, every one of the 4 N/A cells, and every note, so that Field_Coverage equals 100% of published fields.
3. IF any cell's value, unit, row, cell position, N/A status, or note fails to match its Golden_Dataset source during documental verification, THEN THE Evaluation_Harness SHALL fail the verification run and emit a per-cell report identifying the mismatching cell and both the expected and observed content, and SHALL leave the Golden_Dataset unmodified.
4. WHEN the domain property suite runs, THE Evaluation_Harness SHALL exercise each Domain_Property over at least 100 generated candidate inputs per property and SHALL fail if any generated input violates the asserted property.
5. THE Evaluation_Harness SHALL assert the Domain_Property that applying an additional `AND` constraint produces an eligible candidate set whose size is less than or equal to the set before the constraint was applied.
6. THE Evaluation_Harness SHALL assert the Domain_Property that an N/A value never satisfies a numeric filter predicate.
7. THE Evaluation_Harness SHALL assert the Domain_Property that reordering the operands of an `AND` filter yields an eligible set equal to the original.
8. THE Evaluation_Harness SHALL assert the Domain_Property that an inverse unit conversion returns the original value within the tolerance recorded for that conversion only for a Derived_Value, AND SHALL NOT apply conversion-tolerance equality to an official Published_Value such that the official value is substituted by a converted value.
9. THE Evaluation_Harness SHALL assert the Domain_Property that lexicographic ranking is stable, producing byte-for-byte identical ordering for identical candidate sets and identical accepted priorities across repeated evaluations.
10. THE Evaluation_Harness SHALL assert the Domain_Property that a comparison declares a winner only when the service, frequency, supply, and unit conditions of the compared candidates are all compatible, and never declares a winner across any incompatible condition.
11. WHEN a catalog edition is withdrawn, THE Evaluation_Harness SHALL verify that any new recommendation request against that edition is rejected without producing a recommendation, while every prior conversation message for that edition remains retrievable with its original content unchanged.

### Requirement 3: Cost-Gated Model and Tool A/B Evaluation

**User Story:** As an evaluator, I want at least two model candidates per function and both tool sets compared on bilingual golden-anchored scenarios under a strict cumulative budget, so that selection is defensible, cheap-first, and never exceeds the spend cap or fabricates a winner. *(Traces: US-016, QA-02, QA-03, QA-13, F5 §4, F2 §9. Classes: [APPROVED], [EXPERIMENT])*

#### Acceptance Criteria

1. THE Evaluation_Harness SHALL configure at least two Model_Candidates for each evaluated Model_Function (interpretation, tool-calling, explanation) and SHALL compare Tool_Set_A against Tool_Set_B on an identical set of scenarios, where identical means the same scenario identifiers, inputs, and expected outputs are applied to both tool sets.
2. THE Evaluation_Harness SHALL define a Scenario_Suite of 34 to 38 bilingual scenarios covering all eight Scenario_Families (exact PN; torque dual service + 50/60 Hz; T03 N/A and unattributed; 24V AC/DC vs DC; boolean+range filters; follow-ups/corrections; ranking/abstention; prompt-injection/IDOR), with each of the eight families represented by at least one scenario, with Spanish scenarios between 40% and 60% of the suite and English scenarios between 40% and 60% of the suite.
3. THE Evaluation_Harness SHALL source every expected scenario output from the Golden_Dataset AND SHALL NOT derive any expected scenario output from a language model.
4. THE Evaluation_Harness SHALL execute, in strict order, (a) offline schema, AST, and property tests at zero external cost, THEN (b) a Canary_Smoke of 1 to 2 turns per model per function, THEN (c) a Paired_AB_Run on a subset of between 1 and 12 scenarios, AND IF any stage in the order has not completed, THEN THE Evaluation_Harness SHALL NOT begin the next stage.
5. THE Evaluation_Harness SHALL record cumulative spend in the Cost_Ledger across the whole evaluation rather than per model, AND SHALL enforce the Budget_Rule of a USD 10.00 hard cap, at most USD 6.00 allocated to development and evaluations, and at least USD 4.00 reserved for the demo.
6. IF cumulative development-and-evaluation spend recorded in the Cost_Ledger reaches USD 6.00, THEN THE Evaluation_Harness SHALL suspend all further development and evaluation model calls before any spend is charged against the USD 4.00 demo reserve, AND THE Evaluation_Harness SHALL retain the Cost_Ledger totals recorded up to the point of suspension.
7. WHEN a model is evaluated, THE Evaluation_Harness SHALL verify the model identifier, live availability, tool-calling support, JSON-output support, and the current live price before any benchmark call, AND IF any of these cannot be verified, THEN THE Evaluation_Harness SHALL exclude that model from the benchmark, record the reason for exclusion, and make no benchmark call for that model.
8. THE Evaluation_Harness SHALL apply the Promotion_Gate to each candidate, consisting of zero numeric discrepancies in verified cases, zero authorization leaks, 100% tool-parameter validation, and no missing mandatory scenario, AND IF a candidate fails any one Promotion_Gate element, THEN THE Evaluation_Harness SHALL mark that candidate as not promotable.
9. WHEN two candidates are compared, THE Evaluation_Harness SHALL select the candidate with the higher count of successful critical cases even when that candidate has a higher recorded cost, AND WHEN the two candidates have an equal count of successful critical cases, THE Evaluation_Harness SHALL select the candidate with the lower complexity, where lower complexity is the candidate with the fewer configured tools and steps.
10. THE Evaluation_Harness SHALL NOT assert any model winner, tool-set winner, or benchmark result as already executed, SHALL NOT fabricate an evaluation result, AND SHALL report a result only when its Evidence_Record has been captured.

### Requirement 4: Security and Persistence Adversarial Suite

**User Story:** As a security reviewer, I want adversarial tests that attempt to break isolation, authentication, encryption, injection resistance, deletion, and idempotency, so that every mandatory protection is probed and no bypass is accepted. *(Traces: US-030, QA-06, QA-07, QA-08, AT-10, AT-13, AT-14, AT-16, F5 §5. Classes: [ASSESS], [APPROVED])*

#### Acceptance Criteria

1. WHEN user A requests a conversation, job, message, or trace owned by user B, THE Evaluation_Harness SHALL verify the backend returns a `404` or `403` response within 2000 ms whose body contains no field value, metadata attribute, timestamp, identifier, or count belonging to B's resource, and whose response size and latency do not differ measurably (within 50 ms) between a non-existent resource and an existing resource owned by B.
2. WHEN developer A requests a Debug trace owned by developer B, THE Evaluation_Harness SHALL verify the request is denied with a response byte-identical to the Criterion 1 denial response, containing zero bytes of trace content, confirming the `developer` role grants no cross-owner access.
3. IF registration is attempted with a client-supplied `role=developer` or any other client-supplied privilege field, THEN THE Evaluation_Harness SHALL verify the backend either creates an account whose effective role is exactly `user` or rejects the request with an error indicating the field is not permitted, and in no case persists an account whose role is `developer`.
4. WHEN a refresh token is reused after it has already been exchanged, THE Evaluation_Harness SHALL verify the backend detects the reuse, revokes the entire refresh-token family within the same request, and returns an error indicating the session is no longer valid.
5. WHEN a request is made using any access or refresh token belonging to a session that has been logged out, THE Evaluation_Harness SHALL verify the backend rejects the request as unauthorized and performs no authorized action.
6. WHEN a raw PostgreSQL dump is inspected without the key material, THE Evaluation_Harness SHALL verify that every stored title, message, sensitive trace, and checkpoint field is AES-256-GCM ciphertext, that no field yields reusable plaintext, and that scanning the dump for any known plaintext sample returns zero matches.
7. IF stored ciphertext or its authentication tag is modified in any byte, THEN THE Evaluation_Harness SHALL verify decryption fails closed, returns an error indicating integrity verification failed, and returns no corrupted, partial, or substituted plaintext.
8. THE Evaluation_Harness SHALL verify that no access token, refresh token, password, key material, model prompt, raw SQL statement, or stack trace appears in any log entry, Debug trace, or `answer` field, by scanning each output for all injected known-secret samples and confirming zero matches.
9. WHEN a prompt-injection or role-escalation payload is submitted, THE Evaluation_Harness SHALL verify that the authenticated tenant, edition, and scope are byte-identical to their pre-request values, that no SQL statement other than the parameterized queries required by the requested operation executes, and that no system internals (schema names, file paths, configuration values, or stack traces) appear in the response.
10. WHEN a conversation is deleted while a job referencing it is in progress, THE Evaluation_Harness SHALL verify that any write issued by a late worker after the deletion does not restore the conversation, its messages, its traces, or its key material, and that a subsequent read of each returns the same not-found denial as Criterion 1.
11. WHEN duplicate jobs with the same idempotency key are submitted, or a worker is killed mid-turn and the job is retried, THE Evaluation_Harness SHALL verify that exactly one persisted turn effect exists, that no two persisted results for the turn conflict, and that the total count of persisted turn effects for that key is exactly 1.
12. WHEN the Android client logs out or switches account, THE Evaluation_Harness SHALL verify that the previous user's cached content is purged from on-device storage and is not retrievable through any client query, and that no previously rendered content is exposed through UI recomposition after the logout or switch completes.
13. WHILE the Android client is offline and a conversation it has cached is deleted remotely, THE Evaluation_Harness SHALL verify that the client does not restore or re-display the server-deleted data, and that upon reconnection the client reconciles to the server state with the deleted data absent.

### Requirement 5: Android QA and Accessibility

**User Story:** As a mobile QA engineer, I want Compose UI, accessibility, state coverage, route gating, and responsiveness verified on an emulator, so that every documented screen state is reachable and usable without ANR or leaked Debug access. *(Traces: QA-05, QA-09, F5 §6, F5-OFF-01..07, F4-AT01..F4-AT19. Classes: [APPROVED])*

#### Acceptance Criteria

1. THE Evaluation_Harness SHALL verify Compose semantics are exposed for all interactive elements, TalkBack announces a non-empty label for each interactive element, large text scaling up to 200% renders all text without truncation or clipping, both dark and light themes render all elements with no missing or unreadable content, comparison tables scroll horizontally to reveal all off-screen columns, and each chart provides a textual alternative that includes its unit and condition context.
2. THE Evaluation_Harness SHALL verify that each of the following UiStates is reachable and renders its documented content with no missing or placeholder-only elements: loading, empty, queued, running, error, offline-cache, no-matches, N/A, plan-awaiting-confirmation, stale-plan, session-expired, catalog-withdrawn, and deletion-pending.
3. THE Evaluation_Harness SHALL verify the Conversations, Chat, and Developer Debug routes and the Login and Register routes are each navigable to and render their documented destination content.
4. WHEN direct navigation to the Developer Debug route is attempted without the `developer` role, THE Evaluation_Harness SHALL verify that no trace content is obtained even though the destination UI is present in the build.
5. THE Evaluation_Harness SHALL verify that network, database, and cryptography work is performed off the main thread such that the main thread is never blocked for 5 seconds or longer and no ANR is triggered, and that any active polling stops issuing further requests when the owning screen enters the stopped lifecycle state.
6. WHEN connectivity is lost with a cached conversation open, THE Evaluation_Harness SHALL verify a no-connection notice is displayed on screen, the Send control is disabled, and only authorized history remains accessible, consistent with the offline addendum.
7. WHEN connectivity is restored after an offline draft was composed, THE Evaluation_Harness SHALL verify the draft content remains unchanged from what the user composed and is not transmitted until the user performs an explicit new send action.
8. WHEN the backend returns `503` while the network is present, THE Evaluation_Harness SHALL verify a service-unavailable message is displayed rather than a no-connection message.

### Requirement 6: End-to-End Demo Flows

**User Story:** As an assessment evaluator, I want the twelve end-to-end demo flows executed on an emulator with recorded evidence, so that the mandatory behaviors are demonstrated together against the running system. *(Traces: US-016, US-030, US-031, US-032, QA-01..QA-12, AT-01..AT-18, F5 §7. Classes: [ASSESS])*

#### Acceptance Criteria

1. WHEN the Evaluation_Harness runs the registration flow, THE Evaluation_Harness SHALL register a new account, confirm the assigned role equals `user`, log out, log back in with the same credentials, and record that the authenticated session is restored.
2. WHEN the Evaluation_Harness queries an exact part number for both On/Off and Modulating, THE Evaluation_Harness SHALL confirm the displayed figures match the verified reference figures exactly and that the evidence note is present and non-empty.
3. WHEN the Evaluation_Harness performs a filter search, THE Evaluation_Harness SHALL confirm the displayed eligible count equals the number of nominal part numbers listed and that no more than three product cards are shown.
4. WHEN the Evaluation_Harness requests a recommendation with incomplete criteria, THE Evaluation_Harness SHALL review the shown interpretation, submit a correction, confirm the plan revision reflects the correction, and confirm a non-empty ranking is returned.
5. WHEN the Evaluation_Harness compares exactly two models and then alternates a third, THE Evaluation_Harness SHALL confirm a bar chart is displayed only when the compared metrics are comparable and is not displayed otherwise.
6. WHEN the Evaluation_Harness issues a 50 Hz follow-up without repeating the part number, THE Evaluation_Harness SHALL apply it to the prior part-number context, restart the backend, reopen the conversation, and confirm the reopened history contains the same messages in the same order as before the restart.
7. WHEN the Evaluation_Harness opens Developer Debug for the developer's own session, THE Evaluation_Harness SHALL confirm the tool arguments and results are visible; and IF the same access is attempted under a `user` role, THEN THE Evaluation_Harness SHALL confirm access is denied and no tool arguments or results are disclosed.
8. IF the Evaluation_Harness simulates a backend outage, THEN THE Evaluation_Harness SHALL confirm the conversation is recovered from cache, the unsent draft is retained, and the session reconnects once the backend is available.
9. WHEN the Evaluation_Harness sends two consecutive turns to the same conversation, THE Evaluation_Harness SHALL close and reopen the app and confirm the two turns appear in their original send order with their final states matching those before the app was reopened.
10. WHEN the Evaluation_Harness deletes a conversation with a job in progress, THE Evaluation_Harness SHALL confirm the deleted conversation does not reappear in the conversation list after the in-progress job completes.
11. WHEN the Evaluation_Harness runs Verified_Replay and verified publication, THE Evaluation_Harness SHALL confirm zero outbound model (Gemini) calls occur during the run, and SHALL additionally perform a documented Fresh_Extraction using an evaluator-supplied `GEMINI_API_KEY` and confirm the extraction completes.
12. WHEN the Evaluation_Harness reproduces the full system from a clean clone using Docker Compose and the emulator, THE Evaluation_Harness SHALL confirm the system starts successfully and SHALL capture recorded emulator evidence covering all twelve demo flows.

### Requirement 7: Reproducibility, README, and Delivery

**User Story:** As an evaluator, I want a single repository that boots the whole system from a clean clone with documented steps and no committed secrets, so that I can reproduce, run, and judge the solution without implicit knowledge. *(Traces: US-031, US-032, QA-12, QA-14, QA-15, F5 §8. Classes: [ASSESS])*

#### Acceptance Criteria

1. THE delivery SHALL be a single repository that contains all of the following components, with each present and identifiable at the repository top level or in a documented subdirectory: the backend, the worker, the Android app, the ingestion pipeline, and the architecture and AI-assisted-development documentation.
2. THE delivery SHALL provide all of the following artifacts, each resolvable from a path stated in the README: a backend Dockerfile, a `docker-compose.yml` defining exactly the services `db`, `api`, and `worker`, a `.env.example` in which every value is a non-functional placeholder and no value is a real secret or credential, versioned migrations, documented ETL commands, Verified_Replay manifests, controlled seeds, and emulator-to-host networking documentation.
3. THE delivery SHALL provide a README that documents each of the following topics in a dedicated, locatable section: setup, the synchronous endpoint, the asynchronous endpoint, registration, login, the test `user` versus `developer` distinction, Debug permissions, key decisions and tradeoffs, the configurable models, the budget, the security limitations, the Fresh_Extraction versus Verified_Replay modes, and the known failures.
4. THE Verified_Replay path SHALL complete without any Gemini API key being set, AND THE Fresh_Extraction path SHALL be optional and SHALL run only when an evaluator-supplied `GEMINI_API_KEY` is provided.
5. WHEN Cold_Start_Reproduction is performed from a clean clone of the repository on a host with only the documented prerequisites installed, THE Evaluation_Harness SHALL bring the system to a testable state by executing only commands written in the README, in the documented order, with no step relying on undocumented local configuration, host-specific state, or files absent from the clone.
6. IF Cold_Start_Reproduction requires any step, file, or configuration that is not documented in the README or not present in the clean clone, THEN THE Evaluation_Harness SHALL record the reproduction outcome as a failure.
7. WHEN artifact integrity is checked, THE delivery SHALL compute the SHA-256 digest of the source PDF and of the manifest and compare each against its trusted SHA-256 reference value.
8. IF a computed SHA-256 digest does not match its trusted reference value, THEN THE delivery SHALL reject the artifact, SHALL surface an indication identifying the mismatched artifact, and SHALL NOT publish or ingest the mismatched artifact.

### Requirement 8: Evidence and Honesty Policy

**User Story:** As a reviewer, I want every "passed" claim backed by concrete evidence and no fabricated or over-claimed result, so that the evaluation is trustworthy and the release gate is enforced honestly. *(Traces: US-031, US-032, QA-11, QA-13, F5 §1, F5 §9, F5 §10. Classes: [ASSESS], [EXPERIMENT])*

#### Acceptance Criteria

1. WHEN any test or scenario is declared "passed", THE Evaluation_Harness SHALL, before the "passed" status is emitted, record an Evidence_Record containing the command, the date and commit, the environment, the result, a sanitized log with secrets and credentials redacted, the case count and its denominator, the absence of Critical_Defects, the known limits, and the real cumulative cost in USD.
2. THE Evaluation_Harness SHALL NOT claim 100% semantic coverage on the basis of the 68 audited golden rows or the 36 evaluation scenarios, and SHALL state every coverage figure as a numerator over its explicit denominator.
3. THE Evaluation_Harness SHALL NOT fabricate any benchmark, test, measurement, or number, and SHALL present a result only when a persisted Evidence_Record for that specific result exists.
4. THE Release_Gate SHALL require zero known Critical_Defects in numeric integrity, authorization, isolation, mandatory encryption, persistence/no-resurrection, and the mandatory `POST /api/conversation` contract before the solution is declared releasable.
5. IF a known Critical_Defect exists, THEN THE Evaluation_Harness SHALL NOT declare the solution releasable AND SHALL record the defect with its scope.
6. IF OpenRouter fails or returns no usable response, or the evaluation budget is exhausted, THEN the system SHALL return an explicit service-unavailable response indicating the cause, SHALL preserve the user's draft and history, SHALL NOT spend the demo reserve, AND SHALL NOT invent data to fill the gap.
7. THE Evaluation_Harness SHALL record non-critical defects with their scope and justification rather than suppressing them, and SHALL NOT present code-line coverage as a substitute for verified-data evidence.
8. IF a "passed" status is claimed for a test or scenario that has no persisted Evidence_Record, THEN THE Evaluation_Harness SHALL reject the claim, SHALL NOT present the result as passed, and SHALL record the missing-evidence condition.

### Requirement 9: Traceability Closure Across All Six Specs

**User Story:** As a program reviewer, I want one integral traceability artifact mapping every user story, QA scenario, and phase acceptance test to its implementing spec/task and verifying evidence, so that no obligation is silently dropped across the six specs. *(Traces: US-031, US-032, QA-11, QA-12, F5 §9. Classes: [ASSESS])*

#### Acceptance Criteria

1. THE Traceability_Artifact SHALL map each of the 35 active user stories (US-001 through US-034 and US-036, with US-035 recorded as a cross-cutting delete-race scenario) to at least one implementing spec and at least one implementing task, with no user story absent from the mapping.
2. THE Traceability_Artifact SHALL map each of the 15 QA scenarios (QA-01 through QA-15) to at least one implementing spec and at least one implementing task, with no QA scenario absent from the mapping.
3. THE Traceability_Artifact SHALL map each phase acceptance test — F1 §6 and §11, F3-AT01 through F3-AT12, F4-AT01 through F4-AT19, F5-OFF-01 through F5-OFF-07, and AT-01 through AT-18 — to at least one implementing spec and at least one implementing task, with no listed acceptance test absent from the mapping.
4. THE Traceability_Artifact SHALL associate each mapped item with the Evidence_Record that verifies it, or SHALL mark the item as `pending` when it is mapped to a spec and task but no Evidence_Record yet exists.
5. IF any user story, QA scenario, or phase acceptance test has no implementing spec, no implementing task, or no verifying evidence, THEN THE Traceability_Artifact SHALL flag that item as a `gap` rather than omitting it, where `pending` and `gap` are mutually exclusive states.
6. THE Traceability_Artifact SHALL present the mapping as the integral cross-spec map spanning all six specs, covering Specs 1 through 6.

### Requirement 10: Committed Configuration Artifact

**User Story:** As an assessment evaluator, I want the AI-assistant configuration committed and documented, so that the development setup is reproducible and contains no secrets. *(Traces: US-032, QA-12, assessment p.6. Classes: [ASSESS])*

#### Acceptance Criteria

1. THE delivery SHALL commit the `.kiro/` AI-assistant configuration directory, including all of its tracked files, as part of the repository such that it is present in a fresh clone of the default branch.
2. THE README SHALL contain a section that both references the `.kiro/` Config_Artifact by name and states its purpose as the AI-assistant configuration used for the development setup.
3. THE Config_Artifact SHALL contain no secrets, tokens, or real credentials, and SHALL use non-functional placeholder values for every configuration field that would otherwise require a secret, token, or credential.
4. IF a scan of the Config_Artifact detects a value that is a real secret, token, or credential rather than a placeholder, THEN THE delivery SHALL be treated as failing the no-secrets criterion, with the offending field identified and the artifact not accepted until the value is replaced with a placeholder.
