# Series 76 Technical Assistant — Claude Code project instructions

These are the working rules Claude Code (Claude Opus) followed while finishing the
implementation of this repository, after Kiro (see `../.kiro/`) had implemented
Specs F1–F3. They were kept as Claude Code's persistent project memory during the work.

## Sources of truth, in order of precedence

1. `Series76_Kiro_Handoff_v1.0/02_ORIGINAL_SOURCES/assessment-en.pdf` — the evaluated
   requirements.
2. `series_76_electric_data.pdf` — the **only** source of technical numbers.
3. The six Kiro specs in `.kiro/specs/*` (requirements, design, tasks) — binding.
4. The canonical handoff `Series76_Kiro_Handoff_v1.0/01_CANONICAL_F0_F6/` (F6 first).

## Non-negotiable rules

- **No invented numbers, ever.** Every catalog figure comes from the audited edition of
  the PDF. The LLM never sources a number, SQL, the catalog edition or a permission.
- **AES-256-GCM everywhere** application data is encrypted; never relax it silently.
- **Budget:** USD 10 hard cap on the OpenRouter key; at most USD 6 for development and
  evaluation; keep at least USD 4 for the demo. Every model call goes through the
  cumulative cost ledger.
- **Honesty:** nothing is claimed as executed, passed, benchmarked or measured without
  a persisted Evidence_Record (`docs/evidence/evidence.jsonl`). Anything not executed is
  labeled as such. No model winner is declared without paired A/B evidence.
- **Never weaken an invariant to make a test pass.** Fix the code or the test's wrong
  assumption, and say which.
- When a real incompatibility with an approved decision appears, stop on that point,
  compare alternatives and ask the owner.

## Work method

- Work directly on `main`; commit and push each verified slice; never force-push.
- Per slice: `ruff check src tests`, `mypy src` (strict), the unit suite, and the
  relevant integration suites (real PostgreSQL via Testcontainers).
- Record evidence with `python -m series76_eval run-level <level>` on the committed code.
- The owner runs anything that needs his machine (Gradle/emulator, cold start, keys);
  his logs are recorded as owner-run evidence, never re-described as agent-run.
- Re-verify human audit work against the PDF page images before building on it.

## Language

The owner writes in Spanish and gets replies in Spanish. Code, identifiers, comments,
tests and commit messages are in English.
