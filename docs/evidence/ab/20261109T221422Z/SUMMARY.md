# Paired A/B — 20261109T221422Z

Scored at commit `35da6026dbf9e4d7c1e38853acb16739c776a3df`. Every configuration ran the 36-scenario suite once through the real API (one factor varied, the rest on the baseline model, no fallback). Spend is the stack ledger's own record; failed calls are charged at the pre-call estimate.

| Configuration | Successes | Numeric discrepancies | Leaks | Config verified | Spend (USD) | Median latency (s) |
|---|---|---|---|---|---|---|
| current | 35/36 | 0 | 0 | True | 0.020837 | 4.1 |

## Selection per function

- **INTERPRETATION**: openai/gpt-oss-120b — 35/36 critical successes
- **TOOL_CALLING**: deepseek/deepseek-v4-flash — 35/36 critical successes

## Failed scenarios

- current: S09

Cumulative ledger after the run: USD 0.8892135850.
