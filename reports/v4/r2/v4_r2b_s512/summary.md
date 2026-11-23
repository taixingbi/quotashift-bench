# QuotaShift attack-effect report — `v4_r2b_s512`

> Live target measurements.

- Control: `benign_only(self victims)`  ·  seeds: 3  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 3).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **13.75×**  (median 12.72×, 95% bootstrap CI [7.17, 21.37])
- **Threshold-crossing rate: 100%** of 3 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 48128 tokens, 94 requests per run.
- Victim slowdown per 1k competing tokens: 0.2649
- Victim slowdown per 100 competing requests: 13.5649

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 1127.71 | 157.32 | 7.17 | yes | 0/0 |
| 43 | 3595.08 | 168.26 | 21.37 | yes | 0/0 |
| 44 | 2142.70 | 168.48 | 12.72 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 1127.7 | 156.4 | 1039.8 | 2493.4 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 157.3 | 157.3 | 0.0 | 1418.5 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.827 | 3595.1 | 166.4 | 3523.4 | 5063.4 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 168.3 | 168.3 | 0.0 | 1429.6 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 0.919 | 2142.7 | 168.7 | 2028.2 | 3513.2 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 168.5 | 168.5 | 0.0 | 1453.3 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 0.995 | [0.989, 1.002] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 13.751 | [7.168, 21.367] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 2.572 | [1.758, 3.542] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 0.915 | [0.827, 1.000] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.266 | [1.240, 1.289] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.287 | [0.271, 0.296] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.287 | [0.271, 0.296] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.283 | [0.266, 0.293] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 1.098 | [1.077, 1.118] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 60907 | 60907 | 30507 | 30400 | 14.82 | 647.46 | 123.61 | 34670.9 | 36863.2 | 311.9 | 0.046 | 0 | False |
| control | 42 | 12779 | 12779 | 6443 | 6336 | 4.06 | 125.00 | 74.18 | 26890.4 | 29100.4 | 260.3 | 0.006 | 0 | False |
| attack | 43 | 62727 | 62727 | 31623 | 31104 | 15.36 | 665.13 | 122.51 | 34473.9 | 36625.6 | 309.3 | 0.048 | 0 | False |
| control | 43 | 14599 | 14599 | 7559 | 7040 | 4.60 | 139.41 | 80.96 | 27160.7 | 29243.2 | 259.7 | 0.008 | 0 | False |
| attack | 44 | 63230 | 63230 | 32062 | 31168 | 16.12 | 665.43 | 123.13 | 34723.0 | 36894.5 | 313.1 | 0.042 | 0 | False |
| control | 44 | 15102 | 15102 | 7998 | 7104 | 4.73 | 140.89 | 81.91 | 28010.0 | 30106.5 | 265.7 | 0.012 | 0 | False |

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
| tokenized_context | pass | max completed prompt+max_output 512.0 <= 4096; pre-run check ok |
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 922/922 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 6c5615b0e019, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.016 (max 0.25), earliest last arrival 0.983 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **insufficient_seeds**.

