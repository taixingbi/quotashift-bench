# QuotaShift attack-effect report — `v4_r2f_s1024_direct`

> Live target measurements.

- Control: `benign_only(self victims)`  ·  seeds: 3  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 3).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **2.33×**  (median 2.20×, 95% bootstrap CI [1.98, 2.82])
- **Threshold-crossing rate: 100%** of 3 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 119808 tokens, 117 requests per run.
- Victim slowdown per 1k competing tokens: 0.0111
- Victim slowdown per 100 competing requests: 1.1381

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 382.58 | 173.62 | 2.20 | yes | 0/0 |
| 43 | 474.42 | 168.46 | 2.82 | yes | 0/0 |
| 44 | 398.28 | 201.65 | 1.98 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 382.6 | 382.6 | 0.0 | 2167.9 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 173.6 | 173.6 | 0.0 | 1427.6 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 474.4 | 474.4 | 0.0 | 2815.9 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 168.5 | 168.5 | 0.0 | 1430.1 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 398.3 | 398.3 | 0.0 | 2246.9 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 201.7 | 201.7 | 0.0 | 1467.7 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 2.332 | [1.975, 2.816] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 2.332 | [1.975, 2.816] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 1.673 | [1.519, 1.969] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 1.000 | [1.000, 1.000] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.191 | [1.168, 1.212] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.126 | [0.117, 0.131] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.126 | [0.117, 0.131] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.125 | [0.116, 0.129] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.228 | [0.208, 0.239] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 132587 | 132587 | 122507 | 10080 | 35.77 | 242.79 | 102.64 | 32408.7 | 34608.8 | 304.7 | 0.081 | 0 | False |
| control | 42 | 12779 | 12779 | 6443 | 6336 | 4.15 | 124.92 | 76.84 | 26743.9 | 28803.9 | 260.5 | 0.006 | 0 | False |
| attack | 43 | 134407 | 134407 | 123623 | 10784 | 39.02 | 277.93 | 99.53 | 32079.3 | 34293.3 | 298.1 | 0.114 | 0 | False |
| control | 43 | 14599 | 14599 | 7559 | 7040 | 4.66 | 139.33 | 77.41 | 26907.8 | 29041.9 | 260.3 | 0.009 | 0 | False |
| attack | 44 | 134910 | 134910 | 124062 | 10848 | 36.78 | 272.36 | 100.71 | 32325.4 | 34613.2 | 299.3 | 0.075 | 0 | False |
| control | 44 | 15102 | 15102 | 7998 | 7104 | 4.74 | 140.90 | 81.62 | 27684.4 | 29930.3 | 265.9 | 0.011 | 0 | False |

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
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 991/991 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 6c5615b0e019, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.016 (max 0.25), earliest last arrival 0.992 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **insufficient_seeds**.

