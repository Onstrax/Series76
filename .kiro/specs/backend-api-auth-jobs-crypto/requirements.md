# Requirements Document

## Introduction

**Backend API, Auth, Jobs & Crypto (Spec 3 of 6).**

This specification defines the **FastAPI backend** of the *Series 76 Technical Assistant* (Konecto technical assessment): the HTTP contracts, authentication, authorization and ownership isolation, persistence of conversations and jobs, the durable PostgreSQL-backed job queue with leasing and fencing, the application-layer AES-256-GCM cryptography and key lifecycle, and the separate worker process. It is the trust, transport, and durability boundary that wraps the deterministic domain layer and hosts the agent runtime.

This layer **establishes identity and trust**, **persists and protects** conversation data, **serializes turns durably per session**, and **shapes the response envelope** that the agent and the Android app depend on. It executes typed, already-authorized reads against the domain layer (Spec 2) and never lets a language model author SQL, pick an edition, or dictate a technical number.

This spec is **Spec 3 of 6**. It **depends on**:
- `data-and-ingestion` (Spec 1) — specifically the published `Catalog_Store` surface and the `runtime_catalog_reader` least-privilege PostgreSQL role, the immutable `Catalog_Edition` facts, and edition withdrawal semantics.
- `domain-and-tools` (Spec 2) — the pure domain operations, deterministic services, custom LangChain tools, the `Semantic_Failure_Code` set, and the **verified figure set** that the final `answer` and the structured `content_blocks` will share.

It is **consumed by**:
- `agent-orchestration-response` (Spec 4) — which plugs its agent logic, interpretation, plan versioning, and response composition into the endpoints, DTOs, job states, and the encrypted checkpoint surface defined here.
- `android-app` (Spec 5) — which consumes these HTTP contracts, the typed envelope, auth flows, and polling protocol.

> **Important status note:** Nothing in this document asserts that any migration has been run, any server has been started, any test has been executed, any encryption has been validated against a live database, or any latency/cost has been measured. Every acceptance criterion below is a **contract to be verified** by later implementation and by `evaluation-and-reproducibility` (Spec 6) and F5, never a claim that verification has already happened.

### Legend of Requirement Classes

Each requirement is tagged with one or more classes, following the F0–F6 handoff distinction:

- **[ASSESS]** — Mandatory requirement from the Konecto assessment (`assessment-en.pdf`).
- **[APPROVED]** — Approved addition or decision beyond the raw assessment, ratified in the F0–F6 handoff (including F3-D01/F3-D02 and the F3-ARCH-01 option A ratification).
- **[DELEGATED]** — Delegated technical detail that Kiro may concretize (exact types, library choices, index microstructure, DTO field names, HTTP nuances) while preserving the approved invariants.
- **[EXPERIMENT]** — Requires real execution, benchmark, or measurement to satisfy; cannot be satisfied by design alone.

### Source-of-Truth Precedence

When sources conflict, the following precedence governs this spec:

1. **`assessment-en.pdf`** — authoritative for external obligations: FastAPI + PostgreSQL in Docker Compose, the mandatory `POST /api/conversation` contract, at least one custom LangChain tool, no free text-to-SQL, optional login (elected), Developer Debug screen scope, reproducibility.
2. **Published Catalog (Spec 1) and Domain layer (Spec 2)** — the single source of technical numbers and conditions. This backend **passes through** the verified figure set; it never computes, infers, or invents a technical number.
3. **Approved F3 decisions** — F3-D01 (opaque tokens, option B), F3-D02 (mandatory sync endpoint + async jobs, option B), F3-ARCH-01 (option A: Feature-First + light hexagonal), F3-D03..D12 technical defaults, and the pre-authorized AES-EAX checkpoint-blob contingency.
4. **`series_76_summary.pdf`** — business/narrative **context only**; never a source of technical values.

**Figure-set reminder:** the public catalog technical figures and the minimal structural indexes needed to operate may remain cleartext. Everything sensitive — titles, messages, domain state, plans, sensitive tool traces, and agent checkpoints — is encrypted before it is persisted. No number in any `answer`, `content_block`, or chart is produced by this backend; the backend relays the deterministic, evidence-backed figures supplied by Spec 2 and composed by Spec 4.

### Non-Goals (Out of Scope for This Spec)

- **No agent reasoning, LLM calls as logic, intent interpretation, plan authoring, or response-text composition.** The agent's reasoning, interpretation summaries, filter-AST authoring from natural language, ranking orchestration, and the population of `content_blocks` with verified figures belong to `agent-orchestration-response` (Spec 4). This spec defines **only** the endpoints, DTOs, job states, and the encrypted-checkpoint surface the agent plugs into. The `content_blocks` are defined **structurally** here (the envelope shape); their verified-figure population is Spec 2/4.
- **No domain SQL, typed repositories over the catalog, ranking/comparison/conversion math, or custom tool logic.** These belong to `domain-and-tools` (Spec 2). This layer injects an authorized edition and permission context and invokes those typed operations; it does not implement them.
- **No Android UI, local cache, Keystore, or rendering.** These belong to `android-app` (Spec 5). This layer serves contracts and typed envelopes only.
- **No ingestion, extraction, audit, or edition publication.** These belong to `data-and-ingestion` (Spec 1).
- **No eval harness, A/B tool comparison, model selection, accuracy thresholds, or cost-gate conclusions.** These belong to `evaluation-and-reproducibility` (Spec 6).

