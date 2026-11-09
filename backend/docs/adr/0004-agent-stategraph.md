# ADR 0004: Ship an explicit LangGraph `StateGraph` tool loop with external deterministic coordinators

- Status: Accepted
- Spec: `agent-orchestration-response` (Spec 4)
- Related: F2 §1, §2, §3, §8; Spec 4 Requirements 1, 4, 6, 11; design § "Orchestration composition (F2 §8)"

## Context

F2 §8 sets the default composition as LangChain `create_agent` + call/tool
middleware + structured output, with policy, confirmation, verification, and
composition as **external deterministic coordinators**. It pre-approves an
explicit `StateGraph` (keeping a LangChain node that selects and executes
tools) if resumption after interruption and clarification/confirmation handling
are not clean with `create_agent`. Which one ships is a **[DELEGATED]** detail to
be recorded in an ADR.

Facts found during implementation:

1. The repository pins `langchain==0.3.13`, `langchain-core==0.3.28`,
   `langgraph==0.2.60` (Spec 2 tools and the Spec 3 checkpointer are built and
   tested on this line). `create_agent` and its middleware API belong to the
   LangChain 1.x line; they do not exist in 0.3.x. Upgrading would move
   `langchain-core`/`langgraph` majors under already-verified Specs 2 and 3.
2. Clarification and confirmation are **not** graph interrupts in this design:
   they are deterministic decisions of the `Policy_Engine`, persisted in the
   encrypted domain state and the Spec 3 `Plan_Revision` surface, and resumed
   by a *new* turn (a user reply or an authenticated confirmation whose
   `(session_id, plan_id, plan_revision, user_id)` matches). The model never
   holds the pause state.
3. The provider endpoint may not support native tools and structured output in
   one call (Req 11.3). The interpretation phase (structured output) and the
   tool phase (native tools) are therefore separate model calls anyway.

## Decision

Ship the pre-approved **explicit `StateGraph`**:

- `series76_agent.agent_graph.ToolAgent` compiles a two-node graph per
  EXECUTING phase: `agent` (a LangChain chat model with `bind_tools` over the
  allow-listed Spec 2 `StructuredTool`s) and `tools` (the allow-list adapter that
  injects the server context, strips model-supplied server keys, enforces the
  per-turn bounds fail-closed, and returns inert sanitized data). It stops as
  soon as the plan's required reads are done, when the model stops calling
  tools, or when a budget limit is reached.
- Interpretation, policy, recommendation, claim verification, and composition
  run **outside** the graph as deterministic coordinators
  (`series76_agent.orchestrator.AgentOrchestrator`). The 12-value `Turn_State`
  machine lives there, with a committed state record before and after every
  model call.
- The model sees the **validated plan**, never the raw user message, so text in
  a message cannot steer tool selection beyond what the policy approved. Any
  plan-required read the model skips is completed by the coordinator through
  the **same** allow-listed adapter (never another path) and is visible in the
  developer trace (`origin = "coordinator"`), so Spec 6 can measure tool-selection
  quality honestly.

### Checkpointing

The tool loop is bounded (≤ `max_model_calls_per_turn`) and **read-only**: it
performs idempotent catalog reads only. Crash recovery is therefore
re-execution of the turn under the Spec 3 durable job / lease / fencing
protocol (a reclaimed job whose result already exists is never re-sent to the
model). No graph state is persisted, so no plaintext graph state can leak; the
Spec 3 AES-256-GCM `EncryptedCheckpointer` (ADR 0003) remains mounted at the
composition root for a future long-running graph.

## Consequences

- No dependency major upgrade under Specs 2/3; the agent uses the same LangChain
  primitives (`BaseChatModel.bind_tools`, `StructuredTool`, LangGraph
  `StateGraph`) the assessment requires ("a real LangChain agent invoking at
  least one custom tool").
- A future move to LangChain 1.x `create_agent` can replace `ToolAgent` behind
  the same `run(plan_brief, required, adapter, budget)` contract without touching
  the coordinators.
- Typical turn cost: one interpretation call + one tool-selection call.
- **No model or tool-set winner is declared** (Spec 4 Req 11.10); Tool_Set_A and
  Tool_Set_B are both mountable (`AGENT_TOOL_SET=A|B`). The default `B` is the
  F2 §5 *hypothesis* ("candidata preferida"), not an evaluated result; the A/B
  comparison is an experiment resolved by Spec 6.
