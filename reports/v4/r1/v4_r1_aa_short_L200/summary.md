# QuotaShift attack-effect report — `v4_r1_aa_short_L200`

> Live target measurements.

- Control: `identical_workload`  ·  seeds: 5  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **negative** (seeds with metric: 5).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **0.96×**  (median 0.98×, 95% bootstrap CI [0.85, 1.04])
- **Threshold-crossing rate: 20%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 24064 tokens, 188 requests per run.
- Victim slowdown per 1k competing tokens: -0.0018
- Victim slowdown per 100 competing requests: -0.0232

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 110.53 | 102.69 | 1.08 | no | 0/0 |
| 43 | 143.67 | 141.02 | 1.02 | no | 0/0 |
| 44 | 690.31 | 911.07 | 0.76 | yes | 0/0 |
| 45 | 172.73 | 176.02 | 0.98 | no | 0/0 |
| 46 | 168.91 | 178.23 | 0.95 | no | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 110.5 | 110.5 | 0.0 | 1409.8 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 102.7 | 102.7 | 0.0 | 1419.0 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 143.7 | 110.0 | 0.0 | 1444.8 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 141.0 | 114.3 | 0.0 | 1443.6 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 690.3 | 109.0 | 610.1 | 2030.0 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 911.1 | 342.8 | 734.2 | 2420.5 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 172.7 | 170.8 | 0.0 | 1499.2 |
| control | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 176.0 | 165.7 | 0.0 | 1501.5 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 168.9 | 165.3 | 0.0 | 1474.9 |
| control | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 178.2 | 177.2 | 0.0 | 1563.6 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 0.864 | [0.589, 1.039] | inconclusive |
| Victim user-facing TTFT P95 | ms | 0.956 | [0.848, 1.038] | negative |
| Victim gateway queue time P95 | ms | 0.831 | [0.831, 0.831] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 0.955 | [0.892, 0.998] | negative |
| Victim offered-load SLO success | fraction of offered | 1.000 | [1.000, 1.000] | negative |
| Absolute GPU Dynamic Energy per Arm | J per arm | 0.999 | [0.991, 1.005] | negative |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.999 | [0.991, 1.005] | negative |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.999 | [0.991, 1.005] | negative |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.997 | [0.991, 1.004] | negative |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.999 | [0.997, 1.000] | negative |

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
| attack | 42 | 36843 | 36843 | 18475 | 18368 | 14.54 | 369.89 | 116.77 | 32788.7 | 34924.7 | 302.9 | 0.011 | 0 | False |
| control | 42 | 36843 | 36843 | 18475 | 18368 | 14.63 | 371.47 | 115.49 | 33055.2 | 35323.6 | 305.9 | 0.011 | 0 | False |
| attack | 43 | 38663 | 38663 | 19591 | 19072 | 15.29 | 387.95 | 113.43 | 32431.5 | 34591.8 | 304.9 | 0.012 | 0 | False |
| control | 43 | 38663 | 38663 | 19591 | 19072 | 15.20 | 387.60 | 113.20 | 32860.2 | 35028.9 | 304.9 | 0.013 | 0 | False |
| attack | 44 | 39166 | 39166 | 20030 | 19136 | 15.26 | 390.33 | 111.46 | 32771.1 | 34943.2 | 303.7 | 0.013 | 0 | False |
| control | 44 | 39166 | 39166 | 20030 | 19136 | 15.93 | 389.98 | 109.90 | 32515.0 | 34714.4 | 302.5 | 0.013 | 0 | False |
| attack | 45 | 37837 | 37837 | 19021 | 18816 | 15.08 | 381.88 | 115.43 | 32870.0 | 35033.8 | 305.5 | 0.013 | 0 | False |
| control | 45 | 37837 | 37837 | 19021 | 18816 | 14.86 | 382.09 | 116.01 | 32825.2 | 35005.9 | 305.2 | 0.011 | 0 | False |
| attack | 46 | 39068 | 39068 | 19676 | 19392 | 15.55 | 393.38 | 118.70 | 33439.6 | 35599.2 | 308.9 | 0.012 | 0 | False |
| control | 46 | 39068 | 39068 | 19676 | 19392 | 15.81 | 393.30 | 116.10 | 33285.7 | 35486.0 | 309.2 | 0.012 | 0 | False |

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
| tokenized_context | pass | max completed prompt+max_output 224.0 <= 4096; pre-run check ok |
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 2962/2962 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 05ae0ed77433, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.014 (max 0.25), earliest last arrival 0.997 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation does NOT reach the pre-registered threshold on a majority of seeds (reported as a negative result, per the plan).
Pre-registered CI classification: **negative**.

