# QuotaShift attack-effect report — `v4_r2f_s2048`

> Live target measurements.

- Control: `benign_only(self victims)`  ·  seeds: 3  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 3).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **3.66×**  (median 3.37×, 95% bootstrap CI [3.06, 4.56])
- **Threshold-crossing rate: 100%** of 3 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 120832 tokens, 59 requests per run.
- Victim slowdown per 1k competing tokens: 0.0220
- Victim slowdown per 100 competing requests: 4.5121

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 526.30 | 156.14 | 3.37 | yes | 0/0 |
| 43 | 504.49 | 164.86 | 3.06 | yes | 0/0 |
| 44 | 767.34 | 168.44 | 4.56 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 526.3 | 526.3 | 0.0 | 2591.3 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 156.1 | 156.1 | 0.0 | 1423.9 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 504.5 | 468.7 | 0.0 | 2666.1 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 164.9 | 164.9 | 0.0 | 1432.4 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 767.3 | 625.3 | 334.3 | 3012.4 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 168.4 | 168.4 | 0.0 | 1462.4 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 3.309 | [2.843, 3.712] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 3.662 | [3.060, 4.556] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 1.914 | [1.820, 2.060] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 1.000 | [1.000, 1.000] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.151 | [1.142, 1.161] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.121 | [0.111, 0.127] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.121 | [0.111, 0.127] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.120 | [0.110, 0.126] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.192 | [0.179, 0.201] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 133611 | 133611 | 125387 | 8224 | 34.11 | 207.12 | 91.85 | 31037.5 | 33125.8 | 294.6 | 0.109 | 0 | False |
| control | 42 | 12779 | 12779 | 6443 | 6336 | 4.14 | 124.95 | 75.17 | 26724.6 | 28825.5 | 261.7 | 0.006 | 0 | False |
| attack | 43 | 135431 | 135431 | 126503 | 8928 | 33.21 | 230.64 | 95.27 | 31130.2 | 33348.0 | 290.9 | 0.167 | 0 | False |
| control | 43 | 14599 | 14599 | 7559 | 7040 | 4.62 | 139.32 | 79.44 | 27076.1 | 29171.4 | 260.4 | 0.008 | 0 | False |
| attack | 44 | 135934 | 135934 | 126942 | 8992 | 35.21 | 228.24 | 95.97 | 31955.4 | 34200.6 | 296.2 | 0.115 | 0 | False |
| control | 44 | 15102 | 15102 | 7998 | 7104 | 4.77 | 140.90 | 79.14 | 27987.7 | 30049.1 | 264.9 | 0.011 | 0 | False |

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
| tokenized_context | pass | max completed prompt+max_output 2048.0 <= 4096; pre-run check ok |
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 817/817 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 6c5615b0e019, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.016 (max 0.25), earliest last arrival 0.983 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **insufficient_seeds**.

