# QuotaShift attack-effect report — `v4_cal_D_L200`

> Live target measurements.

- Control: `identical_workload`  ·  seeds: 1  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 1).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **1.03×**  (median 1.03×, 95% bootstrap CI [1.03, 1.03])
- **Threshold-crossing rate: 0%** of 1 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 24000 tokens, 75 requests per run.
- Victim slowdown per 1k competing tokens: 0.0011
- Victim slowdown per 100 competing requests: 0.0345

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 1000 | 187.15 | 182.44 | 1.03 | no | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 1000 | 121 | 121 | 0 | 0 | 0 | 0 | 1.000 | 187.2 | 109.0 | 102.6 | 1486.8 |
| control | 1000 | 121 | 121 | 0 | 0 | 0 | 0 | 1.000 | 182.4 | 110.3 | 102.9 | 1495.3 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 0.988 | [0.988, 0.988] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 1.026 | [1.026, 1.026] | insufficient_seeds |
| Victim gateway queue time P95 | ms | 0.996 | [0.996, 0.996] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 0.994 | [0.994, 0.994] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 1.000 | [1.000, 1.000] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 0.998 | [0.998, 0.998] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.998 | [0.998, 0.998] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.998 | [0.998, 0.998] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.998 | [0.998, 0.998] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 1.000 | [1.000, 1.000] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 1000 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 1000 | 39862 | 39862 | 12918 | 26944 | 10.09 | 548.95 | 121.43 | 34107.0 | 36289.2 | 308.4 | 0.023 | 0 | False |
| control | 1000 | 39862 | 39862 | 12918 | 26944 | 10.07 | 549.15 | 121.40 | 34179.7 | 36357.7 | 309.0 | 0.023 | 0 | False |

### Per-request prefix-cache hits (reported-only; null = missing, not 0)

| arm | seed | victim coverage | victim hit ratio | competitor hit ratio |
|---|---|---|---|---|
| attack | 1000 | 1.000 | 0.000 | 0.000 |
| control | 1000 | 1.000 | 0.000 | 0.000 |

### Validity gates (fail closed; ADR-Q17)

Overall: **PASS**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | pass | lowest arm 1.000 (min 0.95) |
| primary_metric_present | pass | 1/1 seeds have a finite Victim user-facing TTFT P95 |
| tokenized_context | pass | max completed prompt+max_output 320.0 <= 4096; pre-run check ok |
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 392/392 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 46e37f686c25, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.005 (max 0.25), earliest last arrival 0.993 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation does NOT reach the pre-registered threshold on a majority of seeds (reported as a negative result, per the plan).
Pre-registered CI classification: **insufficient_seeds**.

