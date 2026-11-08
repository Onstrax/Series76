# Series 76 Technical Assistant — Backend (Python)

This package implements the Python slices of the *Series 76 Technical Assistant*:

- **`series76_data`** — Spec 1: data-and-ingestion (the dependency root).
- **`series76_domain`** — Spec 2: domain-and-tools.
- **`series76_api`** — Spec 3: backend-api-auth-jobs-crypto.
- **`series76_agent`** — Spec 4: agent-orchestration-response.
- **`series76_eval`** — Spec 6: evaluation-and-reproducibility.

## Source-of-truth discipline

Every technical number served by this system originates from a cell of
`series_76_electric_data.pdf`, audited and bound by SHA-256 manifest to a
published catalog edition. No value is invented, inferred from a part-number
substring, taken from the summary PDF, or produced by a language model.

## Development

```bash
# Create the pinned virtual environment (Python 3.12) and install deps.
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev]"

# Run the test suite (unit + property tests always; integration tests need Docker).
.venv/bin/pytest
```

Property-based tests use Hypothesis (minimum 100 iterations each) and are
tagged `Feature: <spec-name>, Property N`. Database and concurrency tests run
against a **real PostgreSQL container** via Testcontainers — never a mock.

See the repository root `README.md` for the full system overview, Docker
Compose orchestration, and reproducibility instructions.
