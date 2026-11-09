# Paired A/B — 20261109T220422Z

Scored at commit `16035da16b9012af46a5ed6b592e0f5d07f78fa9`. Every configuration ran the 36-scenario suite once through the real API (one factor varied, the rest on the baseline model, no fallback). Spend is the stack ledger's own record; failed calls are charged at the pre-call estimate.

| Configuration | Successes | Numeric discrepancies | Leaks | Config verified | Spend (USD) | Median latency (s) |
|---|---|---|---|---|---|---|
| current | 33/36 | 0 | 0 | True | 0.030535 | 4.1 |

## Selection per function

- **INTERPRETATION**: openai/gpt-oss-120b — 33/36 critical successes
- **TOOL_CALLING**: deepseek/deepseek-v4-flash — 33/36 critical successes

## Failed scenarios

- current: S06, S18, S21

Cumulative ledger after the run: USD 0.8683767436.
