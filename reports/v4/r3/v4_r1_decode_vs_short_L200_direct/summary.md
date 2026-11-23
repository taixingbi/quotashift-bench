# QuotaShift attack-effect report — `v4_r1_decode_vs_short_L200_direct`

> Live target measurements.

- Control: `token_matched_fixed`  ·  seeds: 5  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **negative** (seeds with metric: 5).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **1.00×**  (median 1.00×, 95% bootstrap CI [0.96, 1.03])
- **Threshold-crossing rate: 0%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 24000 tokens, 75 requests per run.
- Victim slowdown per 1k competing tokens: -0.0002
- Victim slowdown per 100 competing requests: -0.0055

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 180.43 | 176.31 | 1.02 | no | 0/0 |
| 43 | 169.13 | 183.11 | 0.92 | no | 0/0 |
| 44 | 178.42 | 179.51 | 0.99 | no | 0/0 |
| 45 | 176.60 | 170.08 | 1.04 | no | 0/0 |
| 46 | 173.34 | 173.33 | 1.00 | no | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 180.4 | 180.4 | 0.0 | 1467.7 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 176.3 | 176.3 | 0.0 | 1481.2 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 169.1 | 169.1 | 0.0 | 1459.0 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 183.1 | 183.1 | 0.0 | 1531.7 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 178.4 | 178.4 | 0.0 | 1547.4 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 179.5 | 179.5 | 0.0 | 1491.5 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 176.6 | 176.6 | 0.0 | 1489.2 |
| control | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 170.1 | 170.1 | 0.0 | 1472.5 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 173.3 | 173.3 | 0.0 | 1483.9 |
| control | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 173.3 | 173.3 | 0.0 | 1490.3 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 0.996 | [0.958, 1.026] | negative |
| Victim user-facing TTFT P95 | ms | 0.996 | [0.958, 1.026] | negative |
| Victim end-to-end latency P95 | ms | 0.998 | [0.973, 1.022] | negative |
| Victim offered-load SLO success | fraction of offered | 1.000 | [1.000, 1.000] | negative |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.028 | [1.019, 1.036] | negative |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 1.029 | [1.020, 1.038] | negative |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 1.029 | [1.020, 1.038] | negative |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 1.026 | [1.019, 1.034] | negative |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 1.358 | [1.352, 1.364] | supported |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |
| 45 | control→attack | 0.000 | 0.000 | False/False |
| 46 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 36779 | 36779 | 11243 | 25536 | 8.90 | 518.85 | 121.84 | 33512.8 | 35542.5 | 309.4 | 0.023 | 0 | False |
| control | 42 | 36843 | 36843 | 18475 | 18368 | 14.43 | 371.91 | 113.26 | 32902.2 | 35089.0 | 305.7 | 0.013 | 0 | False |
| attack | 43 | 38599 | 38599 | 12359 | 26240 | 9.35 | 535.92 | 118.90 | 33918.9 | 36136.0 | 306.3 | 0.032 | 0 | False |
| control | 43 | 38663 | 38663 | 19591 | 19072 | 15.41 | 387.66 | 114.66 | 32900.2 | 35112.7 | 305.5 | 0.014 | 0 | False |
| attack | 44 | 39102 | 39102 | 12798 | 26304 | 9.69 | 537.68 | 121.23 | 34206.3 | 36347.7 | 309.2 | 0.025 | 0 | False |
| control | 44 | 39166 | 39166 | 20030 | 19136 | 15.50 | 389.09 | 112.20 | 32910.2 | 35130.9 | 305.7 | 0.014 | 0 | False |
| attack | 45 | 37773 | 37773 | 11789 | 25984 | 9.20 | 528.56 | 123.74 | 34524.4 | 36605.6 | 310.8 | 0.029 | 0 | False |
| control | 45 | 37837 | 37837 | 19021 | 18816 | 15.03 | 380.48 | 118.14 | 33339.2 | 35488.5 | 307.5 | 0.011 | 0 | False |
| attack | 46 | 39004 | 39004 | 12444 | 26560 | 9.76 | 541.46 | 118.56 | 33558.6 | 35717.6 | 311.9 | 0.030 | 0 | False |
| control | 46 | 39068 | 39068 | 19676 | 19392 | 15.68 | 393.70 | 116.88 | 33125.2 | 35199.6 | 306.1 | 0.014 | 0 | False |

### Per-request prefix-cache hits (reported-only; null = missing, not 0)

| arm | seed | victim coverage | victim hit ratio | competitor hit ratio |
|---|---|---|---|---|
| attack | 42 | 1.000 | 0.000 | 0.000 |
| control | 42 | 1.000 | 0.000 | 0.000 |
| attack | 43 | 1.000 | 0.000 | 0.000 |
| control | 43 | 1.000 | 0.000 | 0.000 |
| attack | 44 | 1.000 | 0.000 | 0.000 |
| control | 44 | 1.000 | 0.000 | 0.000 |
| attack | 45 | 1.000 | 0.000 | 0.000 |
| control | 45 | 1.000 | 0.000 | 0.000 |
| attack | 46 | 1.000 | 0.000 | 0.000 |
| control | 46 | 1.000 | 0.000 | 0.000 |

### Validity gates (fail closed; ADR-Q17)

Overall: **PASS**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | pass | lowest arm 1.000 (min 0.95) |
| primary_metric_present | pass | 5/5 seeds have a finite Victim user-facing TTFT P95 |
| tokenized_context | pass | max completed prompt+max_output 320.0 <= 4096; pre-run check ok |
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 2397/2397 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 6c5615b0e019, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.030 (max 0.25), earliest last arrival 0.969 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation does NOT reach the pre-registered threshold on a majority of seeds (reported as a negative result, per the plan).
Pre-registered CI classification: **negative**.

