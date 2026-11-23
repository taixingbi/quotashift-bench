# QuotaShift attack-effect report — `v4_r1_decode_vs_short_L200`

> Live target measurements.

- Control: `token_matched_fixed`  ·  seeds: 5  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **supported** (seeds with metric: 5).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **4.36×**  (median 6.28×, 95% bootstrap CI [2.24, 6.34])
- **Threshold-crossing rate: 80%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 24000 tokens, 75 requests per run.
- Victim slowdown per 1k competing tokens: 0.1400
- Victim slowdown per 100 competing requests: 4.4810

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 177.61 | 170.95 | 1.04 | no | 0/0 |
| 43 | 1323.54 | 209.22 | 6.33 | yes | 0/0 |
| 44 | 1182.95 | 185.09 | 6.39 | yes | 0/0 |
| 45 | 1021.84 | 162.81 | 6.28 | yes | 0/0 |
| 46 | 300.21 | 169.50 | 1.77 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 177.6 | 168.2 | 0.0 | 1493.4 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 171.0 | 168.7 | 0.0 | 1476.4 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.955 | 1323.5 | 181.5 | 1232.6 | 2651.6 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 209.2 | 172.3 | 41.6 | 1572.6 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 1182.9 | 152.2 | 1091.5 | 2508.4 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 185.1 | 163.6 | 57.5 | 1512.7 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 0.981 | 1021.8 | 166.4 | 946.4 | 2367.8 |
| control | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 162.8 | 157.5 | 0.0 | 1473.6 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 300.2 | 172.7 | 213.5 | 1590.1 |
| control | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 169.5 | 169.5 | 0.0 | 1471.1 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.011 | [0.968, 1.047] | negative |
| Victim user-facing TTFT P95 | ms | 4.361 | [2.243, 6.342] | supported |
| Victim gateway queue time P95 | ms | 24.313 | [18.992, 29.633] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 1.409 | [1.155, 1.659] | inconclusive |
| Victim offered-load SLO success | fraction of offered | 0.987 | [0.969, 1.000] | negative |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.036 | [1.025, 1.044] | negative |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 1.038 | [1.027, 1.046] | negative |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 1.038 | [1.027, 1.046] | negative |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 1.035 | [1.025, 1.044] | negative |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 1.355 | [1.349, 1.362] | supported |

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
| attack | 42 | 36779 | 36779 | 11243 | 25536 | 8.79 | 518.84 | 120.71 | 33991.6 | 36137.4 | 310.5 | 0.023 | 0 | False |
| control | 42 | 36843 | 36843 | 18475 | 18368 | 14.64 | 371.96 | 113.77 | 32536.5 | 34721.0 | 305.9 | 0.011 | 0 | False |
| attack | 43 | 38599 | 38599 | 12359 | 26240 | 9.40 | 535.23 | 120.43 | 33675.5 | 35817.3 | 304.0 | 0.029 | 0 | False |
| control | 43 | 38663 | 38663 | 19591 | 19072 | 15.37 | 387.80 | 113.70 | 32372.0 | 34553.8 | 304.4 | 0.012 | 0 | False |
| attack | 44 | 39102 | 39102 | 12798 | 26304 | 9.57 | 535.59 | 122.42 | 34522.3 | 36809.6 | 310.9 | 0.023 | 0 | False |
| control | 44 | 39166 | 39166 | 20030 | 19136 | 15.57 | 389.25 | 114.53 | 32995.0 | 35196.7 | 305.0 | 0.013 | 0 | False |
| attack | 45 | 37773 | 37773 | 11789 | 25984 | 9.21 | 527.73 | 123.01 | 34445.9 | 36539.7 | 310.0 | 0.026 | 0 | False |
| control | 45 | 37837 | 37837 | 19021 | 18816 | 14.90 | 380.71 | 116.48 | 33229.5 | 35390.0 | 307.7 | 0.011 | 0 | False |
| attack | 46 | 39004 | 39004 | 12444 | 26560 | 9.86 | 541.20 | 119.17 | 33588.9 | 35801.7 | 308.7 | 0.024 | 0 | False |
| control | 46 | 39068 | 39068 | 19676 | 19392 | 15.74 | 393.93 | 115.15 | 33132.4 | 35359.5 | 305.9 | 0.012 | 0 | False |

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
| provenance | pass | sha 05ae0ed77433, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.030 (max 0.25), earliest last arrival 0.969 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **supported**.

