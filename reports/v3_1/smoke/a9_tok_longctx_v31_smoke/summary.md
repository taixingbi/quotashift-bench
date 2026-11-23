# QuotaShift attack-effect report — `a9_tok_longctx_v31_smoke`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 1  ·  pre-registered metric: **GPU Dynamic Energy per 1,000 Authorized Tokens** (`gpu_energy_per_1k_authorized_tokens`, unit: J per 1,000 authorized tokens)
- Definition: arm-window GPU dynamic energy (board power minus pre-arm idle) / (planned input + requested output tokens of all requests in the arm / 1000)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **invalid** (seeds with metric: 1).

## GPU Dynamic Energy per 1,000 Authorized Tokens: attack vs matched control

- Mean attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens: **1.01×**  (median 1.01×, 95% bootstrap CI [1.01, 1.01])
- **Threshold-crossing rate: 0%** of 1 seeds crossed the threshold.

### Per-seed detail (matched pairs; values in J per 1,000 authorized tokens)

| seed | attack (J per 1,000 authorized tokens) | control (J per 1,000 authorized tokens) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 427.69 | 423.55 | 1.01 | no | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 41 | 41 | 0 | 0 | 0 | 0 | 1.000 | 179.5 | 179.5 | 0.0 | 2118.6 |
| control | 42 | 41 | 41 | 0 | 0 | 0 | 0 | 0.293 | 9735.9 | 103.0 | 9644.2 | 11050.2 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.743 | [1.743, 1.743] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 0.018 | [0.018, 0.018] | insufficient_seeds |
| Victim gateway queue time P95 | ms | 0.000 | [0.000, 0.000] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 0.192 | [0.192, 0.192] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 3.417 | [3.417, 3.417] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 1.010 | [1.010, 1.010] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 1.009 | [1.009, 1.009] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 1.002 | [1.002, 1.002] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.344 | [0.344, 0.344] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 25324 | 25321 | 21164 | 4157 | 6.71 | 88.21 | 35.08 | 10830.8 | 12919.1 | 285.7 | 0.104 | 0 | False |
| control | 42 | 25336 | 25308 | 12664 | 12644 | 10.43 | 265.27 | 37.97 | 10731.2 | 12903.5 | 303.2 | 0.012 | 0 | False |

### Per-request prefix-cache hits (reported-only; null = missing, not 0)

| arm | seed | victim coverage | victim hit ratio | competitor hit ratio |
|---|---|---|---|---|
| attack | 42 | 1.000 | 0.000 | 0.000 |
| control | 42 | 1.000 | 0.000 | 0.000 |

### Validity gates (fail closed; ADR-Q17)

Overall: **FAIL**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | pass | lowest arm 1.000 (min 0.95) |
| primary_metric_present | pass | 1/1 seeds have a finite GPU Dynamic Energy per 1,000 Authorized Tokens |
| tokenized_context | pass | max completed prompt+max_output 3840.0 <= 4096; pre-run check ok |
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 245/245 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | FAIL | dirty ['True'] |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); secondary latency endpoints only |

## Verdict

Under matched budgets, the attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens does NOT reach the pre-registered threshold on a majority of seeds (reported as a negative result, per the plan).
Pre-registered CI classification: **invalid**. (Computed before validity gates: insufficient_seeds.)

