# Requirements Document

## Introduction

**Android App (Spec 5 of 6).**

This specification defines the **native Android client** of the *Series 76 Technical Assistant* (Konecto technical assessment): the Kotlin + Jetpack Compose application, its five navigable destinations (Login, Register, Conversations, Chat, Developer Debug), its MVVM + unidirectional-data-flow presentation, its read-only local cache, its offline experience, and its accessibility and reproducibility obligations.

This layer is a **pure consumer and renderer**. It **consumes** the HTTP contracts, typed `Response_Envelope`, authentication flows, job-polling protocol, and error envelope established by `backend-api-auth-jobs-crypto` (Spec 3), and it **renders** the typed `content_blocks` composed by `agent-orchestration-response` (Spec 4). It presents what the backend returns; it never establishes identity, opens a transaction, encrypts server-side data, owns the queue, interprets intent, authors a plan, or composes a technical figure. The server is the single source of truth; the client does not infer, derive, re-rank, or recompute.

This spec is **Spec 5 of 6**. It **depends on**:

- `backend-api-auth-jobs-crypto` (Spec 3) — the HTTP contracts (`POST /api/conversation`, `POST /api/conversation/jobs`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel`, the auth endpoints, `GET /api/sessions` and related conversation endpoints, `POST /api/sessions/{id}/plans/{rev}/confirm`, `DELETE /api/sessions/{id}`, the trace endpoint, `GET /api/health`/`GET /api/ready`), the typed `Response_Envelope` with `session_id` + `answer` always present, the `Content_Block` discriminated union defined structurally, the `Job_State` set, the opaque-token auth and refresh-rotation flow, the idempotency contract via `Client_Request_Id`, the `Plan_Revision` confirmation semantics with `409` on stale, and the `Error_Envelope` with stable codes and bilingual user messages. This client **plugs into** these seams; it never defines them.

It is **evaluated by**:

- `evaluation-and-reproducibility` (Spec 6) — which validates reproducibility, accessibility checks, and UI-behavior conformance against the golden set and acceptance tests. This spec defines the **behaviors and acceptance tests to be exercised**; it runs no benchmark and asserts no executed test result.

> **Important status note:** Nothing in this document asserts that any emulator has been started, any build has been produced, any Compose or instrumentation test has been executed, any device has been exercised, or any accessibility audit has been completed. Every acceptance criterion below is a **contract to be verified** by later implementation and by `evaluation-and-reproducibility` (Spec 6) and F5, never a claim that verification has already happened.

### Legend of Requirement Classes

Each requirement is tagged with one or more classes, following the F0–F6 handoff distinction:

- **[ASSESS]** — Mandatory requirement from the Konecto assessment (`assessment-en.pdf`): the three evaluable screens (Conversations, Chat, Developer Debug), rendering technical figures without parsing prose, bilingual ES/EN, loading/error states on every screen, and reproducibility.
- **[APPROVED]** — Approved addition or decision beyond the raw assessment, ratified in the F0–F6 handoff (login/register/logout, the F4-D01/D02/D03 UX decisions, the F4 v1.1 offline addendum, the MVVM+UDF/Room/Retrofit technical defaults).
- **[DELEGATED]** — Delegated technical detail that Kiro may concretize (exact composable structure, navigation route types, Room schema, DI wiring, polling constants, DTO field names) while preserving the approved invariants.
- **[EXPERIMENT]** — Requires real execution, benchmark, or measurement to satisfy; cannot be satisfied by design alone and is resolved by Spec 6.

### Source-of-Truth Precedence

When sources conflict, the following precedence governs this spec:

1. **`assessment-en.pdf`** — authoritative for external obligations: a native Android app with Conversations, Chat, and Developer Debug screens; the app rendering the `answer` and comparable technical data without parsing prose; bilingual ES/EN; loading and error states on every screen; and reproducibility from a clean checkout.
2. **Backend contracts (Spec 3)** — the endpoints, DTOs, `Response_Envelope`, `Content_Block` structure, `Job_State`, auth/refresh flow, idempotency, plan-confirmation semantics, and error envelope this client consumes. The client conforms to these contracts; it never redefines or bypasses them.
3. **Composed output (Spec 4)** — the typed `content_blocks` and `interpretation_summary` the client renders. Every technical figure the client displays originates from a Spec 2/4 verified figure already present in a typed block; the client never composes one.
4. **Approved F4 decisions** — the F4 Android UX handoff (§1 inherited bindings, §2 type-rendering contract, §3 five-destination navigation, §4 Conversations, §5 Chat, §6 Developer Debug, §7 architecture selection, §8 cache/session policy, §9 accessibility/i18n, §11 F4-D01/D02/D03), and the binding **F4 v1.1 offline addendum** (§1–§8) which prevails over any more generic offline wording.
5. **`series_76_summary.pdf`** — business/narrative **context only**; never a source of technical values.

**Source-of-truth reminder:** the Android client **renders typed blocks and NEVER parses, derives, re-ranks, or computes a technical number from prose.** Every technical figure shown in any card, table, bar, or highlight is read from a typed field of a `Content_Block` that the backend supplied, carrying its unit, service, frequency, availability, and provenance. The `answer` string is displayed as user-safe prose; the client never extracts a figure from it. The backend is the single source of truth for users, permissions, conversations, messages, plans, rankings, job states, and all technical values.

### Non-Goals (Out of Scope for This Spec)

- **No backend, HTTP server, authentication server, job queue, or cryptography internals.** FastAPI endpoints, Argon2id hashing, opaque-token verifiers, the durable PostgreSQL queue with leases/fencing/idempotency, AES-256-GCM server-side encryption, the KEK/DEK lifecycle, and server-side deletion belong to `backend-api-auth-jobs-crypto` (Spec 3). This client **consumes** those contracts; it does not implement them. (Client-side Keystore-backed storage of the app's own tokens and cache is in scope.)
- **No agent reasoning, intent interpretation, plan authoring, response-text composition, or verified-figure production.** Interpretation, filter-AST authoring, ranking orchestration, claim verification, and the population of `content_blocks` with verified figures belong to `agent-orchestration-response` (Spec 4). This client **renders** the typed blocks; it never derives a number or re-orders a ranking.
- **No domain SQL, typed repositories over the catalog, ranking/comparison/conversion math, or custom tool logic.** These belong to `domain-and-tools` (Spec 2).
- **No ingestion, extraction, audit, or edition publication.** These belong to `data-and-ingestion` (Spec 1).
- **No eval harness, A/B tool comparison, model selection, accuracy thresholds, or cost-gate conclusions.** These belong to `evaluation-and-reproducibility` (Spec 6).

### Traceability Summary

| This spec traces to | Items |
|---|---|
| User stories | US-001, US-003, US-004, US-005, US-006, US-007, US-008, US-009, US-012, US-018, US-019, US-020, US-021, US-025, US-026, US-027, US-028, US-029, US-030, US-032, US-033, US-034, US-036 |
| QA scenarios | QA-05 (performance/responsiveness), QA-09 (accessibility), QA-10 (robustness), QA-11 (traceability) |
| F0 acceptance tests | AT-06 (heterogeneous FLA comparison), AT-07 (N/A not zero), AT-10 (IDOR), AT-11 (cache after logout/switch), AT-16 (local storage no plaintext) |
| F4 decisions | F4-D01 (compact-but-always-visible interpretation), F4-D02 (optional comparable bars), F4-D03 (Room read cache, no background sync) |
| F4 acceptance tests | F4-AT01..F4-AT19 |
| F4 v1.1 addendum | Offline addendum §1–§8 |
| F5 offline tests | F5-OFF-01..F5-OFF-07 |
| Enablers | EN-07 (response/error contract), EN-08 (Android storage/navigation) |

## Glossary

- **Android_Client**: The native Kotlin + Jetpack Compose application defined by this spec, the sole subject of its requirements.
- **Response_Envelope**: The typed backend response (defined by Spec 3) that always carries `session_id` and `answer`, plus optional `content_blocks`, `status`, `interpretation_summary`, `plan`, `warnings`, `request_id`, and `catalog_edition_id`.
- **Content_Block**: A typed, discriminated element of the Response_Envelope (structure defined by Spec 3, populated by Spec 2/4) of kind `text`, `product_card`, `comparison_table`, `matching_part_numbers`, `bar_chart`, `clarification`, or `plan_review`.
- **Answer_Text**: The full user-safe prose string in the Response_Envelope, displayed verbatim and never parsed for technical figures.
- **Interpretation_Summary**: The backend-provided summary of the turn's intent and applied/proposed/delegated/ignored criteria, rendered compact and expandable, containing no tool names, prompts, or internal parameters.
- **Turn_State**: The client-side UI state of a chat turn, one of `draft`, `submitting`, `queued`, `running`, `needs_clarification`, `awaiting_confirmation`, `completed`, `failed`, `cancelled`, or `disconnected_reconciling`.
- **Job_State**: The server-authoritative job state (defined by Spec 3) the client observes by polling, one of `QUEUED`, `RUNNING`, `NEEDS_CLARIFICATION`, `AWAITING_CONFIRMATION`, `COMPLETED`, `FAILED`, `CANCELLED`, `STALE_PLAN`, or `CATALOG_WITHDRAWN`.
- **Client_Request_Id**: The caller-supplied idempotency key the client generates once per logical turn intent and reuses across retries until acceptance is known.
- **Plan_Revision**: The monotonic plan revision number (defined by Spec 3) the client echoes on confirmation; a `409`/stale response triggers reload and re-confirmation.
- **Offline_Banner**: The persistent, visible notice shown in Conversations and Chat when the device has no usable connectivity, stating that saved conversations are viewable but messages cannot be sent.
- **Draft**: Locally preserved, unsent composer text that is never auto-sent; it remains after connectivity returns until the user presses Send again.
- **Account_Epoch**: A per-login generation/epoch guard that invalidates a prior account's in-flight responses and cache so a late response cannot write the wrong user's cache.
- **Read_Cache**: The Room-backed local store of the authenticated owner's own conversation list and message history, used for read-only display and never treated as the source of truth.
- **Keystore_Storage**: Client storage of the app's own tokens and cached payloads under keys backed by the Android Keystore, never in plaintext.
- **Developer**: An account with role `developer` (defined by Spec 3) that the client reveals the Debug destination to as a UI convenience, with the backend re-checking role and ownership on every call.
- **Last_Sync_Label**: The user-visible marker on cached content indicating the time of its last synchronization and that it may be stale.

## Requirements

### Requirement 1: Platform and Client Architecture

**User Story:** As an app maintainer, I want a native Kotlin + Jetpack Compose client built Feature-First with MVVM and unidirectional data flow, type-safe navigation, a read-only Room cache, and a Retrofit stack, so that the UI stays testable and responsive while the server remains the single source of truth. *(Traces: US-027, F4 §1, F4 §7, F4-D03, EN-08. Classes: [APPROVED], [DELEGATED])*

#### Acceptance Criteria

1. THE Android_Client SHALL be implemented as a native Kotlin application using Jetpack Compose for its user interface, organized Feature-First, AND SHALL be built as a single Gradle module.
2. THE Android_Client SHALL structure its presentation with MVVM and unidirectional data flow such that each screen observes immutable state exposed by a ViewModel through StateFlow and dispatches user intent as unidirectional events, AND SHALL NOT mutate rendered state directly from a composable; IF a ViewModel fails to load its state, THEN THE Android_Client SHALL render an error state rather than crash.
3. THE Android_Client SHALL navigate between destinations using type-safe Navigation Compose passing only lightweight identifiers and parameters, AND SHALL NOT serialize full messages or full conversation payloads through a navigation route.
4. THE Android_Client SHALL perform all network access through Retrofit over OkHttp with an authentication interceptor that attaches the current access token, AND SHALL route all catalog and conversation data exclusively through the Spec 3 HTTP contracts.
5. THE Android_Client SHALL use Room as a read cache for the authenticated owner's own conversation list and message history, AND SHALL use DataStore only for non-sensitive settings, AND SHALL NOT store tokens or sensitive payloads in DataStore in plaintext.
6. THE Android_Client SHALL compose its dependencies through a manual or light dependency-injection mechanism, AND SHALL NOT introduce a heavyweight DI container framework.
7. THE Android_Client SHALL obtain job progress by polling the Spec 3 job endpoints with exponential backoff starting at 1 second, doubling to a maximum interval of 30 seconds, honoring any `Retry-After` the backend provides, AND SHALL NOT depend on server push or a WebSocket channel for job updates.
8. WHEN the authentication interceptor receives a `401`, THE Android_Client SHALL attempt the Spec 3 refresh-rotation flow once and, if refresh fails, SHALL close the session, AND SHALL NOT retry the original request with an invalid token indefinitely.
9. THE Android_Client SHALL treat the backend as the single source of truth for users, permissions, conversations, messages, plans, rankings, job states, and technical values, AND SHALL NOT locally infer, derive, re-rank, or recompute any of these.
10. THE Android_Client SHALL NOT parse, extract, derive, or compute a technical number from Answer_Text or any prose string, AND SHALL render every technical figure only from a typed field of a Content_Block supplied by the backend.
11. IF a typed Content_Block field required to render a figure is absent or malformed, THEN THE Android_Client SHALL render a safe fallback (an explicit unavailable indicator) for that element AND SHALL NOT fabricate or infer a value.

### Requirement 2: Five Navigable Destinations

**User Story:** As a user, I want Login, Register, Conversations, Chat, and Developer Debug as distinct navigable destinations with a clear auth graph and main graph, so that the three evaluated screens and the two approved auth screens are reachable and the Debug screen is exposed only to developers. *(Traces: US-003, US-027, F4 §3, F4-AT12. Classes: [ASSESS], [APPROVED])*

#### Acceptance Criteria

1. THE Android_Client SHALL provide Login, Register, Conversations, Chat, and Developer Debug as five distinct navigable destinations, AND SHALL present Conversations, Chat, and Developer Debug as the three evaluated screens and Login and Register as the two approved authentication screens.
2. THE Android_Client SHALL organize an authentication graph in which Login and Register navigate to each other, and a main graph in which Conversations navigates to Chat and Chat (for a developer) navigates to the Debug trace detail, AND SHALL NOT present Conversations, Chat, or Developer Debug as a modal substitute for a navigable destination.
3. WHEN the application launches and a stored access or refresh token exists whose expiry has not passed and which the backend accepts, THE Android_Client SHALL route to Conversations, AND WHEN no such session exists THE Android_Client SHALL route to Login.
4. THE Android_Client SHALL include the Developer Debug destination in the release build, AND SHALL reveal navigation to it only when `GET /api/auth/me` reports the caller's role as `developer`, treating that reveal as a UI convenience while the backend re-verifies role and ownership on every trace request.
5. IF the `GET /api/auth/me` role lookup fails or is unavailable, THEN THE Android_Client SHALL NOT reveal the Developer Debug navigation entry, failing closed.
6. IF a non-developer attempts to reach a Developer Debug route indirectly, THEN THE Android_Client SHALL NOT expose the navigation entry AND the backend SHALL deny the underlying request, such that no trace content is displayed.

### Requirement 3: Authentication Screens, Logout, and Account Switch

**User Story:** As a user, I want to register a user-only account, log in, log out, and switch accounts with my tokens stored securely and prior-account data never leaking, so that my session is safe and isolated. *(Traces: US-001, US-033, US-036, F4-AT01, F4-AT02, F4-AT03, F4-AT04. Classes: [APPROVED])*

#### Acceptance Criteria

1. WHEN a visitor registers from the Register screen, THE Android_Client SHALL submit only the registration credentials (email and password) and SHALL NOT present a role selector or send any role or privilege field, such that the backend assigns role `user` and a `developer` account can never be created through the app.
2. IF the backend rejects a registration as invalid or a duplicate, THEN THE Android_Client SHALL remain on the Register screen, present an error indication, and create no local authenticated session.
3. WHEN login credentials do not match an account, THE Android_Client SHALL present a generic authentication-failed message that does not distinguish an unknown email from a wrong password, AND SHALL NOT retain the entered password in memory or storage beyond the submission attempt.
4. WHEN an outgoing authenticated request indicates an expired access token, THE Android_Client SHALL refresh it automatically using the Spec 3 refresh-rotation flow, synchronizing concurrent requests so that exactly one refresh executes per rotation and no previously rotated token is replayed on a subsequent request.
5. IF a token refresh fails, THEN THE Android_Client SHALL close the authenticated session, route to Login, AND hide all cached content such that no cached conversation or message is displayed without a fresh authenticated session.
6. WHEN the user logs out, THE Android_Client SHALL clear the stored tokens, invalidate the session on the backend via `POST /api/auth/logout`, AND make the cache inaccessible such that logged-out state displays no prior cached content.
7. IF the backend logout call fails or times out, THEN THE Android_Client SHALL still clear the local tokens and make the cache inaccessible, failing closed locally.
8. WHEN the user switches to a different account, THE Android_Client SHALL purge the previous account's cache and any wrapped residual key before rendering any content of the new account, using an Account_Epoch guard such that not even a single frame of the previous account's content is displayed.
9. THE Android_Client SHALL store its access and refresh tokens using Keystore-backed storage, AND SHALL NOT persist a token, password, or wrapped key in plaintext.

### Requirement 4: Conversations Screen

**User Story:** As a user, I want a Conversations screen that lists only my conversations with titles, last activity, and pending-job indicators, lets me search by title, create, open, rename, and delete with confirmation, and handles every load and error state, so that I manage my dialogues safely. *(Traces: US-004, US-005, US-006, US-007, US-008, US-009, US-027, US-028, AT-10, AT-11. Classes: [ASSESS], [APPROVED])*

#### Acceptance Criteria

1. WHEN the Conversations screen loads, THE Android_Client SHALL display only the authenticated token owner's conversations, each with its title, a last-activity timestamp, and a pending-job indicator shown when and only when at least one job for that conversation is outstanding, AND SHALL NOT display any conversation belonging to another owner.
2. WHEN the user enters one or more characters (up to a maximum of 200 characters) in the search field, THE Android_Client SHALL execute a case-insensitive title-only search against the Spec 3 session-listing endpoint matching conversations whose title contains the entered text, AND SHALL NOT search message bodies, AND WHERE no connectivity is available THE Android_Client SHALL apply the same filter to the local cache and label the result as a partial offline result rather than an exhaustive backend result.
3. THE Android_Client SHALL support creating a new conversation, opening an existing conversation, and renaming a conversation to a non-empty title of 1 to 200 characters, AND WHEN the user initiates a delete THE Android_Client SHALL present a confirmation prompt with explicit confirm and cancel choices, deleting only upon confirm and leaving the conversation unchanged upon cancel, AND SHALL provide logout and a visible account identity of the authenticated token owner on the screen.
4. THE Android_Client SHALL represent the Conversations screen with explicit states for first-load, refreshing, empty, loaded, offline-cache, recoverable-error, deleting, deleted, and session-expired, AND WHILE in the recoverable-error state THE Android_Client SHALL present a retry affordance that, when activated, re-attempts the failed operation and transitions to the resulting state.
5. WHEN the user scrolls to within the last visible page of the loaded list, THE Android_Client SHALL request the next page using the cursor and stable ordering supplied by the backend with a page size defined by the backend, AND SHALL NOT assume a locally derived ordering overrides the backend ordering.
6. WHEN the user confirms deletion of a conversation, THE Android_Client SHALL treat the deletion as final only after the backend confirms it, SHALL invalidate the local cache for that conversation upon confirmation, AND IF the backend does not confirm the deletion within 30 seconds THEN THE Android_Client SHALL treat the deletion as unconfirmed and retain the conversation in its pre-delete state.
7. IF connectivity fails before a delete is confirmed, THEN THE Android_Client SHALL hold the deletion in an indeterminate state, AND WHEN connectivity is restored THE Android_Client SHALL re-query the backend as the authoritative source and reconcile the conversation's presence to match the backend result, AND SHALL NOT rebuild the server's state from local cache and SHALL NOT resurrect a conversation the backend reports as deleted.
8. IF the backend reports a conversation as no longer existing, THEN THE Android_Client SHALL purge it from the local cache AND SHALL NOT re-upload cached data to recreate it.

### Requirement 5: Chat Screen Typed-Block Rendering

**User Story:** As a user, I want the Chat screen to render typed content blocks faithfully, show the interpretation and plan confirmation, and compare products without ever deriving a number from prose, so that every figure I see is exactly what the backend verified. *(Traces: US-012, US-018, US-019, US-020, US-021, US-034, AT-06, AT-07, F4-D01, F4-D02. Classes: [ASSESS])*

#### Acceptance Criteria

1. WHEN a Response_Envelope is received, THE Android_Client SHALL render each Content_Block according to its kind — `text`, `product_card`, `comparison_table`, `matching_part_numbers`, `bar_chart`, `clarification`, and `plan_review` — reading every technical figure from the block's typed fields, AND IF a block has an unknown kind THEN THE Android_Client SHALL render it as a safe text fallback, AND SHALL NOT parse, extract, or compute any technical figure from Answer_Text or any prose.
2. THE Android_Client SHALL display Answer_Text as full user-safe prose, AND SHALL NOT present any tool name, token, prompt, SQL, or internal parameter in the Chat screen.
3. THE Android_Client SHALL display the Interpretation_Summary in a compact form that is always visible and expandable to detail, consistent with F4-D01, AND SHALL label each listed criterion with its backend-provided category without inventing a category.
4. WHEN the envelope carries a plan awaiting confirmation, THE Android_Client SHALL present a plan confirmation panel showing the proposed criteria and ranking with Confirm and Edit affordances, AND SHALL send the `Plan_Revision` with the confirmation.
5. IF a plan confirmation returns a `409` stale-plan response, THEN THE Android_Client SHALL reload the current plan, present the refreshed plan for a new confirmation, AND SHALL NOT automatically re-execute the superseded plan.
6. THE Android_Client SHALL render at most three full product cards, AND WHEN at least two cards are displayed THE Android_Client SHALL provide a dual-of-two comparison selector among the displayed cards, AND SHALL render `bar_chart` only for metrics the backend marks comparable, each bar accompanied by a textual alternative value.
7. WHERE a field carries an N/A or absent state, THE Android_Client SHALL present that field with its explicit state AND SHALL NOT render it as zero, as a zero-height bar, or as a comparison winner.
8. WHEN technical values are displayed, THE Android_Client SHALL show each value's unit and its service and 50/60 Hz frequency context where the backend provides them, AND SHALL present FLA values from heterogeneous supply configurations with their supply condition without rendering a lower-energy-consumption claim.
9. WHEN a result set has matches, THE Android_Client SHALL display the match count and the full list of matching part-number names while rendering at most three full product cards.
10. WHEN the turn is a single-recommendation (top-1) result, THE Android_Client SHALL present the winning candidate together with the integer count of eligible candidates only, AND SHALL NOT enumerate the other eligible part numbers in that mode.

### Requirement 6: Chat Turn Lifecycle and Asynchronous Jobs

**User Story:** As a mobile user, I want a new conversation to start without a session id, turns to move through explicit states, and job polling to run off the main thread with safe idempotent retries, so that long agent work never blocks me or duplicates my turn. *(Traces: US-029, US-034, F4-AT06, F4-AT07, F4-AT08. Classes: [APPROVED])*

#### Acceptance Criteria

1. WHEN the user starts a new conversation, THE Android_Client SHALL send the first query with no `session_id` field present, AND WHEN the backend returns a `session_id` for that turn even while the turn runs as an asynchronous job, THE Android_Client SHALL persist the returned `session_id`, associate the ongoing `job_id` with it, and remove any provisional local draft placeholder for that turn so that exactly one turn record remains.
2. THE Android_Client SHALL represent each chat turn with exactly one Turn_State drawn from `draft`, `submitting`, `queued`, `running`, `needs_clarification`, `awaiting_confirmation`, `completed`, `failed`, `cancelled`, or `disconnected_reconciling`, and SHALL never hold a turn in two Turn_States simultaneously.
3. THE Android_Client SHALL determine job state only from responses to the Spec 3 job endpoint and never from elapsed time alone, AND SHALL retain the `Client_Request_Id` for a submitted turn until the turn's acceptance outcome is resolved to one of accepted, rejected, or still-unknown, discarding it only after the outcome is accepted or rejected.
4. WHEN a job submission is accepted with `202`, THE Android_Client SHALL poll the job result off the main thread with exponential backoff starting at 1 second, doubling each attempt up to a maximum interval of 30 seconds, AND WHERE the backend supplies a `Retry-After` value, THE Android_Client SHALL wait at least that value clamped to the range 1 to 300 seconds before the next poll, AND SHALL NOT block the main thread while any poll is in progress.
5. IF the acceptance response to a job submission is lost or its outcome is unknown, THEN THE Android_Client SHALL retry the submission using the same `Client_Request_Id` so the backend treats it idempotently and no duplicate turn is created, AND SHALL generate a new idempotency key only when the user initiates a genuinely new intent and never for a transport-level retry.
6. WHEN a job reaches a terminal Job_State, THE Android_Client SHALL stop all polling for that job and set the turn's Turn_State to `completed` for `COMPLETED`, `failed` for `FAILED`, or `cancelled` for `CANCELLED`, reflecting that terminal Turn_State in the UI.

### Requirement 7: Offline Experience

**User Story:** As a user with no connectivity, I want a clear offline banner, a disabled Send that preserves my draft, no silent queueing or auto-send, and safe reconciliation when I reconnect, so that I never get a false confirmation or an unexpected message sent on my behalf. *(Traces: US-028, F4 v1.1 addendum §1–§8, F5-OFF-01..07. Classes: [APPROVED])*

#### Acceptance Criteria

1. WHILE the device has no usable connectivity, defined as the inability to establish a successful request to the backend because no network transport is available or no backend response is received within the connect timeout, THE Android_Client SHALL display a non-dismissible Offline_Banner on both the Conversations screen and the Chat screen for the entire duration of the no-connectivity condition, with localized ES and EN copy stating that saved conversations are viewable but messages cannot be sent until connectivity returns.
2. WHILE the device has no usable connectivity, THE Android_Client SHALL disable the Send action with a visibly disabled state and an accessible state description announced by TalkBack, AND SHALL keep the composer present so the user can write or edit a Draft that is preserved locally in encrypted form and remains retrievable after the app is backgrounded, terminated, or restarted.
3. WHILE the device has no usable connectivity, THE Android_Client SHALL NOT issue any `POST`, SHALL NOT enqueue the message locally for later automatic sending, AND SHALL NOT mark the message as sent, queued, or completed or display any server confirmation.
4. WHEN connectivity returns, THE Android_Client SHALL NOT automatically send the preserved Draft, SHALL keep the Draft content unchanged, AND SHALL require the user to explicitly press Send again before the Draft is transmitted.
5. WHILE displaying cached history offline, THE Android_Client SHALL show only the authenticated owner's previously authorized content accompanied by a Last_Sync_Label stating the timestamp of the most recent successful synchronization, AND SHALL NOT present the cached content as an exhaustive or current backend result.
6. IF the device has no usable connectivity, THEN THE Android_Client SHALL present the offline condition as an Offline_Banner, AND IF the device has usable network transport but the backend returns a `503` response, the authentication token is rejected as invalid, or an upstream dependency reports as unavailable, THEN THE Android_Client SHALL present a server or authentication error that is visually and textually distinct from the Offline_Banner and SHALL NOT attribute the condition to a lack of internet.
7. IF connectivity is lost while a request is in flight, THEN THE Android_Client SHALL treat the remote result as indeterminate and, upon reconnection, SHALL reconcile it to a single deterministic outcome of sent or not-sent using the `Client_Request_Id` or `job_id`, AND any retry SHALL reuse the same idempotency key so that no duplicate message is created.
8. WHEN connectivity is recovered, THE Android_Client SHALL revalidate the session and reconcile the state of all pending jobs before re-enabling the Send action, AND SHALL NOT transmit any pending Draft unless the user performs an explicit Send action.

### Requirement 8: Developer Debug Screen

**User Story:** As a developer, I want a Debug screen that shows the sanitized tool activity of my own turns and nothing secret or belonging to another user, so that I can inspect behavior without compromising privacy. *(Traces: US-003, US-030, AT-10, F4-AT12, F4-AT13. Classes: [ASSESS], [APPROVED])*

#### Acceptance Criteria

1. WHILE `GET /api/auth/me` reports the caller's role as `developer`, THE Android_Client SHALL make the Developer Debug destination navigable, treating that as a UI convenience while every trace request is re-verified server-side for role and ownership.
2. WHEN a trace is displayed, THE Android_Client SHALL present, per turn and per tool call, the tool name, the sanitized arguments, the sanitized results, any error, the duration, the `trace_id`, and the timestamp, AND WHERE the backend provides cost or token counts THE Android_Client SHALL present them.
3. THE Android_Client SHALL distinguish a tool-attempt entry from the turn's overall execution.
4. THE Android_Client SHALL identify turns that invoked no tool, AND SHALL present durations as non-negative values.
5. THE Android_Client SHALL NOT display any token, password, secret request header, KEK, DEK, or internal prompt in any trace view.
6. WHEN a trace request is denied, THE Android_Client SHALL surface a `401`, `403`, or `404` outcome without disclosing whether the targeted resource exists or who owns it.
7. WHEN a conversation is deleted, THE Android_Client SHALL reflect that its traces are no longer available.
8. THE Android_Client SHALL NOT display to a developer any trace belonging to a different developer.

### Requirement 9: Local Cache and Session Security

**User Story:** As a user, I want my cached data isolated per account, encrypted locally, hidden after logout, and purged on account switch, so that a stolen device dump or a late response never leaks my conversations to another account. *(Traces: US-028, US-033, AT-11, AT-16, F4-AT04, F4-AT16. Classes: [APPROVED])*

#### Acceptance Criteria

1. IF cached content is requested without a current local authenticated session, THEN THE Android_Client SHALL NOT display it, AND THE Android_Client SHALL maintain a Read_Cache isolated per user such that no account can read another account's cache entries.
2. WHEN the user logs out, THE Android_Client SHALL remove cached content from the UI and from in-memory decrypted state within 1 second such that no cached content is displayed in logged-out state.
3. WHEN the user switches accounts, THE Android_Client SHALL purge the previous account's cache and any wrapped residual key to completion before rendering the new account, such that zero residual entries or wrapped keys of the previous account remain readable.
4. THE Android_Client SHALL encrypt cached titles and messages locally, using either payload-level encryption or an audited full-database encryption, under keys backed by the Android Keystore, AND SHALL NOT persist a plaintext index of titles or messages.
5. THE Android_Client SHALL exclude the cache and tokens from Android backup, AND SHALL NOT write a token, password, or key material to any log or trace in plaintext.
6. WHEN two or more concurrent requests trigger a refresh-token rotation, THE Android_Client SHALL synchronize them so that exactly one rotation is consumed and no refresh replay occurs.
7. WHEN a response arrives after a logout or account switch, THE Android_Client SHALL compare its Account_Epoch against the current epoch and discard it on mismatch such that a late response cannot write the cache of the wrong user.
8. THE Android_Client SHALL NOT upload cached data to recreate a conversation the backend reports as deleted.
9. IF a Keystore-backed key required to decrypt the cache is unavailable, THEN THE Android_Client SHALL treat the cache as empty AND SHALL NOT expose ciphertext or partial plaintext.

### Requirement 10: Accessibility, Internationalization, and UI States

**User Story:** As a user relying on assistive technology or a different language, I want localized ES/EN strings, accessible labels and tables, chart text alternatives, and loading/empty/error states on every screen without the UI freezing, so that the app is usable for everyone. *(Traces: US-025, US-026, US-027, QA-09, F4-AT17, F4-AT18, F4-AT19. Classes: [APPROVED], [DELEGATED])*

#### Acceptance Criteria

1. THE Android_Client SHALL provide localized strings and number and date formats for Spanish and English, SHALL fall back to a default language for any missing string, AND SHALL NOT translate part numbers, units, or technical identifiers.
2. WHEN the user switches the interface language, THE Android_Client SHALL change only the user-interface language and SHALL NOT change any part number, unit, numeric value, or source of a displayed technical figure.
3. THE Android_Client SHALL provide TalkBack content descriptions for interactive and informational elements, support large-text scaling up to 2.0x per the OS font-size setting without loss of content, and support dark and light themes.
4. THE Android_Client SHALL render comparison tables with accessible headers and horizontal scrolling, AND SHALL provide a textual alternative value for every chart so that no information is conveyed by the chart alone.
5. WHEN a screen operation is loading, empty, or fails, THE Android_Client SHALL represent the corresponding loading, empty, or error state on that screen, AND WHILE in an error state SHALL present an actionable retry affordance and a failure message without exposing a stack trace or internal detail.
6. THE Android_Client SHALL perform network, database, and cryptography work off the main thread and SHALL cancel polling and in-flight work per the lifecycle, such that the main thread is not blocked beyond 5 seconds and no application-not-responding condition arises from these operations.

### Requirement 11: Reproducibility of the App

**User Story:** As an evaluator, I want to build and run the app from a clean checkout in Android Studio against the emulator with documented networking and no committed secrets, so that I can exercise all screens without implicit steps. *(Traces: US-032, F4-AT19, QA reproducibility. Classes: [ASSESS])*

#### Acceptance Criteria

1. WHEN built from a clean checkout in Android Studio following only the documented steps, THE Android_Client SHALL compile with zero errors and deploy to the Android emulator.
2. IF a build or run step is required that is not covered by the documentation, THEN that step SHALL be considered a defect against this requirement.
3. THE Android_Client SHALL document the host-to-emulator networking configuration, including the `10.0.2.2` loopback mapping, such that an evaluator can reach a host-run backend following only the documented configuration.
4. THE Android_Client release configuration SHALL disallow global cleartext traffic AND SHALL permit cleartext only for the single documented local emulator loopback host, rejecting cleartext for all other hosts.
5. THE Android_Client SHALL NOT embed any real secret, token, password, or key in the application source, resources, or build output, AND SHALL use non-functional placeholder or configuration values for any endpoint or credential input.
6. THE Android_Client SHALL provide documentation covering emulator setup, the navigation path to reach the Developer Debug screen, and the demo `user` and `developer` accounts, without placing real credentials in the repository.
