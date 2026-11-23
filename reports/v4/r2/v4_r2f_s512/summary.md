# QuotaShift attack-effect report — `v4_r2f_s512`

> Live target measurements.

- Control: `benign_only(self victims)`  ·  seeds: 3  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 3).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **3.13×**  (median 2.79×, 95% bootstrap CI [2.23, 4.36])
- **Threshold-crossing rate: 100%** of 3 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 119808 tokens, 234 requests per run.
- Victim slowdown per 1k competing tokens: 0.0177
- Victim slowdown per 100 competing requests: 0.9086

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 370.52 | 166.39 | 2.23 | yes | 0/0 |
| 43 | 454.44 | 162.75 | 2.79 | yes | 0/0 |
| 44 | 807.01 | 185.11 | 4.36 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 370.5 | 292.4 | 0.0 | 2323.5 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 166.4 | 166.4 | 0.0 | 1425.2 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 454.4 | 266.8 | 260.9 | 2481.6 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 162.7 | 162.7 | 0.0 | 1444.6 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 807.0 | 290.9 | 729.8 | 2742.8 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 185.1 | 185.1 | 0.0 | 1446.8 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.656 | [1.571, 1.757] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 3.126 | [2.227, 4.360] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 1.748 | [1.630, 1.896] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 1.000 | [1.000, 1.000] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.227 | [1.210, 1.241] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.130 | [0.118, 0.135] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.130 | [0.118, 0.135] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.128 | [0.116, 0.133] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.328 | [0.306, 0.346] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 132587 | 132587 | 118763 | 13824 | 48.61 | 360.89 | 109.67 | 32869.7 | 34899.6 | 309.8 | 0.048 | 0 | False |
| control | 42 | 12779 | 12779 | 6443 | 6336 | 4.05 | 124.89 | 77.80 | 26759.7 | 28901.6 | 259.5 | 0.006 | 0 | False |
| attack | 43 | 134407 | 134407 | 119879 | 14528 | 48.43 | 390.00 | 113.03 | 33818.7 | 35956.3 | 311.5 | 0.054 | 0 | False |
| control | 43 | 14599 | 14599 | 7559 | 7040 | 4.60 | 139.26 | 77.77 | 27246.0 | 29295.6 | 261.8 | 0.009 | 0 | False |
| attack | 44 | 134910 | 134910 | 120318 | 14592 | 49.80 | 400.63 | 110.53 | 33723.4 | 35642.1 | 311.0 | 0.049 | 0 | False |
| control | 44 | 15102 | 15102 | 7998 | 7104 | 4.77 | 140.86 | 81.97 | 27866.2 | 29971.8 | 266.4 | 0.010 | 0 | False |

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
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 1342/1342 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 6c5615b0e019, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.004 (max 0.25), earliest last arrival 0.997 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **insufficient_seeds**.

