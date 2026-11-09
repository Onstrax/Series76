# Requirements Document

## Introduction

**Agent Orchestration & Response (Spec 4 of 6).**

This specification defines the **agentic orchestration and response-composition layer** of the *Series 76 Technical Assistant* (Konecto technical assessment): the LangChain agent with bounded autonomy, the bilingual semantic interpreter, the deterministic policy engine, the per-turn state machine, the conditional confirmation protocol, the recommendation-completeness gate, the response composer with claim verification, multi-turn memory and context resolution, the abstention and fallback policy, and the OpenRouter model configuration with bounded budgets.

This layer **drives one conversation turn end to end**: it interprets a user message, authors a validated plan, (optionally) asks for clarification or confirmation, selects and invokes allow-listed custom tools, and composes a bilingual `answer` together with typed `content_blocks` whose every technical figure originates from the verified figure set. It is the reasoning brain; it is **not** the trust, transport, durability, numeric, or presentation boundary.

This spec is **Spec 4 of 6**. It **depends on**:

- `domain-and-tools` (Spec 2) — the pure domain operations (`get_part`, `search_parts`, `get_source_notes`), the deterministic services (`rank_candidates`, `compare_parts`, `convert_units`), the custom LangChain tools (Tool_Set_A and Tool_Set_B), the recommendation-completeness primitives (four Requirement_Groups, Coverage_Status), the `Semantic_Failure_Code` set, and the **verified figure set** (every number carries Data_Status and Evidence_Reference). This layer **calls** these operations; it never reimplements a repository, a ranking, a comparison, a conversion, or a number.
- `backend-api-auth-jobs-crypto` (Spec 3) — the HTTP endpoints, the typed DTOs and `Response_Envelope`, the `Content_Block` discriminated union defined structurally, the `Job_State` set, the durable PostgreSQL-backed job queue with leases/fencing/idempotency, the `Plan_Revision` confirmation endpoint, and the encrypted-checkpoint surface. This layer **plugs into** these seams; it never establishes identity, opens transactions, encrypts data, or owns the queue.

It is **consumed by**:

- `android-app` (Spec 5) — which renders the `Response_Envelope` (`answer`, `content_blocks`, `interpretation_summary`, `status`, `plan`, `warnings`) that this layer produces, without extracting technical figures from generated prose.

It is **evaluated by**:

- `evaluation-and-reproducibility` (Spec 6) — which resolves the empirical model-selection and tool-set A/B comparison against the golden set. This spec defines the **harness-ready seams, candidate configuration, and promotion gates**; it runs no benchmark and declares no winner.

> **Important status note:** Nothing in this document asserts that any benchmark, A/B tool comparison, model evaluation, cost measurement, latency measurement, or live model call has been executed. Every model candidate, tool-set candidate, and budget gate below is a **contract or harness seam to be exercised** by `evaluation-and-reproducibility` (Spec 6) and F5 — never a claim that selection, measurement, or a winner has already been produced. No model winner and no tool-set winner is declared here.

### Legend of Requirement Classes

Each requirement is tagged with one or more classes, following the F0–F6 handoff distinction:

- **[ASSESS]** — Mandatory requirement from the Konecto assessment (`assessment-en.pdf`).
- **[APPROVED]** — Approved addition or decision beyond the raw assessment, ratified in the F0–F6 handoff.
- **[DELEGATED]** — Delegated technical detail that Kiro may concretize (prompt wording, exact state-store shape, retry constants, DI wiring) while preserving the approved invariants.
- **[EXPERIMENT]** — Requires real execution, benchmark, or measurement to satisfy; cannot be satisfied by design alone and is resolved by Spec 6.

### Source-of-Truth Precedence

When sources conflict, the following precedence governs this spec:

1. **`assessment-en.pdf`** — authoritative for external obligations: a real LangChain agent invoking at least one custom tabular tool, no free text-to-SQL, the mandatory `POST /api/conversation` contract behavior (`session_id` + `answer`), the Developer Debug scope, bilingual ES/EN, OpenRouter via environment-configured models, and reproducibility.
2. **Verified figure set (Spec 2) over the Published Catalog (Spec 1)** — the single source of technical numbers and conditions. Every technical figure returned by this layer originates from a Spec 2 fact or a Spec 2 deterministic derivation, which itself derives numbers **only** from `series_76_electric_data.pdf`. **The LLM never authors a technical number.**
3. **Backend contracts (Spec 3)** — the endpoints, DTOs, `Response_Envelope`, `Content_Block` structure, `Job_State`, plan-confirmation semantics, and encrypted checkpoint surface this layer plugs into.
4. **Approved F2 decisions** — the F2 agent-architecture handoff (§1 bounded autonomy, §2 responsibility split, §3 state machine/plan, §4 AST capabilities, §5 tool contract A/B, §6 verification of visible output, §7 persistence coherence, §8 orchestration limits, §9 model/tool selection plan, §10 fallback matrix, and the v1.1 per-function evaluation addendum).
5. **`series_76_summary.pdf`** — business/narrative **context only**; never a source of technical values.

**Source-of-truth reminder:** no number emitted by this layer in `answer`, any `content_block`, any chart series, or any highlight may be invented by the language model, inferred from a part-number substring, taken from the summary PDF, or reconstructed from generated prose. The LLM composes prose and selects among allow-listed tools; the authoritative numbers come from the Spec 2 verified figure set and are composed through typed placeholders.

### Non-Goals (Out of Scope for This Spec)

