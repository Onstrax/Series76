# Series 76 Technical Assistant

A conversational technical assistant for the Series 76 electric actuator catalog.
It answers part-number lookups, filtered searches, comparisons and recommendations
from a **published, audited catalog edition**. Every technical figure it shows traces
to a cell of `series_76_electric_data.pdf`; the language model never supplies a
number, SQL, catalog edition or permission.

| Component | Path | Spec (`.kiro/specs/…`) |
|---|---|---|
| Ingestion pipeline + catalog schema | `backend/src/series76_data`, `backend/migrations` | `data-and-ingestion` |
| Deterministic domain + typed tools | `backend/src/series76_domain` | `domain-and-tools` |
| HTTP API, auth, jobs, worker, crypto | `backend/src/series76_api` | `backend-api-auth-jobs-crypto` |
| Agent orchestration + typed responses | `backend/src/series76_agent` | `agent-orchestration-response` |
| Android client (Kotlin + Compose) | `android/` | `android-app` |
| Evaluation harness, evidence, traceability | `backend/src/series76_eval`, `docs/` | `evaluation-and-reproducibility` |

Architecture decisions are recorded as ADRs in `backend/docs/adr/`. The API contract
snapshot is `docs/contract/openapi.json`, and the cross-spec traceability matrix is
`docs/traceability/TRACEABILITY.md`.

## Status: what is verified and what is not

This section lists only what has been executed. Everything else is marked
**[EXPERIMENT]**: written, but not run in the authoring environment.

- **Executed:** the backend unit and property suites (Hypothesis, at least 100 examples per
  property), the integration suites against a real PostgreSQL 15 container (Testcontainers),
  `ruff` and `mypy --strict`. Each executed level has an `Evidence_Record` in
  `docs/evidence/evidence.jsonl`. Run `python -m series76_eval status` in `backend/` to see them.
- **[EXPERIMENT] — catalog data.** The audited golden dataset and the `verified_replay`
  manifests do not exist yet. They come from a **manual audit** of
  `series_76_electric_data.pdf`, and no language model may transcribe it. Until that audit
  exists, the published catalog is empty, so the assistant finds no part numbers. It never
  makes any up.
- **[EXPERIMENT] — Android.** No Gradle build, JVM test run or emulator run has been
  executed (no Android SDK in the authoring environment). See `android/README.md`.
- **[EXPERIMENT] — live model evaluation.** It needs an `OPENROUTER_API_KEY`. No model or
  tool-set winner has been declared, because no paired A/B evidence exists.
- **[EXPERIMENT] — Docker Compose cold start.** `docker-compose.yml` is written and its
  provisioning step is integration-tested, but a full `docker compose up` from a clean clone
  has not been recorded as evidence.

## Setup