### Traceability Summary

| This spec traces to | Items |
|---|---|
| User stories | US-001, US-002, US-003, US-004, US-005, US-006, US-007, US-008, US-013, US-025, US-029, US-030, US-032, US-033, US-034, US-036, and US-035 (delete-race cross-cutting scenario) |
| QA scenarios | QA-04 (consistency), QA-06 (authorization), QA-07 (authentication), QA-08 (privacy/encryption/deletion), QA-11 (traceability) |
| F3 acceptance tests | F3-AT01 (login/refresh/logout revocation), F3-AT02 (register role forcing), F3-AT03 (debug IDOR), F3-AT04 (mandatory POST), F3-AT05 (concurrent turns), F3-AT06 (idempotency), F3-AT07 (worker interruption/lease), F3-AT08 (delete during LLM), F3-AT09 (DB dump no plaintext), F3-AT10 (Android cross-token), F3-AT11 (catalog failure), F3-AT12 (clean Docker Compose) |
| F0 acceptance tests | AT-05 (plan versioning), AT-10 (IDOR), AT-13 (delete & traces), AT-14 (delete/job race), AT-16 (title/content encryption) |
| F3 contracts | F3 consolidated contract table; F3-D01..D12; §4 API inventory; §5 envelopes; §7 crypto; §8 concurrency |

## Glossary

- **Backend**: The FastAPI modular monolith (api/application/domain/infrastructure, Feature-First) plus the separate worker process, sharing one image and codebase.
- **API_Process**: The deployment process serving HTTP requests via FastAPI.
- **Worker_Process**: A separate deployment process built from the same image/codebase that consumes durable jobs and runs the agent turn outside any SQL transaction.
- **Use_Case**: An application-layer service that authorizes, controls the transaction boundary (Unit of Work), and invokes domain operations.
- **Repository**: A typed data-access component for persisting and reading application aggregates (conversations, sessions, jobs, traces), distinct from the Spec 2 catalog read surface.
- **Unit_Of_Work**: The SQLAlchemy transaction boundary coordinated by a Use_Case (begin/commit/rollback); no Repository commits arbitrarily.
- **DTO**: A Pydantic request/response data type at the API boundary, distinct from the domain model and the ORM model, that never exposes secrets or ORM internals.
- **DB_Role**: A per-service least-privilege PostgreSQL role — `app_writer` (application read/write), `runtime_catalog_reader` (read-only catalog, defined by Spec 1), `ingest_publisher` (ingestion/publication, Spec 1).
- **User**: An authenticated account with role `user`, the only role creatable through the public registration endpoint.
- **Developer**: An account with role `developer`, provisioned only via CLI/seed, able to inspect the Debug traces of its own conversations and not a superuser.
- **Auth_Session**: A server-side login session identified by `auth_session_id`, distinct from a conversation `session_id`, holding a rotating refresh-token family and associated access tokens.
- **Opaque_Token**: A high-entropy random access or refresh token whose server-side verifier is a SHA-256 hash of the secret, compared in constant time; the token is never stored in plaintext.
- **Refresh_Family**: The chain of rotating refresh tokens belonging to one Auth_Session; reuse detection revokes the entire family.
- **Owner_User_Id**: The authoritative identifier of a resource's owner, resolved from the validated session and never read from the request body.
- **Conversation**: A persisted dialogue identified by `session_id`, owned by exactly one User, pinned to one `catalog_edition_id`.
- **Turn_Job**: A durable, persisted command to process one conversation turn, carrying ordering, lease, fencing, and idempotency metadata.
- **Job_State**: One of `QUEUED`, `RUNNING`, `NEEDS_CLARIFICATION`, `AWAITING_CONFIRMATION`, `COMPLETED`, `FAILED`, `CANCELLED`, `STALE_PLAN`, `CATALOG_WITHDRAWN`.
- **Accepted_Seq**: A per-conversation monotonically assigned sequence that defines turn order, set under a transactional acceptance step and not inferred from queue claim order.
- **Lease**: A time-bounded claim on a Turn_Job expressed by `lease_expires_at`, under which exactly one Worker_Process may process the job.
- **Fencing_Token**: A monotonic token guarding late writes so a stale lease holder cannot persist a result after its lease expired.
- **Client_Request_Id**: A caller-supplied idempotency key enforced by `UNIQUE(owner_id, client_request_id)` for a logical turn attempt.
- **Plan_Revision**: A monotonic revision number of a conversation's interpreted plan; only the current revision may be confirmed.
- **Response_Envelope**: The typed response of the mandatory endpoint and of a completed job, always carrying `session_id` and `answer`, plus optional typed fields.
- **Content_Block**: A typed, discriminated element of the Response_Envelope (`text`, `product_card`, `comparison_table`, `matching_part_numbers`, `bar_chart`, `clarification`, `plan_review`); defined structurally here and populated with verified figures by Spec 2/4.
- **DEK**: A per-conversation Data Encryption Key used for AES-256-GCM encryption of that conversation's sensitive data.
- **KEK**: A Key Encryption Key held outside the database that wraps each DEK.
- **Crypto_Shredding**: Rendering a conversation's sensitive data unrecoverable from active storage by deleting its DEK.
- **Checkpoint**: A LangGraph agent-state checkpoint blob (including pending writes) persisted by this layer in encrypted form.
- **Error_Envelope**: The stable typed error response with `error.code`, `error.user_message` (ES/EN), `request_id`, `retryable`, and sanitized `details`.
- **Tombstone**: A deletion marker/write-guard that blocks resurrection of a deleted conversation by late writes.