- **No HTTP transport, authentication, authorization enforcement, job queue, persistence, or cryptography.** Endpoints, JWT/opaque tokens, RBAC/ownership checks, the durable queue with leases/fencing/idempotency, AES-256-GCM, key lifecycle, and deletion belong to `backend-api-auth-jobs-crypto` (Spec 3). This layer **plugs into** those seams and reads an already-authorized edition and permission context; it never establishes trust, opens a SQL transaction, or persists ciphertext itself.
- **No domain SQL, typed repositories, ranking/comparison/conversion math, custom-tool internals, or the catalog.** These belong to `domain-and-tools` (Spec 2). This layer **calls** the tools and services; it never reimplements a number, a repository, or a deterministic computation.
- **No Android UI, local cache, Keystore, or rendering.** The "maximum three full cards" rule, dual-of-two comparison view, bar-chart drawing, highlight styling, and offline behavior belong to `android-app` (Spec 5). This layer **produces** the typed envelope; it does not decide rendering limits or draw charts.
- **No ingestion, extraction, audit, or edition publication.** These belong to `data-and-ingestion` (Spec 1).
- **No benchmark execution or winner selection.** The actual model/tool A/B runs, accuracy thresholds, cost measurements, and the declared winners belong to `evaluation-and-reproducibility` (Spec 6). This layer defines the **candidates, seams, and gates** the eval harness measures but executes no benchmark and declares no winner.

### Traceability Summary

| This spec traces to | Items |
|---|---|
| User stories | US-010, US-011, US-012, US-013, US-014, US-015, US-016, US-017, US-018, US-019, US-020, US-022, US-023, US-024, US-025, US-026, US-034 |
| QA scenarios | QA-01 (technical accuracy), QA-02 (ES/EN interpretation), QA-03 (functional safety / preliminary vs verified), QA-10 (robustness) |
| F0 acceptance tests | AT-01 (contextual lookup), AT-02 (logical filters), AT-03 (delegation), AT-04 (ranking priority), AT-06 (comparison), AT-07 (N/A), AT-08 (out of document), AT-17 (unsupported narrative figure), AT-18 (top-1) |
| F2 contracts | F2 §1 (bounded autonomy), §2 (responsibility split), §3 (state machine, plan, confirmation), §4 (AST capabilities), §5 (tool A/B contract), §6 (verification of visible output), §7 (persistence coherence), §8 (orchestration limits), §9 (model/tool selection plan), §10 (fallback matrix), v1.1 addendum (per-function evaluation) |
| Enablers | EN-02 (LangChain tools), EN-07 (response/error contract), EN-09 (observability/evals/pricing) |

## Glossary

- **Agent_Orchestrator**: The component that drives one conversation turn through interpretation, policy validation, (optional) clarification/confirmation, tool execution, verification, and response composition.
- **LangChain_Agent**: The real LangChain-based agent that selects among allow-listed custom tools and receives their results under a bounded budget; it has limited autonomy and does not decide permissions, editions, numbers, or rules.
- **Semantic_Interpreter**: The LLM-backed component that classifies bilingual intent, extracts referents and criteria, and authors a draft Filter_AST, producing a structured Interpreted_Plan.
- **Policy_Engine**: The deterministic (non-LLM) component that validates the Filter_AST, requirement-group coverage, clarification need, query permissions, and plan revisions.
- **Response_Composer**: The deterministic component that assembles `answer` and typed `content_blocks` exclusively from the verified figure set via typed placeholders, after claim verification.
- **Interpreted_Plan**: The structured output of interpretation and policy validation, carrying `intent`, `filter_ast`, `referents`, `criteria`, `data_status`, `catalog_edition_id`, `plan_id`, `plan_revision`, `presentation_intent`, and `response_language`.
- **Intent**: One of `EXACT_LOOKUP`, `FILTER_SEARCH`, `COMPARISON`, `RECOMMENDATION`, `DERIVED_CALCULATION`, `EXPLANATION`, `FOLLOWUP`, or `OUT_OF_SCOPE`.
- **Filter_AST**: A typed filter expression with `AND`/`OR`/`NOT` grouping, allow-listed field predicates, typed operators, ranges, and units, authored as a draft by the Semantic_Interpreter and validated by the Policy_Engine; raw SQL is never accepted.
- **Interpretation_Summary**: The user-visible explanation of the turn's intent, applied/proposed/delegated/ignored criteria, and expected presentation format, excluding tool names, prompts, and internal parameters.
- **Turn_State**: One of `ACCEPTED`, `INTERPRETING`, `INTERPRETED`, `NEEDS_CLARIFICATION`, `AWAITING_CONFIRMATION`, `EXECUTING`, `VERIFYING`, `COMPLETED`, `FAILED`, `CANCELLED`, `STALE_PLAN`, or `SOURCE_WITHDRAWN`.
- **Verified_Figure_Set**: The set of technical facts and deterministic derivations returned by Spec 2, each carrying Data_Status and Evidence_Reference; the single source of numbers shared by `answer` and `content_blocks`.
- **Data_Status**: The documented state of a technical fact (defined by Spec 2): one of `AVAILABLE`, `NOT_APPLICABLE`, `NOT_DOCUMENTED`, `NOT_LISTED`, or `UNVERIFIED`.
- **Requirement_Group**: One of the four physical recommendation groups: environment/enclosure, power/supply, service type, required torque (defined by Spec 2).
- **Coverage_Status**: The per-group completeness state (defined by Spec 2): one of `SPECIFIED`, `NO_PREFERENCE`, `UNKNOWN`, `DELEGATED`, `UNSPECIFIED`, or `CONFLICTING`.
- **Recommendation_Grade**: The eligibility classification of a candidate set: `verified` (all four Requirement_Groups `SPECIFIED` and catalog-backed) or `preliminary` (otherwise).
- **Claim**: A verifiable assertion about products, such as `has_more_torque`, `is_faster`, `same_frequency`, or `no_result`, that must pass deterministic verification before appearing in any visible output.
- **Declared_Requirement**: A figure supplied by the user, labeled as a stated requirement and never presented as a catalog specification.
- **Content_Block**: A typed, discriminated element of the Response_Envelope (structure defined by Spec 3), populated with verified figures by this layer.
- **Semantic_Failure_Code**: A typed non-exception business outcome (defined by Spec 2): one of `INVALID_PN`, `PART_NOT_LISTED`, `N_A`, `NO_RESULTS`, `NOT_COMPARABLE`, `SOURCE_WITHDRAWN`, or `INVALID_FILTER`.
- **Fallback_Matrix**: The F2 §10 table mapping each defined failure/abstention condition to a business response and an execution rule.
- **Model_Function**: One of the configurable LLM roles: interpretation, tool-calling (agent), explanation/answer, with titles/ranking/numbers excluded (deterministic, no LLM).
- **Model_Config**: The environment-configured model assignment per Model_Function: `AGENT_MODEL`, optional `INTERPRETER_MODEL`, optional `ANSWER_MODEL`, optional `FALLBACK_MODEL`.
- **Turn_Budget**: The bounded per-turn resource limits: `max_model_calls_per_turn`, `max_tool_calls_per_turn`, `max_token_budget`, `max_walltime`, `max_cost_usd`, `max_result_rows`.
- **Cost_Ledger**: The record of OpenRouter provider/model usage and observed cost, used to respect the USD 10 hard cap (at most USD 6 for development/evals, at least USD 4 reserved for the final demo).
- **Untrusted_Content**: Catalog data, tool outputs, and document text, treated as data and never as instructions to the language model.

