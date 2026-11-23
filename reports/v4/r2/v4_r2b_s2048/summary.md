# QuotaShift attack-effect report — `v4_r2b_s2048`

> Live target measurements.

- Control: `benign_only(self victims)`  ·  seeds: 3  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 3).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **17.01×**  (median 3.44×, 95% bootstrap CI [2.82, 44.77])
- **Threshold-crossing rate: 100%** of 3 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 47104 tokens, 23 requests per run.
- Victim slowdown per 1k competing tokens: 0.3399
- Victim slowdown per 100 competing requests: 69.6163

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 456.83 | 162.09 | 2.82 | yes | 0/0 |
| 43 | 7163.87 | 160.00 | 44.77 | yes | 0/0 |
| 44 | 661.23 | 191.99 | 3.44 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 0.970 | 456.8 | 159.5 | 331.2 | 1957.5 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 162.1 | 162.1 | 0.0 | 1452.7 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.800 | 7163.9 | 180.9 | 7075.5 | 8517.3 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 160.0 | 160.0 | 0.0 | 1438.7 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 661.2 | 189.5 | 539.9 | 1973.1 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 192.0 | 192.0 | 0.0 | 1472.8 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.034 | [0.984, 1.131] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 17.012 | [2.818, 44.773] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 2.869 | [1.340, 5.920] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 0.923 | [0.800, 1.000] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.408 | [1.344, 1.448] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.325 | [0.309, 0.347] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.325 | [0.309, 0.347] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.318 | [0.301, 0.340] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 1.103 | [1.081, 1.120] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 59883 | 59883 | 29995 | 29888 | 11.16 | 642.55 | 138.86 | 38879.3 | 41048.2 | 312.7 | 0.196 | 0 | False |
| control | 42 | 12779 | 12779 | 6443 | 6336 | 4.09 | 124.96 | 75.88 | 26848.7 | 29068.3 | 261.6 | 0.006 | 0 | False |
| attack | 43 | 61703 | 61703 | 31111 | 30592 | 11.66 | 663.41 | 130.37 | 36642.7 | 38758.6 | 305.5 | 0.189 | 0 | False |
| control | 43 | 14599 | 14599 | 7559 | 7040 | 4.67 | 139.43 | 79.36 | 27266.4 | 29363.8 | 261.1 | 0.008 | 0 | False |
| attack | 44 | 62206 | 62206 | 31550 | 30656 | 11.82 | 660.39 | 139.52 | 39416.0 | 41554.9 | 313.6 | 0.145 | 0 | False |
| control | 44 | 15102 | 15102 | 7998 | 7104 | 4.75 | 140.97 | 81.42 | 27541.2 | 29688.4 | 263.0 | 0.009 | 0 | False |

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
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 709/709 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 6c5615b0e019, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.037 (max 0.25), earliest last arrival 0.947 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **insufficient_seeds**.

