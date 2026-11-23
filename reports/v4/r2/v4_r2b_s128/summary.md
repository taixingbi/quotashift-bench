# QuotaShift attack-effect report — `v4_r2b_s128`

> Live target measurements.

- Control: `benign_only(self victims)`  ·  seeds: 3  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 3).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **5.46×**  (median 4.32×, 95% bootstrap CI [4.26, 7.81])
- **Threshold-crossing rate: 100%** of 3 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 48000 tokens, 375 requests per run.
- Victim slowdown per 1k competing tokens: 0.0929
- Victim slowdown per 100 competing requests: 1.1896

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 850.99 | 197.15 | 4.32 | yes | 0/0 |
| 43 | 743.45 | 174.47 | 4.26 | yes | 0/0 |
| 44 | 1261.00 | 161.55 | 7.81 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 851.0 | 163.5 | 682.6 | 2189.9 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 197.2 | 197.2 | 0.0 | 1465.9 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 743.5 | 168.3 | 642.7 | 2079.1 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 174.5 | 174.5 | 0.0 | 1445.9 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 0.982 | 1261.0 | 161.5 | 1165.6 | 2627.3 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 161.6 | 161.6 | 0.0 | 1459.7 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 0.931 | [0.829, 1.000] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 5.461 | [4.261, 7.806] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 1.577 | [1.438, 1.800] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 0.994 | [0.982, 1.000] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.253 | [1.238, 1.268] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.285 | [0.263, 0.296] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.285 | [0.263, 0.296] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.281 | [0.259, 0.292] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 1.088 | [1.069, 1.110] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 60779 | 60779 | 30443 | 30336 | 26.14 | 629.65 | 120.59 | 33612.8 | 35690.4 | 312.7 | 0.012 | 0 | False |
| control | 42 | 12779 | 12779 | 6443 | 6336 | 4.14 | 124.89 | 75.17 | 26856.0 | 28944.6 | 262.1 | 0.006 | 0 | False |
| attack | 43 | 62599 | 62599 | 31559 | 31040 | 26.38 | 644.36 | 120.36 | 34045.0 | 36208.4 | 313.3 | 0.013 | 0 | False |
| control | 43 | 14599 | 14599 | 7559 | 7040 | 4.65 | 139.35 | 76.98 | 26842.6 | 28991.9 | 260.4 | 0.009 | 0 | False |
| attack | 44 | 63102 | 63102 | 31998 | 31104 | 26.56 | 648.38 | 120.52 | 34044.9 | 36196.5 | 313.6 | 0.013 | 0 | False |
| control | 44 | 15102 | 15102 | 7998 | 7104 | 4.73 | 140.83 | 79.99 | 27489.8 | 29706.0 | 263.3 | 0.010 | 0 | False |

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
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 1765/1765 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 6c5615b0e019, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.004 (max 0.25), earliest last arrival 0.997 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **insufficient_seeds**.

