# QuotaShift attack-effect report — `v4_r2b_s256`

> Live target measurements.

- Control: `benign_only(self victims)`  ·  seeds: 3  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 3).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **8.91×**  (median 10.44×, 95% bootstrap CI [4.63, 11.65])
- **Threshold-crossing rate: 100%** of 3 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 48128 tokens, 188 requests per run.
- Victim slowdown per 1k competing tokens: 0.1643
- Victim slowdown per 100 competing requests: 4.2054

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 778.08 | 168.01 | 4.63 | yes | 0/0 |
| 43 | 1709.93 | 163.82 | 10.44 | yes | 0/0 |
| 44 | 2040.44 | 175.16 | 11.65 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 778.1 | 177.2 | 661.8 | 2114.3 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 168.0 | 168.0 | 0.0 | 1428.4 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.973 | 1709.9 | 166.1 | 1607.5 | 3077.4 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 163.8 | 163.8 | 0.0 | 1440.7 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 0.946 | 2040.4 | 154.7 | 1959.5 | 3450.0 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 175.2 | 175.2 | 0.0 | 1452.7 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 0.984 | [0.883, 1.055] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 8.906 | [4.631, 11.649] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 1.997 | [1.480, 2.375] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 0.973 | [0.946, 1.000] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.241 | [1.211, 1.269] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.282 | [0.266, 0.290] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.282 | [0.266, 0.290] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.277 | [0.261, 0.286] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 1.092 | [1.071, 1.112] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 60907 | 60907 | 30507 | 30400 | 18.70 | 640.12 | 121.67 | 34124.6 | 36180.2 | 312.1 | 0.023 | 0 | False |
| control | 42 | 12779 | 12779 | 6443 | 6336 | 4.06 | 124.95 | 73.34 | 26893.0 | 29041.6 | 261.8 | 0.006 | 0 | False |
| attack | 43 | 62727 | 62727 | 31623 | 31104 | 19.71 | 656.79 | 119.52 | 33907.6 | 35941.6 | 309.5 | 0.024 | 0 | False |
| control | 43 | 14599 | 14599 | 7559 | 7040 | 4.61 | 139.59 | 78.78 | 27243.1 | 29367.3 | 261.1 | 0.009 | 0 | False |
| attack | 44 | 63230 | 63230 | 32062 | 31168 | 19.60 | 658.80 | 119.31 | 33706.4 | 35800.5 | 313.2 | 0.023 | 0 | False |
| control | 44 | 15102 | 15102 | 7998 | 7104 | 4.77 | 140.91 | 81.99 | 27838.9 | 29915.1 | 266.3 | 0.012 | 0 | False |

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
| tokenized_context | pass | max completed prompt+max_output 256.0 <= 4096; pre-run check ok |
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 1204/1204 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 6c5615b0e019, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.009 (max 0.25), earliest last arrival 0.997 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **insufficient_seeds**.