Prerequisites: Docker with Compose v2. For local development: Python 3.12 and
[`uv`](https://docs.astral.sh/uv/). For the app: Android Studio with JDK 17.

### Quick start (Docker Compose)

```bash
cd backend
cp .env.example .env
# Edit .env and replace every CHANGE_ME:
#   POSTGRES_PASSWORD  - local database owner password
#   DATABASE_URL       - set the series76_app password (any strong local value)
#   ENCRYPTION_KEK     - python3 -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
docker compose up --build
```

Compose runs three services: `db` (PostgreSQL 15), `api` (FastAPI on
`http://localhost:8000`) and `worker` (the asynchronous job worker). `api` and `worker` are
built from one image. Before either starts, the one-shot `migrate` job does two things and
then exits:

1. It runs `alembic upgrade head`.
2. It provisions the least-privilege login role named in `DATABASE_URL`, granted
   `app_writer` and `runtime_reader_role` (`python -m series76_api.provision`).

If the migration fails, nothing is served. Only that job sees the privileged database URL.

Check the services: `curl http://localhost:8000/api/health` and `…/api/ready`.

The default `AGENT_RUNTIME=fake` is a deterministic, zero-spend agent, so the whole HTTP
surface works without any key. To use the real agent, see
[Configurable models](#configurable-models).

### Local development (no Compose)

```bash
cd backend
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/pytest                        # unit + property tests
.venv/bin/pytest -m integration         # needs Docker (Testcontainers PostgreSQL)
.venv/bin/ruff check src tests && .venv/bin/mypy src
```

### Android emulator to host networking

The emulator reaches the host at `10.0.2.2`. The app's default backend URL is
`http://10.0.2.2:8000/` (`android/gradle.properties`, `series76.apiBaseUrl`). Cleartext HTTP
is allowed **only** for that host. Build and run steps are in `android/README.md`.

## Registration and login

```bash
curl -X POST localhost:8000/api/auth/register -H 'content-type: application/json' \
     -d '{"email":"ana@example.com","password":"<12+ chars, 3 of: lower/upper/digit/symbol>"}'
curl -X POST localhost:8000/api/auth/login -H 'content-type: application/json' \
     -d '{"email":"ana@example.com","password":"…"}'
# -> {"access_token": "…", "refresh_token": "…", …}
```

- Send `Authorization: Bearer <access_token>` on every call.
- `POST /api/auth/refresh` rotates the pair. Reusing an already-rotated refresh token
  revokes the whole token family.
- `POST /api/auth/logout` revokes the current session.
- `GET /api/auth/me` returns your id, email and role.
- Tokens are opaque and stored only as SHA-256 verifiers. Passwords are hashed.

## Test `user` vs `developer`

- **Registration always creates a `user`.** Any client-supplied `role` or privilege field is
  ignored, and no HTTP endpoint can create or promote a `developer`.
- **A `developer` is created out-of-band, with the seed CLI.** The password comes from the
  environment, never from the repository:

```bash
cd backend
SEED_PASSWORD='<choose one>' docker compose run --rm -e SEED_PASSWORD api \
  python -m series76_api.seed --email dev@example.com --role developer
SEED_PASSWORD='<choose one>' docker compose run --rm -e SEED_PASSWORD api \
  python -m series76_api.seed --email user@example.com --role user
```

No demo credentials are committed. Pick them when you seed.

## Debug permissions

`GET /api/sessions/{session_id}/messages/{message_id}/trace` returns the sanitized trace of
one assistant turn. The trace contains turn states, tool calls with their typed arguments and
statuses, model-call counts and figure counts. It never contains prompts, keys, tokens or
model output.

Access is granted only when **both** of these hold:

- the caller has the `developer` role;
- the caller **owns** the conversation.

Every other caller, including a developer reading another developer's trace, gets the same
denial as for a resource that does not exist. Traces are stored encrypted. In the Android
app, the Debug screen is shown only to developers, and the backend re-checks the role on
every call.

## Synchronous endpoint — `POST /api/conversation`

```bash
curl -X POST localhost:8000/api/conversation -H "authorization: Bearer $TOKEN" \
     -H 'content-type: application/json' \
     -d '{"query":"What is the torque of 76-…?", "session_id": null, "client_request_id": "uuid"}'
```

The request needs `query`. `session_id` is optional: omit it to start a new conversation.
`client_request_id` is optional and makes retries idempotent.

The endpoint returns a **Response_Envelope**:

- `answer`, `status` (`COMPLETED` / `NEEDS_CLARIFICATION` / `AWAITING_CONFIRMATION`),
  `session_id`, `message_id`, `turn_id` and `catalog_edition_id`;
- `interpretation_summary`, `plan` and `warnings`;
- typed `content_blocks` of exactly these kinds: `text`, `product_card`, `comparison_table`,
  `matching_part_numbers`, `bar_chart`, `clarification`, `plan_review`.

Figures inside blocks are typed: value, unit, data status and cell-level evidence. When a
plan needs confirmation, send
`POST /api/sessions/{id}/plans/{revision}/confirm`.

## Asynchronous endpoint — `POST /api/conversation/jobs`

This endpoint takes the same body and returns `202 {"job_id", "session_id", "status": "QUEUED"}`:

- Poll `GET /api/jobs/{job_id}`, honoring `Retry-After`. When the job is `COMPLETED`, the
  poll returns the same Response_Envelope as the synchronous path.
- `POST /api/jobs/{job_id}/cancel` cancels a job and is idempotent.
- Each user can have only a bounded number of pending jobs (`PENDING_JOB_CAP`).

The worker leases jobs with fencing tokens:

- A retried or duplicated job produces exactly one persisted effect.
- Deleting a conversation while one of its jobs runs never brings it back.

## Conversations

- `GET /api/sessions` lists your conversations, with `pending_jobs` for each.
- `GET /api/sessions/{id}/messages` returns the history in order.
- `PATCH /api/sessions/{id}` renames a conversation.
- `DELETE /api/sessions/{id}` deletes it; its encryption key is destroyed.

Titles, messages, traces, plan state and checkpoints are encrypted with AES-256-GCM: each
conversation has its own data key, wrapped by `ENCRYPTION_KEK`, which lives outside the
database.

## Configurable models

No model id is hardcoded. To enable the real agent, set these in `.env`:

```dotenv
AGENT_RUNTIME=orchestrator
OPENROUTER_API_KEY=<your key>
AGENT_MODEL=<tool-calling model id>
AGENT_MODEL_CANDIDATES=<model a>,<model b>        # >= 2 per function for the A/B evaluation
INTERPRETER_MODEL=<model id>   INTERPRETER_MODEL_CANDIDATES=<a>,<b>
ANSWER_MODEL=<model id>        ANSWER_MODEL_CANDIDATES=<a>,<b>
FALLBACK_MODEL=<model id>      # used only if it preserves the required capabilities
MODEL_CAPABILITIES={"<model id>": ["tools", "json_schema"]}
OPENROUTER_DATA_COLLECTION=deny
AGENT_TOOL_SET=B               # A = coarse tools, B = fine-grained (see ADR 0002)
```

- **Models without verified capabilities are refused.** A model whose capabilities are not
  listed in `MODEL_CAPABILITIES` is rejected rather than guessed (fail closed).
- **No configuration means a clear error, not an answer.** Without a key or a model, the API
  starts and answers turns with a retryable `503`. It never invents an answer.
- **The agent is an explicit LangGraph `StateGraph` tool loop** (ADR 0004). A semantic
  interpreter produces a typed interpretation. All numbers come from deterministic tools over
  the published edition, and a claim verifier withholds any figure it cannot bind to evidence.

## Budget

There is one **cumulative** cost ledger across every model and function, with three limits:

- **USD 10.00** hard cap;
- **USD 6.00** for development and evaluation;
- **USD 4.00** reserved for the final demo.

These limits are fixed in code (`series76_agent/domain/ledger.py`). Configuration can only
lower spending, never raise the limits. Each call is authorized against a conservative
estimate before it is made, and its real cost is recorded afterwards. Each turn also has its
own model-call, tool-call, token, cost and wall-time rails (the `TURN_*` variables).

In Compose, `api` and `worker` share one ledger file on a named volume. Every authorization
re-reads that file under a file lock. As an outer backstop, set a **credit limit on the
OpenRouter key itself**.

Evaluation follows this order: offline → canary → paired A/B (`python -m series76_eval`).
No model or tool set is declared the winner without a persisted `Evidence_Record`.

## Ingestion modes: `verified_replay` vs `fresh_extraction`

- **`verified_replay` (the default)** rebuilds the catalog from approved, versioned
  manifests whose SHA-256 is checked before anything is ingested. It needs **no Gemini
  key**.
- **`fresh_extraction` (optional)** re-derives candidates from the PDF. It runs only with
  the evaluator's own `GEMINI_API_KEY`, and its output must pass the same manual audit
  before it is published.

Current state, honestly:

- The pipeline is implemented as a library: replay extractor, normalizer, reconciler,
  verifier, manifest builder and publisher. It is tested against a real PostgreSQL database.
- The `fresh_extraction` extractor is a stub.
- **There is no command-line ETL runner**, and **no audited manifests are committed**,
  because they depend on the manual PDF audit [EXPERIMENT].

`python -m series76_eval integrity` checks the source PDF against the trusted digest in
`Series76_Kiro_Handoff_v1.0/SHA256SUMS.txt`. A mismatch rejects the PDF before ingestion.

## Key decisions and tradeoffs

- **No invented numbers.** Figures come only from typed, parameterized tools over a
  published edition. The model gets typed placeholders and cannot write digits into the
  answer prose. Figures that cannot be verified are withheld, with their state shown
  (for example `N/A`, not documented, unavailable).
- **Two-layer data model.** An audited source edition is published by SHA-256 manifest.
  The runtime reads only the published edition, through `runtime_reader_role`.
- **Database roles and API split.** Three least-privilege database roles, plus
  `app_writer` for conversation data. The HTTP layer never runs SQL written by a model.
- **AES-256-GCM everywhere**, with per-conversation data keys, AAD bound to purpose, owner
  and record, and crypto-shredding on delete (ADR 0003 records the EAX fallback, which was
  not needed).
- **Sync and async turns share one durable job model**, with fencing tokens and a
  no-resurrection guard.
- **Explicit `StateGraph` instead of a prebuilt agent** (ADR 0004): every state of the
  12-state turn machine is visible and testable.
- **Android is a pure consumer.** It renders typed blocks, keeps a per-account encrypted
  cache backed by the Keystore, and never sends anything offline.
- **Messages carry an insertion sequence.** `conversation.messages.seq` (migration 0009)
  keeps a worker turn's question before its answer, because both are written in one
  transaction.

## Security limitations

- **Single-node assumptions.** The KEK comes from an environment variable. Production should
  use a KMS or secret manager, and key rotation is not automated.
- **No email verification and no password reset flow.** Rate limiting on login exists, but
  there is no global API rate limiting or WAF.
- **The local stack runs over HTTP.** Put TLS in front of `api` for any non-local
  deployment.
- **Each process enforces the cost ledger.** Two calls in flight in different processes can
  overshoot the cap by at most their pre-call estimates, which is why a provider-side key
  limit is recommended.
- **Traces are minimal by design, which limits debugging.** They hold no prompts or model
  text.
- **The Android Debug screen is reachable by navigation.** It shows no content without the
  backend's role check.

## Known failures and gaps

- **The catalog is empty until the manual audit is done**, so lookups return
  "no matching part numbers" ([EXPERIMENT], above).
- **The traceability matrix has two real documentation gaps:** `F3-AT10` (Android
  cross-token) and `F3-AT11` (catalog failure). They appear in the Spec 3 summary table but
  in no requirement `Traces:` line of any spec. Closing them needs a spec edit, which is the
  owner's decision. A strict `xfail` test records the gap.
- **Android code, build and tests are unexecuted** [EXPERIMENT].
- **Live model evaluation and cost measurements have not been run**, and no model has been
  selected [EXPERIMENT].
- **The twelve end-to-end demo flows and the cold-start reproduction are pending evidence.**
  `python -m series76_eval status` shows them.

## Evaluation harness

Run these from `backend/`:

| Command | What it does |
|---|---|
| `python -m series76_eval levels` | Lists the twelve test levels. |
| `python -m series76_eval run-level <level>` | Runs a level and persists its `Evidence_Record`. |
| `python -m series76_eval traceability` | Regenerates `docs/traceability/TRACEABILITY.md`. |
| `python -m series76_eval repro-check` | Checks the delivery structure statically. |
| `python -m series76_eval config-check` | Scans `.kiro/` for secrets. |
| `python -m series76_eval contract-snapshot` | Checks the API contract for drift. |
| `python -m series76_eval integrity` | Checks the source PDF's SHA-256. |
| `python -m series76_eval live-eval` | Refuses to run without a key and audited data. |

A result counts as "passed" only if it has a persisted `Evidence_Record`. Coverage is always
reported as a fraction with an explicit denominator.

## AI-assisted development and the `.kiro/` configuration

`.kiro/` is the **AI-assistant configuration artifact** used for this project's development
setup. `.kiro/specs/` holds the six Kiro specs: requirements, design and task list for each
component. They were the binding contract for the implementation.

The code was written with AI assistance (Kiro specs; Claude Code for Specs 4–6 and the final
integration). These working rules applied:

- Each slice was verified with ruff, mypy, unit tests and real-PostgreSQL integration
  tests before its commit.
- No invariant was weakened to make a test pass.
- Defects that property tests found were fixed in the code, not in the tests. Examples:
  withheld figures that still showed a status, history ordering, the debug trace shape, and
  cache purge on logout.
- Anything that could not be executed is labeled [EXPERIMENT] instead of being reported as
  done.

`.kiro/` contains no secrets. `python -m series76_eval config-check` verifies that, and every
credential in `.env.example` is a placeholder.