## Requirements

### Requirement 1: Architecture and Process Model

**User Story:** As a backend maintainer, I want a Feature-First modular monolith with a light hexagonal boundary and a separate worker process on the same image, so that domain rules stay testable, deployment stays simple, and the API never blocks on long agent work. *(Traces: F3-ARCH-01 option A, F3-D03, F3-D04, F3-D09, QA reproducibility. Classes: [APPROVED], [DELEGATED])*

#### Acceptance Criteria

1. THE Backend SHALL organize code Feature-First with a light hexagonal separation into api, application, domain, and infrastructure boundaries, such that the domain layer imports neither FastAPI, SQLAlchemy, LangChain, nor any provider SDK.
2. THE Backend SHALL serve persistence reads and writes through typed Repositories whose transactions are controlled by Use_Cases via a Unit_Of_Work, AND SHALL NOT allow a Repository to commit a transaction on its own.
3. THE Backend SHALL expose and accept data at the HTTP boundary exclusively through Pydantic DTOs that are distinct from domain models and ORM models, AND SHALL NOT introduce a redundant DAO layer alongside a Repository over the same table.
4. THE Backend SHALL run the API_Process and the Worker_Process as two separate processes built from the same image and codebase, AND SHALL NOT require a separately maintained worker codebase or an external message broker.
5. THE Backend SHALL connect to PostgreSQL provisioned via Docker Compose using per-service DB_Roles — `app_writer` for application data, `runtime_catalog_reader` for catalog reads, and `ingest_publisher` reserved for ingestion — such that the application data path has no ingestion staging privileges and the catalog read path has no application write privileges.
6. THE Backend SHALL NOT execute any SQL string generated by a language model, AND SHALL route every catalog read through the typed domain operations of Spec 2.
7. IF a code path attempts to execute a SQL string that originated from a language model, THEN THE Backend SHALL reject the execution, return no catalog data to the caller, and surface an error indicating that LLM-generated SQL is not permitted.
8. WHERE dependency wiring is required, THE Backend SHALL compose dependencies through a light dependency-injection mechanism at a bootstrap/composition root using only the dependency-injection facilities FastAPI provides, AND SHALL NOT introduce an additional DI container framework.
9. WHILE the Worker_Process is executing an agent task, THE Backend SHALL continue to accept and respond to API_Process HTTP requests without blocking on completion of that worker task.

### Requirement 2: Authentication with Opaque Tokens

**User Story:** As a user, I want to register and log in with credentials protected by strong hashing and server-revocable opaque tokens, so that my sessions can be revoked immediately and my password is never recoverable. *(Traces: US-001, US-033, US-036, QA-07, F3-D01, F3-AT01, F3-AT02. Classes: [ASSESS], [APPROVED])*

#### Acceptance Criteria

1. THE Backend SHALL store every user password using Argon2id with a per-password random salt of at least 128 bits, AND SHALL NOT apply a bare SHA-256 or any unsalted fast hash to a password.
2. THE Backend SHALL issue access and refresh tokens as Opaque_Tokens generated from a CSPRNG with at least 128 bits of entropy, preferring 256 bits, AND SHALL store only a SHA-256 verifier of each token secret, comparing presented tokens against the stored verifier in constant time such that comparison duration does not vary with the number of matching leading characters.
3. WHEN a visitor invokes `POST /api/auth/register` with a unique well-formed email of 3 to 254 characters and a password of 12 to 128 characters that satisfies the approved strength policy (minimum 12 characters), THE Backend SHALL create an account with role `user` assigned server-side, AND SHALL ignore or reject any client-supplied role or privilege field such that the created account can never be `developer`.
4. IF `POST /api/auth/register` is invoked with an already-registered email, an email outside 3 to 254 characters, a password outside 12 to 128 characters or failing the strength policy, or a value that would elevate role, THEN THE Backend SHALL reject the request with a typed validation error that does not reveal whether any unrelated account exists, SHALL NOT create any account, AND SHALL NOT create a `developer` account.
5. WHEN `POST /api/auth/login` is invoked with credentials that do not match a stored account, THE Backend SHALL return a generic `401` whose body and timing do not distinguish an unknown email from a wrong password, AND SHALL reject further login attempts for the same source after 5 consecutive failures within a 15-minute window until the window elapses.
6. WHEN `POST /api/auth/refresh` is invoked with the current unexpired refresh token of an Auth_Session, THE Backend SHALL atomically rotate the refresh token, invalidate the presented token, and return a new refresh token within the same Refresh_Family, such that two concurrent refresh requests presenting the same token result in at most one succeeding and the other being rejected.
7. IF `POST /api/auth/refresh` is invoked with a previously rotated or revoked refresh token, THEN THE Backend SHALL detect the reuse, SHALL revoke the entire Refresh_Family so that no token in that family authorizes any subsequent request, AND SHALL return an error indicating the session is invalid that requires a fresh login.
8. WHEN `POST /api/auth/logout` is invoked, THE Backend SHALL revoke server-side the refresh family and associated access tokens of the current login session such that any token from that session no longer authorizes any request within at most 1 second of the revocation completing, AND SHALL leave other devices' sessions authorizing normally unless the caller explicitly requests revoking them.
9. WHEN `GET /api/auth/me` is invoked with a valid unexpired access token, THE Backend SHALL return the caller's identity and role, AND SHALL NOT include password hashes, token secrets, or token verifiers in the response.
10. WHERE no real email-sending mechanism is implemented, THE Backend SHALL treat the registered email as an unverified identifier AND SHALL NOT represent the email as verified, with the verification limitation documented for production.
11. THE Backend SHALL provision `developer` accounts only through a CLI or seed procedure, SHALL NOT provision or elevate a `developer` through any public endpoint, AND SHALL keep seedable demo `user` and `developer` accounts out of the repository as real credentials, using placeholder or seed configuration instead.