## Requirements

### Requirement 1: Hybrid LangChain Agent with Bounded Autonomy

**User Story:** As an agent integrator, I want a real LangChain agent that invokes at least one custom tabular tool and chooses only among allow-listed tools, so that the model retrieves verified facts without ever authoring SQL, picking an edition, setting permissions, or dictating a technical number. *(Traces: US-010, US-011, F2 §1, F2 §2, EN-02. Classes: [ASSESS], [APPROVED])*

#### Acceptance Criteria

1. THE LangChain_Agent SHALL invoke at least one custom tabular tool provided by `domain-and-tools` (Spec 2) to retrieve catalog facts for a turn, AND SHALL NOT satisfy a catalog query by any path other than an allow-listed Spec 2 tool.
2. WHEN the LangChain_Agent selects a tool that is on the server-defined allow-list, THE Agent_Orchestrator SHALL permit the selection, AND IF the LangChain_Agent selects a tool that is not on the server-defined allow-list, THEN THE Agent_Orchestrator SHALL reject the selection without executing it, SHALL NOT issue any catalog read for that selection, SHALL leave catalog state and domain state unchanged, AND SHALL return a rejection result indicating the selection was not permitted.
3. THE LangChain_Agent SHALL NOT author, emit, or cause execution of any SQL string, AND THE Agent_Orchestrator SHALL route every catalog read exclusively through the typed Spec 2 operations such that no language-model output reaches the database as SQL.
4. THE Agent_Orchestrator SHALL supply the `catalog_edition_id`, the permission context, and the result limits to each tool invocation from the server-injected context of Spec 3, AND IF a tool invocation carries a model-visible argument that attempts to set, duplicate, or override `catalog_edition_id`, the permission context, or any result limit, THEN THE Agent_Orchestrator SHALL ignore that model-supplied value, SHALL use only the server-injected value, AND SHALL proceed without altering the server-injected context.
5. THE Agent_Orchestrator SHALL NOT allow the language model to set, change, or override a permission decision, an edition selection, a physical rule, or a technical number.
6. WHEN a tool returns an output or a catalog datum is read, THE Agent_Orchestrator SHALL treat that output and datum as Untrusted_Content with respect to the language model, such that no text within a tool result or catalog value is executed, routed back into tool selection, or followed as an instruction.
7. IF a tool output, a catalog value, or a user message contains text that attempts to redirect the agent, escalate privileges, or override a system rule, THEN THE Agent_Orchestrator SHALL disregard that embedded instruction, SHALL continue under the configured policy, SHALL produce a response that reflects only the configured policy, AND SHALL NOT include in that response any system prompt, internal tool name, credential, secret, or data belonging to another owner.
8. WHEN the Agent_Orchestrator invokes a Spec 2 tool, THE Agent_Orchestrator SHALL enforce the server-injected result limits and per-turn invocation bounds, AND IF an invocation would exceed a server-injected limit or bound, THEN THE Agent_Orchestrator SHALL stop the invocation fail-closed, SHALL NOT return partial catalog data as a complete result, AND SHALL return a result indicating the limit was reached.

### Requirement 2: Bilingual Semantic Interpreter

**User Story:** As a technical user writing in Spanish or English, I want the assistant to classify my intent and extract my filters, referents, and criteria into a structured plan, so that my meaning is captured faithfully without the model inventing physical rules or card figures. *(Traces: US-010, US-011, US-012, US-013, US-022, US-026, QA-02, F2 §2, F2 §3. Classes: [ASSESS])*

#### Acceptance Criteria

