# QuotaShift attack-effect report — `v4_r2f_s256`

> Live target measurements.

- Control: `benign_only(self victims)`  ·  seeds: 3  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 3).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **4.89×**  (median 2.72×, 95% bootstrap CI [2.56, 9.40])
- **Threshold-crossing rate: 100%** of 3 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 120064 tokens, 469 requests per run.
- Victim slowdown per 1k competing tokens: 0.0324
- Victim slowdown per 100 competing requests: 0.8301

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 418.75 | 163.68 | 2.56 | yes | 0/0 |
| 43 | 510.83 | 187.57 | 2.72 | yes | 0/0 |
| 44 | 1563.75 | 166.41 | 9.40 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 418.7 | 211.0 | 343.9 | 2084.5 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 163.7 | 163.7 | 0.0 | 1429.3 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 510.8 | 177.8 | 413.3 | 2218.7 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 187.6 | 187.6 | 0.0 | 1466.8 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 0.982 | 1563.8 | 201.3 | 1426.9 | 3206.2 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 166.4 | 166.4 | 0.0 | 1449.5 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.149 | [0.948, 1.289] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 4.893 | [2.558, 9.397] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 1.728 | [1.458, 2.212] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 0.994 | [0.982, 1.000] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.261 | [1.245, 1.269] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.133 | [0.122, 0.139] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.133 | [0.122, 0.139] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.131 | [0.120, 0.138] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.434 | [0.419, 0.448] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 132843 | 132843 | 111499 | 21344 | 52.91 | 510.07 | 117.27 | 33647.1 | 35795.5 | 313.6 | 0.023 | 0 | False |
| control | 42 | 12779 | 12779 | 6443 | 6336 | 4.16 | 125.17 | 73.29 | 26508.1 | 28644.6 | 259.7 | 0.006 | 0 | False |
| attack | 43 | 134663 | 134663 | 112615 | 22048 | 52.15 | 526.99 | 117.83 | 34229.1 | 36482.2 | 315.8 | 0.025 | 0 | False |
| control | 43 | 14599 | 14599 | 7559 | 7040 | 4.69 | 139.34 | 77.55 | 26996.2 | 29095.5 | 261.9 | 0.008 | 0 | False |
| attack | 44 | 135166 | 135166 | 113054 | 22112 | 54.76 | 528.74 | 118.94 | 34339.1 | 36490.6 | 316.0 | 0.025 | 0 | False |
| control | 44 | 15102 | 15102 | 7998 | 7104 | 4.80 | 140.85 | 82.29 | 27581.1 | 29491.6 | 263.7 | 0.011 | 0 | False |

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
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 2047/2047 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 6c5615b0e019, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.003 (max 0.25), earliest last arrival 0.998 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **insufficient_seeds**.