### Requirement 3: Authorization and Ownership Isolation

**User Story:** As a user, I want every access to my conversations, jobs, and traces to be checked against authoritative ownership, so that no other user — not even a developer — can read or affect my data. *(Traces: US-002, US-003, QA-06, AT-10, F3-AT03. Classes: [ASSESS], [APPROVED])*

#### Acceptance Criteria

1. WHEN any conversation, job, plan, message, or trace is queried or mutated, THE Backend SHALL scope the operation by an authoritative Owner_User_Id resolved from the validated session token, AND SHALL NOT derive ownership from any value supplied in the request body, query parameters, or request headers.
2. IF a request body, query parameter, or header supplies an owner identifier that differs from the Owner_User_Id resolved from the validated session, THEN THE Backend SHALL ignore the supplied identifier and SHALL use only the session-resolved Owner_User_Id to scope the operation.
3. IF an authenticated caller requests a conversation, job, plan, message, or trace whose stored Owner_User_Id does not equal the caller's session-resolved Owner_User_Id, THEN THE Backend SHALL deny the operation, SHALL return a `404 Not Found` response that does not confirm the resource's existence, AND SHALL NOT return any field, metadata, or count belonging to the other user's resource.
4. THE Backend SHALL complete the authorization check that compares the caller's session-resolved Owner_User_Id against the target resource's stored Owner_User_Id before performing any decryption of a title, message, plan, or trace, such that a request failing the ownership check is rejected with no decryption operation performed on the target resource.
5. THE Backend SHALL treat the `developer` role as enabling Debug capabilities only over resources whose stored Owner_User_Id equals the developer's own session-resolved Owner_User_Id, AND SHALL deny a caller holding the `developer` role access to any conversation, job, plan, message, or trace owned by a different Owner_User_Id, returning the same `404 Not Found` response defined in criterion 3.
6. THE Backend SHALL evaluate endpoint-level ownership and role authorization within the request-handling path before dispatching to any language model or custom tool, such that no language model output or custom tool invocation can cause the Backend to return or mutate a resource that the endpoint's ownership or role check would deny.

### Requirement 4: Mandatory Synchronous Conversation Endpoint

**User Story:** As an assessment evaluator, I want the mandatory `POST /api/conversation` endpoint to always return `session_id` and `answer`, so that the required contract holds regardless of the async queue. *(Traces: US-004, US-006, US-034, F3-AT04, F3-D02. Classes: [ASSESS])*

#### Acceptance Criteria

1. THE Backend SHALL expose `POST /api/conversation` accepting a request with an optional `session_id` and a required `query` of 1 to 4000 characters, AND SHALL always return a final response containing both a non-empty `session_id` and a non-empty `answer`.
2. WHEN `POST /api/conversation` is invoked without a `session_id`, THE Backend SHALL create a new Conversation owned by the caller, associate the first turn, and return its stable `session_id` in the response.
3. WHEN a final response is returned, THE Backend MAY include typed optional fields — `content_blocks`, `status`, `interpretation_summary`, `plan`, `warnings`, `request_id`, `catalog_edition_id` — AND SHALL keep `session_id` and `answer` present in every final response regardless of which optional fields are included.
4. WHEN the turn requires clarification or confirmation rather than a final technical result, THE Backend SHALL return a non-empty conversational `answer` together with a `status` whose value is `clarification` or `confirmation`, AND SHALL NOT include any technical number that is not part of the verified figure set from Spec 2/4.
5. WHEN a conversation is resumed after an API_Process or Worker_Process restart, THE Backend SHALL return the persisted multi-turn history and confirmed context for that conversation, scoped exclusively to the owning caller so that no turn, message, or context belonging to any other owner is included.
6. WHEN `POST /api/conversation` is retried with the same `Client_Request_Id` for the same owner, THE Backend SHALL treat the retry as idempotent, SHALL NOT create a duplicate conversation or duplicate turn, AND SHALL return the final response produced for the original request.
7. THE Backend SHALL keep the `POST /api/conversation` request and response contract — optional `session_id` plus required `query` in, `session_id` plus `answer` always out — inviolable, such that the presence, behavior, or outcome of the asynchronous job queue SHALL NOT alter, replace, or invalidate this contract.
8. THE `content_blocks` field SHALL be defined structurally by this layer as a discriminated union of typed block kinds, AND the population of those blocks with verified technical figures SHALL remain owned by `domain-and-tools` (Spec 2) and `agent-orchestration-response` (Spec 4).
9. IF `POST /api/conversation` is invoked with a missing, empty, or whitespace-only `query`, or a `query` exceeding 4000 characters, THEN THE Backend SHALL reject the request without creating a Conversation or turn and SHALL return an error response indicating the `query` validation failure.
10. IF `POST /api/conversation` is invoked with a `session_id` that does not exist or is not owned by the caller, THEN THE Backend SHALL reject the request without creating or modifying any Conversation or turn and SHALL return an error response indicating the session is not found or not accessible.