1. WHEN a user message is interpreted, THE Semantic_Interpreter SHALL classify the turn into exactly one Intent drawn from `EXACT_LOOKUP`, `FILTER_SEARCH`, `COMPARISON`, `RECOMMENDATION`, `DERIVED_CALCULATION`, `EXPLANATION`, `FOLLOWUP`, or `OUT_OF_SCOPE`, such that the Interpreted_Plan contains one and only one intent value from this set.
2. WHEN a user message is written in Spanish or in English, THE Semantic_Interpreter SHALL interpret the message in that language AND SHALL produce an Interpreted_Plan whose intent, criteria, and referents are equivalent for semantically equivalent Spanish and English inputs, where equivalence means the two plans select the same intent value, the same set of criteria with identical status and hard/preference classification, and the same set of referents, and where the identity of part numbers, numeric values, and units is byte-for-byte unchanged by the input language.
3. WHEN a message expresses logical filtering, THE Semantic_Interpreter SHALL author a draft Filter_AST using only `AND`, `OR`, and `NOT` nodes with allow-listed field predicates, typed operators, ranges, and units, AND SHALL NOT emit raw SQL.
4. WHEN a message mentions part numbers or references prior products, THE Semantic_Interpreter SHALL record in the Interpreted_Plan each mentioned part number and each referent together with its provenance, where provenance identifies whether the item originated from the current message or from a prior turn.
5. WHEN a message expresses recommendation criteria, THE Semantic_Interpreter SHALL record each criterion with its Requirement_Group association and a status drawn from `SPECIFIED`, `NO_PREFERENCE`, `UNKNOWN`, `DELEGATED`, `UNSPECIFIED`, or `CONFLICTING`, and whether it is a hard constraint or a preference.
6. THE Semantic_Interpreter SHALL NOT create a physical rule, a certification claim, or a product card figure that is not present in the verified figure set, AND SHALL NOT populate any technical number into the Interpreted_Plan.
7. THE Semantic_Interpreter SHALL produce the Interpreted_Plan as a structured output with the `catalog_edition_id` taken from the validated session and never from a model-supplied argument.
8. IF the validated session does not supply a `catalog_edition_id`, THEN THE Semantic_Interpreter SHALL NOT produce an Interpreted_Plan AND SHALL return an error indication reporting that the catalog edition is unavailable, with no plan state retained.
9. IF a message cannot be classified into exactly one Intent with sufficient confidence, THEN THE Semantic_Interpreter SHALL classify the turn as `FOLLOWUP` when clarification is required or `OUT_OF_SCOPE` otherwise, and SHALL NOT select more than one intent value.
10. IF a message requests filtering on a field that is not in the allow-list or references a part number or referent that cannot be resolved, THEN THE Semantic_Interpreter SHALL exclude that predicate or referent from the draft Filter_AST AND SHALL record the unresolved field, part number, or referent in the Interpreted_Plan with an indication that it was not resolved.

### Requirement 3: Deterministic Policy Engine

**User Story:** As a backend maintainer, I want a deterministic policy engine that validates the AST, coverage, clarification need, permissions, and plan versions, so that validation, confirmation, and authorization are never decided by the language model. *(Traces: US-012, US-013, US-014, F2 §2, F2 §3. Classes: [APPROVED])*

#### Acceptance Criteria

1. WHEN an Interpreted_Plan is produced, THE Policy_Engine SHALL validate the Filter_AST structurally and against the field allow-list before any tool execution, AND IF the Filter_AST is structurally invalid, references a field outside the allow-list, or carries an operator or unit incompatible with its field, THEN THE Policy_Engine SHALL block all tool execution, SHALL produce either a clarification outcome or an `INVALID_FILTER` outcome that indicates to the caller which validation failed, and SHALL leave the catalog unqueried and the conversation's active state unchanged.
2. WHEN the Intent is `RECOMMENDATION`, THE Policy_Engine SHALL evaluate the Coverage_Status of each of the four Requirement_Groups using the Spec 2 completeness primitives, SHALL derive the Recommendation_Grade solely from those four Coverage_Status values, AND SHALL produce identical Coverage_Status and Recommendation_Grade values for identical plan and coverage inputs across repeated evaluations.
3. WHEN an Interpreted_Plan is produced, THE Policy_Engine SHALL decide deterministically whether blocking clarification or confirmation is required such that identical plan inputs yield the identical decision across repeated evaluations, AND the language model SHALL NOT make that decision.
4. WHERE the Interpreted_Plan is a single-filter search, THE Policy_Engine SHALL NOT require recommendation coverage before execution.
5. THE Policy_Engine SHALL validate that the turn's query permissions and `catalog_edition_id` resolve from the validated session before any tool execution, AND IF a permission or `catalog_edition_id` value originates from the language model rather than the validated session, THEN THE Policy_Engine SHALL reject it and block execution.
6. WHEN a plan is confirmed or executed, THE Policy_Engine SHALL verify the plan revision deterministically against the conversation's active state so that identical state and revision inputs yield the identical verification result across repeated evaluations, AND the language model SHALL NOT authorize, confirm, or validate a plan revision.
7. THE Policy_Engine SHALL perform every validation, coverage, clarification-need, permission, and plan-version decision with zero invocations of a language model.

### Requirement 4: Turn State Machine

**User Story:** As an operator, I want each turn driven through an explicit state machine that never holds a SQL transaction during a model call, so that interruptions, clarifications, and confirmations behave predictably and align with the durable worker. *(Traces: US-013, US-029, F2 §3, F2 §8. Classes: [APPROVED])*

#### Acceptance Criteria

