# QuotaShift attack-effect report — `v4_r2f_s128`

> Live target measurements.

- Control: `benign_only(self victims)`  ·  seeds: 3  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 3).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **17.17×**  (median 14.79×, 95% bootstrap CI [10.23, 26.48])
- **Threshold-crossing rate: 100%** of 3 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 120064 tokens, 938 requests per run.
- Victim slowdown per 1k competing tokens: 0.1346
- Victim slowdown per 100 competing requests: 1.7234

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 2051.99 | 200.65 | 10.23 | yes | 0/0 |
| 43 | 2671.88 | 180.69 | 14.79 | yes | 0/0 |
| 44 | 5006.82 | 189.06 | 26.48 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 0.939 | 2052.0 | 193.4 | 1895.9 | 3472.8 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 200.7 | 200.7 | 0.0 | 1480.6 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.764 | 2671.9 | 187.7 | 2545.5 | 4105.5 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 180.7 | 180.7 | 0.0 | 1448.2 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 0.279 | 5006.8 | 212.5 | 4914.7 | 6460.7 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 189.1 | 189.1 | 0.0 | 1452.6 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.042 | [0.964, 1.124] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 17.165 | [10.227, 26.482] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 3.209 | [2.346, 4.448] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 0.661 | [0.279, 0.939] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.281 | [1.271, 1.293] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.135 | [0.124, 0.142] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.135 | [0.124, 0.142] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.133 | [0.122, 0.140] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.674 | [0.656, 0.696] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 132843 | 132843 | 96491 | 36352 | 79.19 | 800.18 | 120.84 | 34381.7 | 36582.3 | 316.2 | 0.014 | 0 | False |
| control | 42 | 12779 | 12779 | 6443 | 6336 | 4.06 | 124.86 | 72.46 | 26595.5 | 28741.2 | 259.3 | 0.006 | 0 | False |
| attack | 43 | 134663 | 134663 | 97607 | 37056 | 73.73 | 813.80 | 121.26 | 34703.8 | 37005.7 | 316.5 | 0.014 | 0 | False |
| control | 43 | 14599 | 14599 | 7559 | 7040 | 4.64 | 139.32 | 80.55 | 27122.4 | 29170.1 | 260.4 | 0.009 | 0 | False |
| attack | 44 | 135166 | 135166 | 98046 | 37120 | 92.87 | 814.56 | 123.86 | 35363.6 | 37636.0 | 315.9 | 0.015 | 0 | False |
| control | 44 | 15102 | 15102 | 7998 | 7104 | 4.77 | 140.86 | 80.04 | 27820.4 | 29988.5 | 265.5 | 0.009 | 0 | False |

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
| tokenized_context | pass | max completed prompt+max_output 224.0 <= 4096; pre-run check ok |
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 3454/3454 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 6c5615b0e019, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.002 (max 0.25), earliest last arrival 0.999 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **insufficient_seeds**.