### Requirement 5: Asynchronous Jobs and Polling

**User Story:** As a mobile client, I want to enqueue a turn and poll for its result, so that the UI never blocks on long agent work while still receiving the same final envelope. *(Traces: US-029, F3-D02, F3-AT05. Classes: [APPROVED])*

#### Acceptance Criteria

1. WHEN `POST /api/conversation/jobs` is invoked with a valid authorized request, THE Backend SHALL return `202 Accepted` carrying `job_id`, `session_id` (creating the conversation if `session_id` was omitted), and a `status` field whose value is exactly one of the Job_State enum values and is `QUEUED` at acceptance time.
2. IF `POST /api/conversation/jobs` is invoked with a request that fails validation or authorization, THEN THE Backend SHALL reject the request without enqueuing a job, SHALL NOT create or modify any Turn_Job or conversation, AND SHALL return an error outcome indicating validation failure or missing authorization.
3. WHEN `GET /api/jobs/{id}` is invoked by the job's owner, THE Backend SHALL return the current Job_State, AND WHEN that Job_State is `COMPLETED`, THE Backend SHALL additionally return the final result using the same Response_Envelope as the mandatory `POST /api/conversation` endpoint, always including `session_id` and `answer`.
4. IF `GET /api/jobs/{id}` or `POST /api/jobs/{id}/cancel` is invoked by a requester who is not the job's owner, THEN THE Backend SHALL reject the request without disclosing whether the job exists AND SHALL NOT return any Job_State, result, or envelope belonging to another user.
5. WHEN `POST /api/jobs/{id}/cancel` is invoked by the job's owner while the Job_State is `QUEUED`, `RUNNING`, `NEEDS_CLARIFICATION`, or `AWAITING_CONFIRMATION`, THE Backend SHALL request cancellation and return a cancellation-accepted status; AND WHEN the same cancel request is repeated against the same job, THE Backend SHALL return the same cancellation-accepted status and SHALL NOT return an error distinct from the first response and SHALL NOT create an additional cancellation effect.
6. THE Backend SHALL represent every Turn_Job with exactly one Job_State drawn from `QUEUED`, `RUNNING`, `NEEDS_CLARIFICATION`, `AWAITING_CONFIRMATION`, `COMPLETED`, `FAILED`, `CANCELLED`, `STALE_PLAN`, or `CATALOG_WITHDRAWN`, and SHALL represent conversation state and plan state as values distinct from and independent of the Job_State.
7. WHEN `GET /api/jobs/{id}` returns a job whose Job_State is `COMPLETED`, `FAILED`, or `CANCELLED`, THE Backend SHALL set `Cache-Control: no-store`; AND WHEN it returns a job whose Job_State is `QUEUED`, `RUNNING`, `NEEDS_CLARIFICATION`, or `AWAITING_CONFIRMATION`, THE Backend SHALL set `Cache-Control: no-store` AND SHALL include a `Retry-After` header expressing a non-negative integer number of seconds between 1 and 60 inclusive.
8. THE Backend SHALL enforce a configurable maximum count of pending jobs (jobs whose Job_State is `QUEUED`, `RUNNING`, `NEEDS_CLARIFICATION`, or `AWAITING_CONFIRMATION`) per user and a configurable maximum count per session, each with a default of 5 and a permitted configured range of 1 to 100 inclusive.
9. IF accepting a new job via `POST /api/conversation/jobs` would exceed the configured per-user or per-session pending-job limit, THEN THE Backend SHALL reject the new job without enqueuing it, SHALL leave existing jobs and conversation state unchanged, AND SHALL return a rate-limit error outcome.
10. THE Backend SHALL NOT reuse the `202 Accepted` job acceptance as a substitute for the final response of the mandatory `POST /api/conversation` endpoint, which SHALL always return its final `session_id` and `answer` via the Response_Envelope.

### Requirement 6: Durable Queue, Leases, Fencing, and Idempotency

**User Story:** As an operator, I want turns serialized per conversation on a durable PostgreSQL queue with leases and fencing, so that concurrent submissions, retries, and worker crashes never duplicate or corrupt a conversation. *(Traces: US-029, US-035, QA-04, F3-D05, F3-D06, F3-AT05, F3-AT06, F3-AT07. Classes: [ASSESS], [APPROVED])*