1. THE Agent_Orchestrator SHALL represent each turn with exactly one Turn_State drawn from the set {`ACCEPTED`, `INTERPRETING`, `INTERPRETED`, `NEEDS_CLARIFICATION`, `AWAITING_CONFIRMATION`, `EXECUTING`, `VERIFYING`, `COMPLETED`, `FAILED`, `CANCELLED`, `STALE_PLAN`, `SOURCE_WITHDRAWN`}, and SHALL reject assignment of any value outside this set.
2. THE Agent_Orchestrator SHALL advance a turn only along the ordered path `ACCEPTED` → `INTERPRETING` → `INTERPRETED` → (`NEEDS_CLARIFICATION` | `AWAITING_CONFIRMATION` | `EXECUTING`) → `VERIFYING` → `COMPLETED`, permitting transition into `FAILED`, `CANCELLED`, `STALE_PLAN`, or `SOURCE_WITHDRAWN` only as special terminal or branching outcomes, AND SHALL NOT perform any transition that is not one of these enumerated transitions.
3. THE Agent_Orchestrator SHALL NOT hold an open SQL transaction across a call to the language-model provider, and SHALL persist the turn state in one transaction that commits before each such external call and in a separate transaction that commits after each such external call, consistent with the Spec 3 worker contract.
4. WHILE a turn is in `NEEDS_CLARIFICATION`, THE Agent_Orchestrator SHALL NOT transition that turn toward `EXECUTING` or invoke any tool for that turn until a user reply addressed to the outstanding clarification for that turn is received.
5. WHILE a turn is in `AWAITING_CONFIRMATION`, THE Agent_Orchestrator SHALL NOT invoke any tool that consumes model-call, tool-call, token, cost, or wall-time budget until an authenticated confirmation whose `(session_id, plan_id, plan_revision, user_id)` matches the turn's active plan revision is received, where any correction creates a new `plan_revision` that invalidates confirmation of the prior revision.
6. WHEN a turn is cancelled or its conversation is deleted, THE Agent_Orchestrator SHALL transition the turn to `CANCELLED` AND SHALL NOT persist a late result that would resurrect a deleted conversation, consistent with the Spec 3 fencing and tombstone contract.
7. WHEN the pinned edition for a recommendation turn has been withdrawn, THE Agent_Orchestrator SHALL transition the turn to `SOURCE_WITHDRAWN` AND SHALL NOT execute a new recommendation against that edition, while retaining prior history unchanged.
8. IF a confirmation is received for a turn in `AWAITING_CONFIRMATION` whose `plan_revision` does not match the turn's active plan revision, THEN THE Agent_Orchestrator SHALL transition the turn to `STALE_PLAN`, SHALL NOT execute the superseded plan revision, and SHALL surface an indication that the plan has changed.

### Requirement 5: Interpretation Transparency

**User Story:** As a user, I want an always-visible interpretation of my request that shows what was applied, proposed, delegated, and ignored without exposing internal tooling, so that I can trust the plan while simple exact or single-filter queries still run without a needless second turn. *(Traces: US-012, AT-01, F2 §3. Classes: [ASSESS])*

#### Acceptance Criteria

1. WHEN a turn is interpreted, THE Agent_Orchestrator SHALL include in that same response a visible Interpretation_Summary, presented without requiring any additional user action to reveal it, that states each of the following as a distinct labeled element: the intent, the applied criteria, the proposed criteria, the delegated criteria, the ignored criteria, and the expected presentation format.
2. THE Interpretation_Summary SHALL NOT contain tool names, prompt text, or internal parameter names.
3. WHEN the Interpretation_Summary is produced, THE Agent_Orchestrator SHALL label each listed criterion with exactly one of the categories documented-fact, user-assumption, proposal, or delegation, such that no criterion is left uncategorized.
4. WHEN the Intent is an `EXACT_LOOKUP` that resolves to exactly one documented part number, or a `FILTER_SEARCH` whose filter resolves to exactly one determinate value against documented data, THE Agent_Orchestrator SHALL execute the turn in a single pass and SHALL NOT require a confirmation turn before returning the result.
5. IF the turn contains two or more valid interpretations of the user request, a statement that conflicts with another statement in the same request or with a documented fact, a delegation whose outcome changes which criteria are applied or which results are returned, or a proposed recommendation or priority ordering that the user has not accepted, THEN THE Agent_Orchestrator SHALL return a clarification or confirmation request and SHALL NOT execute the turn or access documented data for that request until the user responds.
6. WHEN a user asks about a specific part number and two or more documented measurements apply to that part number, THE Agent_Orchestrator SHALL present every applicable measurement, each labeled with its service and its frequency, in a single pass without requiring a confirmation turn.

### Requirement 6: Conditional Plan Confirmation and Revision

**User Story:** As a user, I want to confirm the exact plan revision I reviewed, so that a correction I made is never executed under a stale, previously approved plan. *(Traces: US-013, AT-05, F2 §3. Classes: [APPROVED])*

#### Acceptance Criteria

1. WHEN an authenticated confirmation is received, THE Agent_Orchestrator SHALL compare the tuple (`session_id`, `plan_id`, `plan_revision`, `user_id`) against the conversation's active state, AND SHALL materialize a plan only when all four elements of the tuple match the conversation's active state exactly.
2. WHEN a user corrects a plan, THE Agent_Orchestrator SHALL create a new Plan_Revision whose revision identifier is monotonically greater than the prior revision for that session, AND SHALL invalidate the prior revision's approval such that any subsequent confirmation targeting the prior revision triggers no execution.
3. THE Agent_Orchestrator SHALL treat a confirmation as valid only after it has been validated and materialized by the backend plan-confirmation seam of Spec 3, AND SHALL NOT treat a confirmation as an unrestricted instruction to the language model.
4. IF a confirmation targets a plan revision that is not the conversation's current revision, THEN THE Agent_Orchestrator SHALL transition the turn to the stale-plan final state, SHALL surface an indication that the plan changed together with the current Plan_Revision, AND SHALL NOT execute the targeted plan nor mutate the conversation's active state.
5. WHILE the conversation's current plan revision is unchanged, THE Agent_Orchestrator SHALL treat repeated or duplicate confirmations of that revision idempotently, triggering at most one execution for that revision.
6. THE Agent_Orchestrator SHALL execute a confirmed plan only after the Spec 3 confirmation seam reports the confirmation bound to exactly the conversation's current Plan_Revision.

