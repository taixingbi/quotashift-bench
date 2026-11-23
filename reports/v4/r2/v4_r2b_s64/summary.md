# QuotaShift attack-effect report — `v4_r2b_s64`

> Live target measurements.

- Control: `benign_only(self victims)`  ·  seeds: 3  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 3).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **3.92×**  (median 3.62×, 95% bootstrap CI [2.25, 5.89])
- **Threshold-crossing rate: 100%** of 3 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 48000 tokens, 750 requests per run.
- Victim slowdown per 1k competing tokens: 0.0608
- Victim slowdown per 100 competing requests: 0.3894

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 382.29 | 169.66 | 2.25 | yes | 0/0 |
| 43 | 594.82 | 164.46 | 3.62 | yes | 0/0 |
| 44 | 1066.50 | 181.03 | 5.89 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 382.3 | 166.6 | 279.2 | 1663.0 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 169.7 | 169.7 | 0.0 | 1422.8 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 594.8 | 174.2 | 477.4 | 1884.1 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 164.5 | 164.5 | 0.0 | 1452.4 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 1066.5 | 178.7 | 968.9 | 2380.1 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 181.0 | 181.0 | 0.0 | 1436.0 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.010 | [0.982, 1.059] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 3.920 | [2.253, 5.891] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 1.375 | [1.169, 1.657] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 1.000 | [1.000, 1.000] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.227 | [1.208, 1.242] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.279 | [0.259, 0.290] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.279 | [0.259, 0.290] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.276 | [0.257, 0.286] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 1.066 | [1.047, 1.085] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 60779 | 60779 | 30443 | 30336 | 37.12 | 604.94 | 117.86 | 33206.0 | 35346.2 | 309.5 | 0.009 | 0 | False |
| control | 42 | 12779 | 12779 | 6443 | 6336 | 4.02 | 124.91 | 77.82 | 26981.0 | 28877.3 | 261.6 | 0.006 | 0 | False |
| attack | 43 | 62599 | 62599 | 31559 | 31040 | 37.83 | 620.18 | 119.37 | 33758.7 | 35830.0 | 311.9 | 0.011 | 0 | False |
| control | 43 | 14599 | 14599 | 7559 | 7040 | 4.65 | 139.33 | 78.45 | 27181.8 | 29240.0 | 259.5 | 0.008 | 0 | False |
| attack | 44 | 63102 | 63102 | 31998 | 31104 | 37.94 | 622.10 | 120.54 | 33649.6 | 35812.8 | 312.3 | 0.011 | 0 | False |
| control | 44 | 15102 | 15102 | 7998 | 7104 | 4.74 | 140.83 | 85.02 | 27845.3 | 29974.4 | 265.9 | 0.009 | 0 | False |

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
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 2890/2890 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 6c5615b0e019, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.003 (max 0.25), earliest last arrival 0.999 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **insufficient_seeds**.

