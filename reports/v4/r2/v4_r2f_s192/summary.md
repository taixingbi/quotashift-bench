# QuotaShift attack-effect report — `v4_r2f_s192`

> Live target measurements.

- Control: `benign_only(self victims)`  ·  seeds: 3  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 3).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **6.82×**  (median 6.50×, 95% bootstrap CI [4.52, 9.43])
- **Threshold-crossing rate: 100%** of 3 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 120000 tokens, 625 requests per run.
- Victim slowdown per 1k competing tokens: 0.0485
- Victim slowdown per 100 competing requests: 0.9311

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 828.51 | 183.18 | 4.52 | yes | 0/0 |
| 43 | 1095.99 | 168.57 | 6.50 | yes | 0/0 |
| 44 | 1527.39 | 161.93 | 9.43 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 828.5 | 214.2 | 720.3 | 2444.5 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 183.2 | 183.2 | 0.0 | 1445.0 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 1096.0 | 176.8 | 962.7 | 2741.3 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 168.6 | 168.6 | 0.0 | 1433.5 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 0.964 | 1527.4 | 196.6 | 1401.8 | 3136.2 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 161.9 | 161.9 | 0.0 | 1469.9 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.144 | [1.049, 1.214] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 6.819 | [4.523, 9.433] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 1.913 | [1.692, 2.134] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 0.988 | [0.964, 1.000] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 1.254 | [1.237, 1.266] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.132 | [0.119, 0.141] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.132 | [0.119, 0.141] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.130 | [0.117, 0.138] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.532 | [0.518, 0.546] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 132779 | 132779 | 106443 | 26336 | 67.85 | 626.86 | 116.69 | 33446.5 | 35493.6 | 315.9 | 0.020 | 0 | False |
| control | 42 | 12779 | 12779 | 6443 | 6336 | 4.11 | 124.94 | 74.94 | 27030.8 | 29202.6 | 263.5 | 0.006 | 0 | False |
| attack | 43 | 134599 | 134599 | 107559 | 27040 | 62.92 | 643.54 | 119.67 | 34487.9 | 36644.7 | 316.6 | 0.021 | 0 | False |
| control | 43 | 14599 | 14599 | 7559 | 7040 | 4.62 | 139.28 | 79.51 | 27235.0 | 29376.1 | 262.4 | 0.008 | 0 | False |
| attack | 44 | 135102 | 135102 | 107998 | 27104 | 62.50 | 649.48 | 119.88 | 34491.9 | 36528.0 | 317.4 | 0.020 | 0 | False |
| control | 44 | 15102 | 15102 | 7998 | 7104 | 4.71 | 140.92 | 81.67 | 27409.1 | 29521.5 | 263.5 | 0.011 | 0 | False |

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
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 2515/2515 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 6c5615b0e019, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.003 (max 0.25), earliest last arrival 0.999 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **insufficient_seeds**.