### Requirement 7: Recommendation Completeness, Preliminary vs Verified, and Ranking

**User Story:** As an engineer, I want a recommendation marked verified only when environment, supply, service, and torque are all satisfied, with preliminary results clearly labeled otherwise, so that no unverified recommendation is presented as confirmed and no priority is fabricated. *(Traces: US-014, US-015, US-016, US-017, US-018, AT-03, AT-04, AT-18, QA-03, F2 §4. Classes: [ASSESS], [APPROVED])*

#### Acceptance Criteria

1. WHEN the Intent is `RECOMMENDATION`, THE Agent_Orchestrator SHALL classify the candidate set as `verified` only when all four Requirement_Groups (environment, supply, service, torque) report Coverage_Status `SPECIFIED` and each of the four resolves against at least one catalog-backed matching result, using the Spec 2 completeness primitives.
2. IF at least one Requirement_Group reports a Coverage_Status other than `SPECIFIED`, THEN THE Agent_Orchestrator SHALL classify the candidate set as `preliminary` AND SHALL label the response by naming every one of the four Requirement_Groups whose Coverage_Status is not `SPECIFIED`.
3. WHERE a Requirement_Group's coverage is `DELEGATED`, THE Agent_Orchestrator SHALL present the delegation as a proposed preference AND SHALL NOT synthesize a physical condition value that is absent from the source data, even when the user delegates the choice.
4. WHEN ranking is required and a user-accepted priority ordering is available, THE Agent_Orchestrator SHALL obtain the ranking from the Spec 2 `rank_candidates` service AND SHALL NOT order candidates by a priority that the model proposed but the user did not accept.
5. IF a priority metric is not comparable across the candidate set because of differing service, frequency, supply, or unit context, THEN THE Agent_Orchestrator SHALL NOT declare a winner on that metric, SHALL present the affected candidates as a distinct indeterminate group identified as such, AND SHALL request clarification or an accepted alternative priority before producing any winner.
6. WHEN the user requests a single recommendation (top-1) and at least one candidate is eligible, THE Agent_Orchestrator SHALL present the winning candidate together with the integer count of eligible candidates only AND SHALL NOT enumerate the other eligible part numbers in that mode.
7. WHEN the user requests a single recommendation (top-1) and at least one candidate is eligible, THE Agent_Orchestrator SHALL present a winner identical to the first element of the full ranking computed by Spec 2 from the same candidate set and user-accepted priorities.
8. THE Agent_Orchestrator SHALL NOT use warranty-of-fitness or integral-compatibility language for any candidate set classified as `preliminary`.
9. IF the user requests a single recommendation (top-1) and no candidate is eligible, THEN THE Agent_Orchestrator SHALL present a no-eligible-candidate result AND SHALL NOT declare a winner, preserving the candidate set unchanged.

### Requirement 8: Response Composition and Claim Verification

**User Story:** As a data steward, I want the `answer` and the typed content blocks built from the same verified figure set with every claim checked deterministically, so that no technical number or unsupported assertion ever originates from the language model. *(Traces: US-019, US-020, US-034, QA-01, AT-06, AT-07, AT-17, F2 §6. Classes: [ASSESS])*

#### Acceptance Criteria

1. WHEN a turn completes, THE Response_Composer SHALL build the `answer` and the typed `content_blocks` from the same Verified_Figure_Set instance, inserting every technical number and part number only through typed placeholders bound to Spec 2 facts or deterministic derivations.
2. THE Response_Composer SHALL NOT place in `answer`, any `content_block`, any chart series, or any highlight a technical number that is not bound to a typed placeholder resolving to a Spec 2 fact or deterministic derivation.
3. WHEN a product claim such as `has_more_torque`, `is_faster`, `same_frequency`, or `no_result` is proposed, THE Response_Composer SHALL verify the claim deterministically against the Verified_Figure_Set under identical service type, frequency, supply configuration, and unit of measure before the claim appears in any visible output.
4. IF a proposed claim cannot be verified against the Verified_Figure_Set, THEN THE Response_Composer SHALL omit the claim from the visible output by default, and SHALL return an `INSUFFICIENT_INFORMATION` outcome when the claim is required to answer the turn, AND SHALL NOT present the unverified claim as fact.
5. THE Response_Composer SHALL verify non-numeric claims as well as numeric claims, such that a false non-numeric assertion is removed even when it contains no digits.
6. WHERE a figure originates from the user, THE Response_Composer SHALL label it as a Declared_Requirement AND SHALL NOT present it as a catalog specification.
7. WHEN a chart is produced, THE Response_Composer SHALL populate each chart series from backend-provided verified facts bound to typed placeholders AND SHALL NOT populate a chart series from language-model output.
8. WHERE a compared or displayed field carries an N/A or absent state, THE Response_Composer SHALL present that field with its explicit state AND SHALL NOT render it as zero, as a zero-height bar, or as a comparison winner.
9. WHEN FLA values originate from heterogeneous supply configurations, THE Response_Composer SHALL present each value with its supply condition AND SHALL NOT present the comparison as a lower-energy-consumption or efficiency claim.
10. WHERE no evidence in the Verified_Figure_Set supports a proposed assertion, THE Response_Composer SHALL remove the assertion from the visible output, such that no unreviewed language-model string carries an unsupported technical claim.

### Requirement 9: Multi-Turn Memory and Context

