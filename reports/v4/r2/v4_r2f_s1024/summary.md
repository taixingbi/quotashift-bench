# QuotaShift attack-effect report — `v4_r2f_s1024`

> Live target measurements.

- Control: `benign_only(self victims)`  ·  seeds: 3  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 3).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **3.02×**  (median 3.30×, 95% bootstrap CI [2.05, 3.71])
- **Threshold-crossing rate: 100%** of 3 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 119808 tokens, 117 requests per run.
- Victim slowdown per 1k competing tokens: 0.0169
- Victim slowdown per 100 competing requests: 1.7274

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 388.29 | 189.16 | 2.05 | yes | 0/0 |
| 43 | 567.82 | 172.04 | 3.30 | yes | 0/0 |
| 44 | 621.01 | 167.38 | 3.71 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 388.3 | 388.3 | 0.0 | 2136.3 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 189.2 | 189.2 | 0.0 | 1445.7 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 567.8 | 290.3 | 0.0 | 2549.8 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 172.0 | 172.0 | 0.0 | 1433.3 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 621.0 | 330.0 | 519.9 | 2527.0 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 167.4 | 167.4 | 0.0 | 1442.3 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.904 | [1.687, 2.053] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 3.021 | [2.053, 3.710] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 1.670 | [1.478, 1.779] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 1.000 | [1.000, 1.000] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.180 | [1.169, 1.185] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.125 | [0.114, 0.131] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.125 | [0.114, 0.131] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.123 | [0.113, 0.130] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.226 | [0.208, 0.236] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 132587 | 132587 | 122507 | 10080 | 35.19 | 242.72 | 101.50 | 31881.6 | 33988.0 | 303.7 | 0.081 | 0 | False |
| control | 42 | 12779 | 12779 | 6443 | 6336 | 4.09 | 124.90 | 75.77 | 26908.6 | 29007.4 | 261.4 | 0.006 | 0 | False |
| attack | 43 | 134407 | 134407 | 123623 | 10784 | 36.43 | 275.70 | 101.09 | 32134.5 | 34336.3 | 298.4 | 0.085 | 0 | False |
| control | 43 | 14599 | 14599 | 7559 | 7040 | 4.65 | 139.21 | 77.89 | 27110.5 | 29265.5 | 260.2 | 0.009 | 0 | False |
| attack | 44 | 134910 | 134910 | 124062 | 10848 | 36.33 | 270.63 | 99.64 | 32156.9 | 34300.2 | 298.6 | 0.072 | 0 | False |
| control | 44 | 15102 | 15102 | 7998 | 7104 | 4.75 | 140.80 | 82.38 | 27518.7 | 29645.3 | 264.6 | 0.009 | 0 | False |

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

