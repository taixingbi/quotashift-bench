# QuotaShift attack-effect report — `v4_r2b_s1024`

> Live target measurements.

- Control: `benign_only(self victims)`  ·  seeds: 3  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 3).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **20.42×**  (median 19.71×, 95% bootstrap CI [10.74, 30.80])
- **Threshold-crossing rate: 100%** of 3 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 48128 tokens, 47 requests per run.
- Victim slowdown per 1k competing tokens: 0.4034
- Victim slowdown per 100 competing requests: 41.3111

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 1912.09 | 178.05 | 10.74 | yes | 0/0 |
| 43 | 5031.40 | 163.35 | 30.80 | yes | 0/0 |
| 44 | 3547.76 | 180.01 | 19.71 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 0.960 | 1912.1 | 182.8 | 1810.4 | 3349.4 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 178.1 | 178.1 | 0.0 | 1430.4 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.773 | 5031.4 | 175.6 | 4907.6 | 6377.0 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 163.4 | 163.4 | 0.0 | 1446.3 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 0.910 | 3547.8 | 186.9 | 3469.2 | 4973.1 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 180.0 | 180.0 | 0.0 | 1443.5 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.046 | [1.026, 1.075] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 20.416 | [10.739, 30.801] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 3.399 | [2.342, 4.409] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 0.881 | [0.773, 0.960] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.322 | [1.308, 1.343] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.300 | [0.282, 0.314] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.300 | [0.282, 0.314] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.294 | [0.275, 0.308] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 1.100 | [1.082, 1.117] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 60907 | 60907 | 30507 | 30400 | 12.84 | 652.61 | 126.56 | 35540.7 | 37666.0 | 310.6 | 0.089 | 0 | False |
| control | 42 | 12779 | 12779 | 6443 | 6336 | 4.03 | 124.97 | 72.10 | 26465.7 | 28688.6 | 260.7 | 0.006 | 0 | False |
| attack | 43 | 62727 | 62727 | 31623 | 31104 | 12.93 | 668.43 | 126.82 | 35547.6 | 37667.7 | 309.8 | 0.088 | 0 | False |
| control | 43 | 14599 | 14599 | 7559 | 7040 | 4.66 | 139.33 | 79.85 | 27167.4 | 29247.3 | 259.7 | 0.008 | 0 | False |
| attack | 44 | 63230 | 63230 | 32062 | 31168 | 13.63 | 667.88 | 128.97 | 36539.6 | 38670.9 | 314.0 | 0.095 | 0 | False |
| control | 44 | 15102 | 15102 | 7998 | 7104 | 4.71 | 140.95 | 81.48 | 27787.8 | 29992.3 | 264.7 | 0.008 | 0 | False |

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
| tokenized_context | pass | max completed prompt+max_output 1024.0 <= 4096; pre-run check ok |
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 781/781 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 6c5615b0e019, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.016 (max 0.25), earliest last arrival 0.983 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **insufficient_seeds**.

