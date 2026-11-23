# QuotaShift attack-effect report — `v4_r2f_s3584`

> Live target measurements.

- Control: `benign_only(self victims)`  ·  seeds: 3  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 3).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **4.68×**  (median 4.87×, 95% bootstrap CI [4.30, 4.89])
- **Threshold-crossing rate: 100%** of 3 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 118272 tokens, 33 requests per run.
- Victim slowdown per 1k competing tokens: 0.0311
- Victim slowdown per 100 competing requests: 11.1627

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 714.83 | 166.39 | 4.30 | yes | 0/0 |
| 43 | 797.89 | 163.98 | 4.87 | yes | 0/0 |
| 44 | 797.73 | 163.16 | 4.89 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 714.8 | 714.8 | 0.0 | 2879.4 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 166.4 | 166.4 | 0.0 | 1425.4 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 797.9 | 673.3 | 38.8 | 3451.8 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 164.0 | 164.0 | 0.0 | 1431.4 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 797.7 | 672.0 | 44.7 | 3433.6 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 163.2 | 163.2 | 0.0 | 1441.8 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 4.174 | [4.106, 4.296] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 4.684 | [4.296, 4.889] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 2.271 | [2.020, 2.411] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 1.000 | [1.000, 1.000] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.114 | [1.098, 1.138] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.119 | [0.111, 0.125] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.119 | [0.111, 0.125] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.118 | [0.109, 0.125] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.186 | [0.169, 0.195] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 131051 | 131051 | 123659 | 7392 | 36.85 | 186.11 | 90.57 | 30537.4 | 32514.4 | 291.8 | 0.149 | 0 | False |
| control | 42 | 12779 | 12779 | 6443 | 6336 | 4.03 | 124.86 | 74.13 | 26826.5 | 28999.1 | 261.9 | 0.006 | 0 | False |
| attack | 43 | 132871 | 132871 | 124775 | 8096 | 38.35 | 217.04 | 89.26 | 30045.2 | 32097.2 | 284.1 | 0.244 | 1 | False |
| control | 43 | 14599 | 14599 | 7559 | 7040 | 4.67 | 139.32 | 78.39 | 27357.7 | 29467.7 | 259.8 | 0.008 | 0 | False |
| attack | 44 | 133374 | 133374 | 125214 | 8160 | 37.84 | 211.73 | 91.53 | 30937.9 | 33156.6 | 290.4 | 0.197 | 1 | False |
| control | 44 | 15102 | 15102 | 7998 | 7104 | 4.73 | 140.81 | 83.59 | 27962.9 | 30089.0 | 265.6 | 0.010 | 0 | False |

### Per-request prefix-cache hits (reported-only; null = missing, not 0)

| arm | seed | victim coverage | victim hit ratio | competitor hit ratio |
|---|---|---|---|---|
| attack | 42 | 1.000 | 0.000 | 0.000 |
| control | 42 | 1.000 | 0.000 | n/a |
| attack | 43 | 1.000 | 0.000 | 0.000 |
| control | 43 | 1.000 | 0.000 | n/a |
| attack | 44 | 1.000 | 0.000 | 0.000 |
| control | 44 | 1.000 | 0.000 | n/a |

### Validity gates (fail closed; ADR-Q17)

Overall: **PASS**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | pass | lowest arm 1.000 (min 0.95) |
| primary_metric_present | pass | 3/3 seeds have a finite Victim user-facing TTFT P95 |
| tokenized_context | pass | max completed prompt+max_output 3584.0 <= 4096; pre-run check ok |
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 739/739 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 6c5615b0e019, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.037 (max 0.25), earliest last arrival 0.947 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **insufficient_seeds**.