**User Story:** As a user, I want references like "the second one" or a previous model resolved against persisted conversation state, so that follow-ups stay accurate across turns and restarts without mixing another user's context. *(Traces: US-022, US-023, US-026, F2 §7. Classes: [ASSESS])*

#### Acceptance Criteria

1. WHEN a follow-up references an ordinal (for example "the second one"), a previously mentioned model, or a prior criterion, THE Agent_Orchestrator SHALL resolve the reference exclusively against the referents, criteria, and plan revision recorded in the persisted domain conversation state of Spec 3 for the active conversation, AND SHALL NOT re-derive the referent from the prose message history.
2. IF a reference resolves to more than one plausible referent in the persisted domain conversation state, THEN THE Agent_Orchestrator SHALL place the turn in `NEEDS_CLARIFICATION`, request disambiguation from the user, AND SHALL NOT resolve, execute, or silently switch to any one of the candidate referents or to a different model until the user supplies a disambiguating reply.
3. THE Agent_Orchestrator SHALL treat the persisted domain conversation state as the single authority for referents, criteria, and plan revision, AND SHALL NOT treat the prose message history as the sole authority.
4. THE Agent_Orchestrator SHALL keep a conversation pinned to exactly one `catalog_edition_id` for the lifetime of the conversation.
5. THE Agent_Orchestrator SHALL set the response language to the natural language of the last user turn unless the user explicitly requests a language switch, independent of the language of part numbers and units, AND IF the last user turn contains no detectable natural-language content (for example a part number, ordinal, or numeric-only turn), THEN THE Agent_Orchestrator SHALL retain the response language in effect for the immediately preceding turn of the conversation.
6. WHEN a conversation is resumed after a restart, THE Agent_Orchestrator SHALL resolve references using only the restored persisted domain state that belongs to that conversation and its owner, AND SHALL NOT resolve any reference against the domain state of a different conversation or a different owner.
7. IF a reference resolves to no matching referent in the persisted domain conversation state, THEN THE Agent_Orchestrator SHALL place the turn in `NEEDS_CLARIFICATION`, indicate to the user that the referenced item cannot be located in the conversation context, AND SHALL NOT substitute a guessed referent or model.

### Requirement 10: Abstention, Out-of-Scope, and the Fallback Matrix

**User Story:** As a user, I want clear abstention when a question falls outside the provided documents and predictable handling of every failure condition, so that the assistant never invents external facts and never mishandles an error as a different kind of error. *(Traces: US-023, US-025, QA-10, F2 §10, F2 §8, F3-AT11. Classes: [ASSESS])*

#### Acceptance Criteria

1. WHEN a user asks for information that is not present in the content of the pinned PDF edition, THE Agent_Orchestrator SHALL respond with an abstention that names the pinned source edition and states that the requested information is outside that source, AND SHALL NOT include any technical fact, figure, part attribute, or recommendation that is not traceable to a cell or passage in the pinned source.
2. WHEN any one of the following Fallback_Matrix conditions is detected, THE Agent_Orchestrator SHALL produce only the business response and execution rule defined for that condition: (a) invalid part-number format — request a correction and perform no lookup tool call; (b) part number well formed but not listed — report that the part is not listed in the document; (c) part listed with N/A attributes — report documentary existence and absence of the attribute, returning neither a zero-match nor a verifiable ranking; (d) zero matches — report the applied constraints and that none matched and allow the user to adjust; (e) incomplete recommendation — return results labeled as preliminary with the outstanding questions and without asserting final compatibility; (f) ambiguous AND/OR filter — request clarification without silently changing operator precedence and set the plan to AWAITING_CONFIRMATION; (g) frequency or service without supporting evidence — report the documented scope or request clarification without extrapolating; (h) out-of-scope query — abstain without any external lookup or free knowledge; (i) withdrawn source edition — alert that the edition is withdrawn, leave history intact, and block any new recommendation; (j) tool or database unavailable — return a recoverable error carrying a correlation identifier; (k) model-provider 402 or quota exceeded — return a clear error without inventing a response and without switching to an unauthorized provider; (l) prompt injection or role escalation — ignore the malicious instruction and apply the enforced role-based access control without exposing system internals; (m) stale confirmation — report that the plan changed, show the current version, and not execute the superseded plan; (n) delete versus late job — ensure the conversation does not reappear via a durable cancellation and write guard.
3. WHEN a tool returns a semantic `NO_RESULTS` or `N_A` business outcome, THE Agent_Orchestrator SHALL present it as a successful business result AND SHALL NOT retry the language model or any tool as though a technical error had occurred.
4. IF a transient network, model-provider, or database error occurs on an idempotent operation, THEN THE Agent_Orchestrator SHALL retry at most a bounded maximum number of attempts using exponentially increasing backoff and only while the Turn_Budget has remaining capacity, AND SHALL NOT retry a non-idempotent operation or a semantic failure outcome.
5. IF a Turn_Budget limit is reached, THEN THE Agent_Orchestrator SHALL fail closed by terminating the turn with a typed outcome AND SHALL NOT initiate any further reasoning step or tool call for that turn.
6. WHEN the Agent_Orchestrator returns a failure outcome, THE Agent_Orchestrator SHALL surface exactly one typed code appropriate to the condition AND SHALL NOT expose a stack trace, a system prompt, SQL text, or a secret to the user.
7. IF a part number is well formed but absent from the pinned edition, THEN THE Agent_Orchestrator SHALL report that the part is not listed in the document AND SHALL NOT assert that the product does not exist commercially AND SHALL NOT substitute a similar part number.

### Requirement 11: OpenRouter Model Configuration and Bounded Budget (Harness-Ready)

