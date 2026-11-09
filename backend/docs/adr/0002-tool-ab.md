# ADR 0002: Build both tool assemblies (A and B); defer the winner to Spec 6

- Status: Accepted
- Spec: `domain-and-tools` (Spec 2)
- Supersedes: none
- Related: Requirements 9.2, 9.3 ([EXPERIMENT]); design § "Tool Set A vs Tool Set B"

## Context

The assessment mandates a custom LangChain tool surface over the tabular
catalog. The handoff (F2 §5) proposes two assemblies:

- **Tool Set B (specialized):** `get_part_details`, `search_parts`, and a
  conditionally-exposed `get_source_notes`.
- **Tool Set A (generic baseline):** a single `query_parts` tool with a
  discriminated `{ op: GET | SEARCH, ... }` payload.

Which assembly yields better agent tool-selection accuracy and cost is an
empirical question. Measuring it requires live model runs, which are an
**[EXPERIMENT]** owned by `evaluation-and-reproducibility` (Spec 6).

## Decision

Spec 2 **builds both assemblies** over the *identical* domain operations,
repository, typed input validation, server-injected merge, output
sanitization, and `SemanticFailureCode` set. The two assemblies differ **only**
in the model-visible surface shape; the deterministic core is held constant so
a future A/B test is a fair comparison of tool ergonomics.

**No winner is declared in this spec.** Spec 2 asserts no benchmark result, no
A/B comparison outcome, and no model evaluation. The A/B comparison — including
any winner — is deferred to Spec 6.

## Consequences

- A small amount of adapter duplication between Set A and Set B, justified by a
  reproducible, fair A/B test later.
- Tests in this spec assert only **parity** of the shared core (Set A returns
  the same facts as Set B for identical inputs) and the **existence** of both
  shapes — never a winner or a benchmark result.
- Spec 6 can mount either assembly against a live agent without changing the
  deterministic figure-producing core.
