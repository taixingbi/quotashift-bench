# QuotaShift attack-effect report — `v4_r2f_s96`

> Live target measurements.

- Control: `benign_only(self victims)`  ·  seeds: 3  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 3).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **145.58×**  (median 150.84×, 95% bootstrap CI [114.60, 171.28])
- **Threshold-crossing rate: 100%** of 3 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 120000 tokens, 1250 requests per run.
- Victim slowdown per 1k competing tokens: 1.2048
- Victim slowdown per 100 competing requests: 11.5662

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 23829.45 | 207.93 | 114.60 | yes | 0/0 |
| 43 | 25739.59 | 170.64 | 150.84 | yes | 0/0 |
| 44 | 27749.15 | 162.01 | 171.28 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 0.071 | 23829.5 | 204.9 | 23718.0 | 25270.1 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 207.9 | 207.9 | 0.0 | 1538.9 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.027 | 25739.6 | 189.4 | 25606.0 | 27123.0 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 170.6 | 170.6 | 0.0 | 1448.0 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 0.090 | 27749.1 | 187.3 | 27583.7 | 29106.6 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 162.0 | 162.0 | 0.0 | 1435.3 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.084 | [0.985, 1.156] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 145.577 | [114.604, 171.285] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 18.477 | [16.421, 20.278] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 0.063 | [0.027, 0.090] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.544 | [1.540, 1.546] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.163 | [0.149, 0.172] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.163 | [0.149, 0.172] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.159 | [0.145, 0.169] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.833 | [0.812, 0.853] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 132779 | 132779 | 86443 | 46336 | 87.72 | 1001.05 | 144.40 | 41045.2 | 43151.1 | 313.2 | 0.011 | 0 | False |
| control | 42 | 12779 | 12779 | 6443 | 6336 | 4.14 | 124.85 | 72.03 | 26562.0 | 28589.0 | 260.6 | 0.006 | 0 | False |
| attack | 43 | 134599 | 134599 | 87559 | 47040 | 89.90 | 1018.03 | 147.87 | 41715.7 | 43899.8 | 314.5 | 0.012 | 0 | False |
| control | 43 | 14599 | 14599 | 7559 | 7040 | 4.62 | 139.29 | 79.50 | 26985.3 | 29029.2 | 257.9 | 0.009 | 0 | False |
| attack | 44 | 135102 | 135102 | 87998 | 47104 | 88.83 | 1022.04 | 148.65 | 42466.1 | 44718.7 | 316.5 | 0.012 | 0 | False |
| control | 44 | 15102 | 15102 | 7998 | 7104 | 4.74 | 140.83 | 79.73 | 27566.8 | 29662.9 | 262.9 | 0.009 | 0 | False |

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
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 4390/4390 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 6c5615b0e019, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.002 (max 0.25), earliest last arrival 1.000 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **insufficient_seeds**.