#### Acceptance Criteria

1. THE Backend SHALL persist Turn_Jobs durably in PostgreSQL such that after an API_Process or Worker_Process restart an accepted job remains retrievable with its state unchanged.
2. THE Backend SHALL allow at most one active (RUNNING) Turn_Job per conversation at any instant, AND SHALL allow Turn_Jobs of distinct conversations to run in parallel with no serialization between distinct conversations.
3. WHEN a turn is accepted, THE Backend SHALL assign its Accepted_Seq within the same atomic transaction as acceptance, as a strictly increasing per-conversation sequence that defines turn order, AND SHALL NOT assume that queue claim order (for example via `SKIP LOCKED`) is FIFO.
4. WHEN a Worker_Process claims a Turn_Job, THE Backend SHALL, within a transaction completing in at most 1 second and containing no external call, set `lease_expires_at` between 30 and 120 seconds in the future, assign a strictly monotonic `Fencing_Token`, and increment `attempt_count` by one, such that exactly one lease holder is authorized to persist that job's result.
5. IF a Turn_Job's lease has expired and the job is reclaimed, THEN THE Worker_Process SHALL verify whether a result already exists before re-sending the turn to the model, AND THE Backend SHALL reject any attempt to persist a result carrying a Fencing_Token older than the current one.
6. THE Backend SHALL NOT hold a SQL transaction open across a call to the language-model provider, AND SHALL persist state before and after the external call in separate transactions each completing in at most 1 second.
7. THE Backend SHALL enforce idempotency of accepted turns through a `UNIQUE(owner_id, client_request_id)` constraint, such that a repeated `Client_Request_Id` for the same owner is rejected as a duplicate and yields exactly one persisted turn effect.
8. THE Backend SHALL guarantee that database effects for a given accepted turn are idempotent, WHILE acknowledging that external model billing may occur at least once, AND SHALL NOT claim exactly-once external provider invocation.

### Requirement 7: Plan Confirmation and Revision

**User Story:** As a user, I want to confirm the exact plan revision I reviewed, so that a correction I made is never executed under a stale, previously approved plan. *(Traces: US-013, AT-05, F3 plan contract. Classes: [APPROVED])*

#### Acceptance Criteria

1. WHILE the caller is authenticated and is the owner of the conversation, WHEN `POST /api/sessions/{id}/plans/{rev}/confirm` is invoked with a `rev` equal to the conversation's current Plan_Revision, THE Backend SHALL record a confirmation bound to exactly that Plan_Revision and no other.
2. THE Backend SHALL assign Plan_Revision numbers as strictly increasing integers per conversation, such that any revision created later than another has a numerically greater Plan_Revision than every revision created before it.
3. IF a confirmation targets a Plan_Revision that is not the conversation's current revision, THEN THE Backend SHALL reject the request with `409` CONFLICT (STALE_PLAN), SHALL NOT execute the targeted plan, and SHALL leave the current Plan_Revision and its confirmation state unchanged.
4. WHEN the user corrects a plan, THE Backend SHALL create a new Plan_Revision with a numerically greater number than the prior revision and SHALL mark the prior revision as not the current revision, such that any subsequent confirmation of the prior revision is rejected per criterion 3 and triggers no execution.
5. WHEN the current Plan_Revision is confirmed two or more times by the owner, THE Backend SHALL record at most one confirmation for that revision and SHALL trigger at most one execution for that revision, returning a success response for each repeated confirmation without additional side effects.
6. IF `POST /api/sessions/{id}/plans/{rev}/confirm` is invoked by a caller that is not authenticated, THEN THE Backend SHALL reject the request with `401` (AUTH_REQUIRED), SHALL NOT record a confirmation, and SHALL NOT execute the plan.
7. IF the request is authenticated but the caller is not the owner of the conversation `{id}`, THEN THE Backend SHALL reject the request without revealing the existence of the conversation to the non-owner, SHALL NOT record a confirmation, and SHALL NOT execute the plan.
8. IF the targeted `rev` does not correspond to any Plan_Revision of the conversation `{id}`, THEN THE Backend SHALL reject the request with `404` (NOT_FOUND), SHALL NOT record a confirmation, and SHALL NOT execute any plan.

### Requirement 8: Deletion and No Resurrection

**User Story:** As a user, I want deleting a conversation to purge its content and cancel its jobs irrevocably from active storage, so that no late worker can bring it back and no title search leaks another user's data. *(Traces: US-005, US-007, US-008, US-035, QA-04, AT-13, AT-14, F3-AT08. Classes: [ASSESS], [APPROVED])*

#### Acceptance Criteria

