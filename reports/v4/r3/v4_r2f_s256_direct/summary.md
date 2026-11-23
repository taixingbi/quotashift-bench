# QuotaShift attack-effect report — `v4_r2f_s256_direct`

> Live target measurements.

- Control: `benign_only(self victims)`  ·  seeds: 3  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 3).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **1.34×**  (median 1.38×, 95% bootstrap CI [1.26, 1.39])
- **Threshold-crossing rate: 100%** of 3 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 120064 tokens, 469 requests per run.
- Victim slowdown per 1k competing tokens: 0.0028
- Victim slowdown per 100 competing requests: 0.0722

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 233.69 | 169.95 | 1.38 | yes | 0/0 |
| 43 | 231.42 | 166.96 | 1.39 | yes | 0/0 |
| 44 | 239.22 | 190.55 | 1.26 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 233.7 | 233.7 | 0.0 | 1936.4 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 170.0 | 170.0 | 0.0 | 1429.4 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 231.4 | 231.4 | 0.0 | 2057.5 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 167.0 | 167.0 | 0.0 | 1434.9 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 239.2 | 239.2 | 0.0 | 2126.7 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 190.5 | 190.5 | 0.0 | 1467.2 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.339 | [1.255, 1.386] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 1.339 | [1.255, 1.386] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 1.413 | [1.355, 1.449] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 1.000 | [1.000, 1.000] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.255 | [1.242, 1.271] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.132 | [0.122, 0.139] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.132 | [0.122, 0.139] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.130 | [0.120, 0.136] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.446 | [0.426, 0.463] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 132843 | 132843 | 111499 | 21344 | 54.52 | 517.30 | 117.18 | 34092.4 | 36169.5 | 314.4 | 0.036 | 0 | False |
| control | 42 | 12779 | 12779 | 6443 | 6336 | 4.12 | 124.94 | 74.55 | 26822.7 | 28930.5 | 261.2 | 0.005 | 0 | False |
| attack | 43 | 134663 | 134663 | 112615 | 22048 | 54.76 | 541.79 | 117.10 | 34032.5 | 36219.0 | 315.1 | 0.051 | 0 | False |
| control | 43 | 14599 | 14599 | 7559 | 7040 | 4.71 | 139.68 | 79.13 | 27171.4 | 29257.2 | 261.4 | 0.009 | 0 | False |
| attack | 44 | 135166 | 135166 | 113054 | 22112 | 54.38 | 548.88 | 119.26 | 34551.7 | 36562.4 | 317.3 | 0.056 | 0 | False |
| control | 44 | 15102 | 15102 | 7998 | 7104 | 4.78 | 140.88 | 82.86 | 27816.5 | 29975.1 | 263.5 | 0.010 | 0 | False |

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