**User Story:** As an evaluator, I want models configurable per function with bounded per-turn budgets and a respected spend cap, so that Spec 6 can run the A/B comparison and model selection without this layer presuming any result or exceeding the budget. *(Traces: F2 §8, F2 §9, F2 v1.1 addendum, EN-09. Classes: [APPROVED], [EXPERIMENT])*

#### Acceptance Criteria

1. THE Agent_Orchestrator SHALL read the model assignment for each Model_Function from environment variables — `AGENT_MODEL`, optional `INTERPRETER_MODEL`, optional `ANSWER_MODEL`, and optional `FALLBACK_MODEL` — AND SHALL NOT hardcode a model identifier in the shipped code path.
2. THE Agent_Orchestrator SHALL support configuring at least two candidate models per evaluated function (interpretation, tool-calling, explanation) for Spec 6 to compare, AND having several models configured SHALL NOT cause more than one model call per Model_Function per turn beyond the configured `max_model_calls_per_turn`.
3. THE Agent_Orchestrator SHALL NOT assume that a provider endpoint supports simultaneous native tool-calling and structured output, AND SHALL verify the exact endpoint capability before issuing a request, separating a structured-interpretation phase from a tool-invocation phase where the endpoint does not support both together.
4. IF endpoint capability verification determines that a required feature is unavailable on the configured provider endpoint, THEN THE Agent_Orchestrator SHALL route to the separated-phase path or fail closed with an error indicating the unsupported capability, AND SHALL NOT silently proceed against an incompatible endpoint.
5. WHERE a model feature such as structured output or tool-calling is required, THE Agent_Orchestrator SHALL route the OpenRouter request with `require_parameters=true`, AND IF no provider satisfies the required parameters, THEN THE Agent_Orchestrator SHALL reject the request rather than selecting an incompatible provider.
6. THE Agent_Orchestrator SHALL enforce the Turn_Budget — `max_model_calls_per_turn`, `max_tool_calls_per_turn`, `max_token_budget`, `max_walltime`, `max_cost_usd`, and `max_result_rows` — with conservative configurable defaults, and WHEN any Turn_Budget limit is reached THE Agent_Orchestrator SHALL halt further model and tool calls for that turn, indicate which limit was reached, and preserve any results already produced.
7. THE Agent_Orchestrator SHALL record OpenRouter provider, model, and observed usage in the Cost_Ledger AND SHALL respect the USD 10.00 hard cap such that at most USD 6.00 is consumable for development and evaluations and at least USD 4.00 remains reserved for the final demo.
8. IF cumulative development-and-evaluation spend recorded in the Cost_Ledger reaches USD 6.00, THEN THE Agent_Orchestrator SHALL block further development or evaluation model calls, preserving the USD 4.00 demo reserve.
9. THE Agent_Orchestrator SHALL NOT invoke a language model to produce titles, rankings, or technical numbers, keeping those functions deterministic.
10. THE Agent_Orchestrator SHALL NOT declare a winning model or a winning tool set, AND the model-selection and tool-set A/B comparison SHALL remain an experiment resolved by `evaluation-and-reproducibility` (Spec 6), with no fabricated evaluation result asserted by this layer.
11. WHEN an automatic provider fallback occurs, THE Agent_Orchestrator SHALL NOT allow the fallback to silently change the required capabilities or privacy requirements of the request, AND IF the fallback provider cannot meet those required capabilities or privacy requirements, THEN THE Agent_Orchestrator SHALL abort rather than proceed.

### Requirement 12: Verified-Output Invariant (Cross-Cutting)

**User Story:** As a data steward, I want a single central guarantee that every visible technical figure traces to Spec 2 facts, so that the language model can compose prose and select tools but never produce an authoritative number. *(Traces: US-010, US-016, US-019, US-020, US-024, US-034, QA-01, AT-17, F2 §6. Classes: [ASSESS])*

#### Acceptance Criteria

1. THE Agent_Orchestrator SHALL ensure that every technical figure visible in `answer`, any `content_block`, any chart series, or any highlight traces to exactly one fact or one deterministic derivation in the Spec 2 Verified_Figure_Set, with no number sourced from a language model.
2. WHEN a technical figure is presented, THE Agent_Orchestrator SHALL carry its Data_Status (one of `AVAILABLE`, `NOT_APPLICABLE`, `NOT_DOCUMENTED`, `NOT_LISTED`, or `UNVERIFIED`) and its Evidence_Reference through to the composed output, such that each presented number resolves to at least one Published_Catalog source cell.
3. WHEN a Derived_Value is presented, THE Agent_Orchestrator SHALL label it as derived with its formula and applied precision AND SHALL NOT present it as an official documented value.
4. THE LangChain_Agent SHALL be permitted to compose prose and select among allow-listed tools, AND SHALL NOT be the source of any authoritative product number.
5. WHEN the same part, edition, service, and frequency are queried across turns, THE Agent_Orchestrator SHALL present technical numbers equal, digit-for-digit at the stored precision, to those of the Spec 2 Verified_Figure_Set on every repetition, providing the single figure source shared by `answer` and the structured `content_blocks`.
6. IF a requested technical fact has no supporting Verified_Figure_Set value, THEN THE Agent_Orchestrator SHALL present an explicit unavailable or not-documented state carrying no technical number AND SHALL NOT fabricate a value to fill the gap.
7. THE Agent_Orchestrator SHALL suppress from the visible output any candidate technical figure that does not trace to a Spec 2 Verified_Figure_Set fact or deterministic derivation, such that no language-model-sourced number reaches the user.
8. IF a presented figure's Evidence_Reference does not resolve to a Published_Catalog source cell, THEN THE Agent_Orchestrator SHALL withhold that figure from the visible output and surface an unavailable state rather than present an unverifiable number.