1. WHEN `DELETE /api/sessions/{id}` is invoked by the owner for a conversation that exists and has not been previously deleted, THE Backend SHALL cancel the conversation's pending and active jobs, write a Tombstone/write-guard, purge from active storage the messages, domain state, checkpoints, sensitive traces, and the conversation's DEK, and return `204`, completing the purge within 5 seconds.
2. IF `DELETE /api/sessions/{id}` references a conversation identifier that has never existed or is not owned by the caller, THEN THE Backend SHALL respond with `404`, and IF it references a conversation that was previously deleted (Tombstone present), THEN THE Backend SHALL respond with `410`.
3. IF a Worker_Process attempts a write for a deleted conversation whose Fencing_Token is less than or equal to the token recorded in the Tombstone, THEN THE Backend SHALL block the write, such that the deleted conversation and its messages, checkpoints, and traces are not recreated.
4. WHEN a caller references a deleted conversation or a conversation not owned by the caller, THE Backend SHALL return a response that is indistinguishable (same status code `404`/`410` and no resource-specific body) regardless of whether the target resource exists, and SHALL NOT confirm the existence of, or return any attribute of, another user's resources.
5. WHEN `GET /api/sessions` is invoked, THE Backend SHALL return only the caller's conversations with titles and dates, and SHALL support title-only search by fetching at most the caller's own set of ciphertext titles (capped at 1000 entries per request) and decrypting after authorization, AND SHALL NOT search message bodies, perform `ILIKE` or any substring match over ciphertext, or return another user's conversations.
6. WHEN `GET /api/sessions/{id}/messages` is invoked by the owner, THE Backend SHALL return the conversation's persisted message history and typed blocks ordered by ascending creation timestamp (ties broken by ascending message identifier), AND SHALL NOT include debug traces.
7. WHEN `PATCH /api/sessions/{id}` is invoked by the owner to rename a conversation with a title of 1 to 200 characters, THE Backend SHALL persist the new encrypted title; IF the title is empty or exceeds 200 characters, THEN THE Backend SHALL reject the request with an error indicating invalid title length and leave the existing title unchanged; and IF the caller is not the owner, THEN THE Backend SHALL reject the rename and leave the existing title unchanged.
8. THE Backend SHALL NOT retain deleted conversations' sensitive content in queue, retry, or trace tables after deletion, AND SHALL document that immediate deletion applies to active storage while encrypted backups are retained for a finite window not exceeding 30 days and do not guarantee instantaneous physical deletion.
9. IF `DELETE /api/sessions/{id}` is invoked by a caller who is not the owner of an existing conversation, THEN THE Backend SHALL reject the request with `404` and SHALL NOT cancel jobs, write a Tombstone, or purge any content.

### Requirement 9: AES-256-GCM Cryptography and Key Lifecycle

**User Story:** As a security reviewer, I want sensitive data encrypted before it reaches PostgreSQL under per-conversation keys held outside the database, so that a stolen database copy yields no plaintext and deleting a key renders a conversation unrecoverable. *(Traces: US-007, US-008, EN-05, QA-08, AT-16, F3-D07, F3-D08, F3-AT09. Classes: [APPROVED])*

#### Acceptance Criteria

1. THE Backend SHALL encrypt sensitive data with AES-256-GCM in the application layer before persisting it to PostgreSQL, using a nonce of exactly 96 bits that is unique per key across all encryption operations and contextual AAD binding purpose, owner, conversation, record identifier, and format version, AND SHALL NOT reuse a key/nonce pair.
2. THE Backend SHALL encrypt conversation titles, message contents, domain state, plans, sensitive tool traces, and agent checkpoints (including pending writes) before persistence, AND SHALL leave as cleartext only public catalog technical figures and the non-sensitive index fields required for lookup, ordering, or foreign keys.
3. THE Backend SHALL use a per-conversation DEK wrapped by a KEK held outside the database, persisting only the wrapped DEK ciphertext together with key_metadata (`key_id`, `cipher_version`), AND SHALL NOT store the KEK in PostgreSQL or in the repository.
4. IF an AES-256-GCM authentication tag fails to verify, or a record is encountered as legacy plaintext where ciphertext is required, THEN THE Backend SHALL fail closed by refusing to return the data and surfacing an error rather than returning unauthenticated or plaintext content.
5. IF the KEK is unavailable or a DEK cannot be unwrapped, THEN THE Backend SHALL fail closed with a key-unavailable error, SHALL NOT return the affected data, AND SHALL NOT expose any key material.
6. THE Backend SHALL NOT log tokens, passwords, request headers carrying secrets, the KEK, or any DEK, in any log, trace, or observability output, whether encrypted or not.
7. WHEN a conversation is deleted, THE Backend SHALL perform Crypto_Shredding by deleting the conversation's DEK from active storage so that its sensitive ciphertext becomes unrecoverable from active storage, AND SHALL NOT promise instantaneous physical deletion from finite-retention backups.
8. THE Backend SHALL serialize LangGraph agent Checkpoints using AES-256-GCM encryption that fails closed on tag verification failure and is compatible with pending writes and recovery.
9. WHERE the LangGraph framework integration makes AES-256-GCM infeasible for the checkpoint blob, THE Backend MAY use a pre-authorized AES-EAX fallback for the checkpoint blob only, AND SHALL record that use via an ADR, AND SHALL NOT relax AES-256-GCM for titles, messages, domain state, plans, or traces.

### Requirement 10: Debug Trace Endpoint

**User Story:** As a developer, I want to inspect the sanitized tool activity of my own conversation turns, so that I can debug behavior without ever seeing secrets or another user's data. *(Traces: US-003, US-030, QA-11, AT-10, F3-AT03. Classes: [ASSESS], [APPROVED])*

