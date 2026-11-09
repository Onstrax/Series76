# Paired A/B — 20261109T212846Z

Scored at commit `80b864a210b533bc2d823042f51d654484bebc83`. Every configuration ran the 36-scenario suite once through the real API (one factor varied, the rest on the baseline model, no fallback). Spend is the stack ledger's own record; failed calls are charged at the pre-call estimate.

| Configuration | Successes | Numeric discrepancies | Leaks | Config verified | Spend (USD) | Median latency (s) |
|---|---|---|---|---|---|---|
| baseline | 28/36 | 0 | 0 | True | 0.035445 | 4.1 |
| interpretation=deepseek/deepseek-v4-flash | 26/36 | 0 | 0 | True | 0.045301 | 9.649999999999999 |
| interpretation=google/gemini-2.5-flash-lite | 0/36 | 0 | 0 | True | 0.560000 | 2.0 |
| tool_calling=deepseek/deepseek-v4-flash | 29/36 | 0 | 0 | True | 0.030883 | 5.1 |
| tool_calling=google/gemini-2.5-flash-lite | 24/36 | 0 | 0 | True | 0.079027 | 4.1 |

## Selection per function

- **INTERPRETATION**: openai/gpt-oss-120b — 28/36 critical successes
- **TOOL_CALLING**: deepseek/deepseek-v4-flash — 29/36 critical successes

## Failed scenarios

- baseline: S14, S15, S21, S23, S24, S27, S30, S31
- interpretation=deepseek/deepseek-v4-flash: S09, S12, S14, S15, S21, S23, S24, S27, S28, S30
- interpretation=google/gemini-2.5-flash-lite: S01, S02, S03, S04, S05, S06, S07, S08, S09, S10, S11, S12, S13, S14, S15, S16, S17, S18, S19, S20, S21, S22, S23, S24, S25, S26, S27, S28, S29, S30, S31, S32, S33, S34, S35, S36
- tool_calling=deepseek/deepseek-v4-flash: S14, S15, S23, S24, S27, S30, S31
- tool_calling=google/gemini-2.5-flash-lite: S05, S06, S07, S09, S14, S15, S21, S23, S24, S27, S30, S31

Cumulative ledger after the run: USD 0.8378415873.
