# QuotaShift attack-effect report — `a7_prefix_cache_reset`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/v3/a7_prefix_cache_reset/.

- Control: `prefix_unique`  ·  seeds: 5  ·  pre-registered metric: **Victim backend TTFT P95 (historical `ttft_p95`)** (`ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_sent (backend dispatch); excludes gateway queue time (ADR-Q16)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **supported** (seeds with metric: 5).

## Victim backend TTFT P95 (historical `ttft_p95`): victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim backend TTFT P95 (historical `ttft_p95`): **0.62×**  (median 0.61×, 95% bootstrap CI [0.57, 0.67])
- **Threshold-crossing rate: 100%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 71408 tokens, 75 requests per run.
- Victim slowdown per 1k competing tokens: -0.0054
- Victim slowdown per 100 competing requests: -0.5157

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 238.14 | 382.59 | 0.62 | yes | 0/0 |
| 43 | 225.66 | 402.90 | 0.56 | yes | 0/0 |
| 44 | 235.59 | 329.85 | 0.71 | yes | 0/0 |
| 45 | 241.61 | 396.10 | 0.61 | yes | 0/0 |
| 46 | 203.66 | 357.36 | 0.57 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 135 | 135 | 0 | 0 | 0 | 0 | 1.000 | 310.4 | 238.1 | 53.3 | 3298.1 |
| control | 42 | 135 | 135 | 0 | 0 | 0 | 0 | 1.000 | 742.2 | 382.6 | 406.7 | 3967.8 |
| attack | 43 | 143 | 143 | 0 | 0 | 0 | 0 | 0.993 | 911.2 | 225.7 | 803.4 | 3757.1 |
| control | 43 | 143 | 143 | 0 | 0 | 0 | 0 | 0.965 | 1569.4 | 402.9 | 1399.7 | 4711.4 |
| attack | 44 | 142 | 142 | 0 | 0 | 0 | 0 | 0.986 | 469.0 | 235.6 | 287.5 | 3538.3 |
| control | 44 | 142 | 142 | 0 | 0 | 0 | 0 | 0.986 | 615.8 | 329.8 | 550.1 | 4311.7 |
| attack | 45 | 138 | 138 | 0 | 0 | 0 | 0 | 1.000 | 531.0 | 241.6 | 409.5 | 3510.8 |
| control | 45 | 138 | 138 | 0 | 0 | 0 | 0 | 1.000 | 751.8 | 396.1 | 632.6 | 4536.2 |
| attack | 46 | 148 | 148 | 0 | 0 | 0 | 0 | 1.000 | 465.0 | 203.7 | 345.5 | 3445.4 |
| control | 46 | 148 | 148 | 0 | 0 | 0 | 0 | 1.000 | 1036.0 | 357.4 | 852.4 | 4730.7 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 0.615 | [0.574, 0.667] | supported |
| Victim user-facing TTFT P95 | ms | 0.583 | [0.463, 0.703] | supported |
| Victim gateway queue time P95 | ms | 0.456 | [0.288, 0.593] | supported |
| Victim end-to-end latency P95 | ms | 0.790 | [0.756, 0.820] | inconclusive |
| Victim offered-load SLO success | fraction of offered | 1.006 | [1.000, 1.017] | negative |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.989 | [0.974, 1.003] | negative |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.989 | [0.974, 1.003] | negative |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.990 | [0.973, 1.006] | negative |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.881 | [0.872, 0.891] | negative |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.598 | 0.201 | False/False |
| 43 | control→attack | 0.591 | 0.210 | False/False |
| 44 | attack→control | 0.577 | 0.183 | False/False |
| 45 | control→attack | 0.609 | 0.174 | False/False |
| 46 | attack→control | 0.603 | 0.186 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 114681 | 139380 | 48212 | 19360 | 19.78 | 422.90 | 115.52 | 33320.6 | 35456.0 | 306.9 | 0.050 | 0 | False |
| control | 42 | 114681 | 139380 | 95876 | 19360 | 31.04 | 463.48 | 116.64 | 33726.4 | 35912.4 | 312.6 | 0.069 | 0 | False |
| attack | 43 | 119267 | 145529 | 51129 | 20416 | 20.36 | 452.99 | 113.60 | 32756.6 | 34894.6 | 303.5 | 0.056 | 0 | False |
| control | 43 | 119267 | 145529 | 98873 | 20416 | 32.32 | 500.23 | 115.13 | 33456.4 | 35754.5 | 307.5 | 0.095 | 0 | False |
| attack | 44 | 130379 | 160850 | 59298 | 20576 | 22.69 | 461.43 | 117.36 | 33654.7 | 35899.4 | 310.5 | 0.058 | 0 | False |
| control | 44 | 130379 | 160850 | 114642 | 20576 | 34.59 | 512.61 | 117.40 | 33200.5 | 35281.0 | 315.4 | 0.080 | 0 | False |
| attack | 45 | 134502 | 163114 | 55754 | 20384 | 22.52 | 457.79 | 117.24 | 33536.0 | 35672.0 | 308.5 | 0.062 | 0 | False |
| control | 45 | 134502 | 163114 | 117946 | 20384 | 37.21 | 515.11 | 118.86 | 34773.6 | 37041.9 | 315.2 | 0.100 | 1 | False |
| attack | 46 | 137998 | 167943 | 58167 | 21568 | 23.04 | 486.99 | 118.93 | 34037.1 | 36365.7 | 310.9 | 0.059 | 0 | False |
| control | 46 | 137998 | 167943 | 119191 | 21568 | 36.04 | 552.17 | 120.43 | 34032.5 | 36228.7 | 316.1 | 0.087 | 0 | False |

### Per-request prefix-cache hits (reported-only; null = missing, not 0)

| arm | seed | victim coverage | victim hit ratio | competitor hit ratio |
|---|---|---|---|---|
| attack | 42 | 1.000 | 0.517 | 0.650 |
| control | 42 | 1.000 | 0.517 | 0.000 |
| attack | 43 | 1.000 | 0.502 | 0.656 |
| control | 43 | 1.000 | 0.502 | 0.000 |
| attack | 44 | 1.000 | 0.454 | 0.661 |
| control | 44 | 1.000 | 0.453 | 0.000 |
| attack | 45 | 1.000 | 0.516 | 0.657 |
| control | 45 | 1.000 | 0.516 | 0.000 |
| attack | 46 | 1.000 | 0.509 | 0.657 |
| control | 46 | 1.000 | 0.509 | 0.000 |

### Validity gates (fail closed; ADR-Q17)

Overall: **FAIL**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | pass | lowest arm 1.000 (min 0.95) |
| primary_metric_present | pass | 5/5 seeds have a finite Victim backend TTFT P95 (historical `ttft_p95`) |
| tokenized_context | FAIL | no pre-run tokenization check recorded |
| provenance | FAIL | dirty ['True']; model revision status not recorded |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **supported**.