#### Acceptance Criteria

1. WHEN `GET /api/sessions/{id}/messages/{mid}/trace` is invoked by a caller holding role `developer` who owns the conversation, THE Backend SHALL return the sanitized trace for that message.
2. IF the caller does not hold role `developer`, or does not own the conversation, or the conversation or message does not exist, THEN THE Backend SHALL deny the request with a byte-for-byte identical denial response that discloses nothing about whether the resource exists.
3. WHEN a trace is returned, THE Backend SHALL include only sanitized tool arguments, sanitized tool results, and timing values, AND the timing values SHALL be non-negative durations.
4. THE Backend SHALL NOT include in any returned trace any credential, token, request header, the KEK, any DEK, system prompt, or raw provider secret.
5. IF a developer A requests a trace belonging to developer B, THEN THE Backend SHALL deny the request using the same identical denial response as criterion 2, exposing none of B's trace.
6. WHEN a conversation is deleted, THE Backend SHALL purge its traces so that a subsequent trace request returns the identical denial response of criterion 2 and no trace content.

### Requirement 11: Error Envelope, HTTP Status, and Transport Security

**User Story:** As an API consumer, I want stable error codes, bilingual user messages, and secure transport, so that clients can handle failures predictably without leaking internals. *(Traces: US-025, QA-06, F3-D10, F3-D11, F3 §5 error envelope. Classes: [APPROVED], [DELEGATED])*

#### Acceptance Criteria

1. WHEN the Backend returns an error, THE Backend SHALL use an Error_Envelope with a stable `error.code` drawn from `VALIDATION_ERROR`, `AUTH_REQUIRED`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `STALE_PLAN`, `CATALOG_WITHDRAWN`, `JOB_CANCELLED`, `RATE_LIMITED`, `UPSTREAM_UNAVAILABLE`, `BUDGET_EXCEEDED`, or `INTERNAL_ERROR`, together with a localized `error.user_message` in the caller's language (ES or EN), a `request_id` that is unique per request and correlates the response to server logs, and a `retryable` flag whose value is consistent for a given `error.code`.
2. THE Backend SHALL return a `NO_RESULTS` outcome as a successful business result distinct from the `UPSTREAM_UNAVAILABLE` failure outcome, such that zero matches and a provider failure are never conflated.
3. WHEN the Backend returns an error, THE Backend SHALL NOT include SQL, prompts, secrets, stack traces, or sensitive PII in the response, and SHALL include only sanitized `details`.
4. THE Backend SHALL map outcomes to HTTP status codes consistently: `200` for responses, `201` for registration, `202` for accepted jobs, `204` for deletes, `400` for malformed requests and `422` for semantically invalid input, `401` for authentication, `403` for role denial, `404` for an owned-or-nonexistent resource, `409` for conflict/stale plan, `410` for an explicitly withdrawn or cancelled resource, `429` for rate limiting, `500` for an internal failure, and `503` for an unavailable upstream dependency.
5. THE Backend SHALL require HTTPS in production, AND SHALL permit a documented, narrowly scoped local emulator HTTP loopback exception for development without enabling global cleartext traffic in a release configuration.
6. WHEN `GET /api/health` is invoked, THE Backend SHALL return a liveness result without sensitive information; AND WHEN `GET /api/ready` is invoked, THE Backend SHALL return a readiness result that distinguishes database availability from other critical-dependency availability.

### Requirement 12: Reproducibility of the Backend

**User Story:** As an evaluator, I want to bring up the backend from a clean checkout with Docker Compose and documented placeholders, so that I can run the API, worker, and database without implicit steps or committed secrets. *(Traces: US-032, QA reproducibility, F3-AT12. Classes: [ASSESS])*

#### Acceptance Criteria

1. THE Backend SHALL provide a Docker Compose configuration defining `db` (PostgreSQL with a persistent volume), `api` (FastAPI), and `worker` (same image/codebase with the job-processor entrypoint).
2. THE Backend SHALL provide a documented, explicit database migration step (Alembic or an equivalent versioned mechanism) that runs and completes successfully before the API_Process and Worker_Process begin serving traffic; IF the migration step fails, THEN the API_Process and Worker_Process SHALL NOT begin serving traffic and the failure SHALL be surfaced.
3. THE Backend SHALL provide a `.env.example` containing placeholder-only values for `DATABASE_URL`, `OPENROUTER_API_KEY`, `AGENT_MODEL`, `INTERPRETER_MODEL`, `ANSWER_MODEL`, `ENCRYPTION_KEK` (or its path), `AUTH_TOKEN_POLICY`, `GEMINI_API_KEY` (ingestion-only), and the time/queue/cost limits, AND SHALL NOT include real secrets.
4. THE Backend SHALL provide a seed CLI that creates the demo `user` and `developer` accounts without placing real credentials in the repository or image.
5. WHEN the language-model provider is unreachable, THE Backend SHALL still start the API_Process and Worker_Process, AND `GET /api/ready` SHALL return a result reflecting the degraded dependency rather than the process crashing on startup.
6. THE Backend SHALL NOT bake `.env` files, the KEK, or any secret into the built Docker image.
