# QuotaShift attack-effect report — `a7_prefix_cache`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/v3/a7_prefix_cache/.

- Control: `prefix_unique`  ·  seeds: 5  ·  pre-registered metric: **Victim backend TTFT P95 (historical `ttft_p95`)** (`ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_sent (backend dispatch); excludes gateway queue time (ADR-Q16)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **supported** (seeds with metric: 5).

## Victim backend TTFT P95 (historical `ttft_p95`): victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim backend TTFT P95 (historical `ttft_p95`): **0.61×**  (median 0.62×, 95% bootstrap CI [0.56, 0.66])
- **Threshold-crossing rate: 100%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 71408 tokens, 75 requests per run.
- Victim slowdown per 1k competing tokens: -0.0055
- Victim slowdown per 100 competing requests: -0.5269

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 218.92 | 379.48 | 0.58 | yes | 0/0 |
| 43 | 233.93 | 374.65 | 0.62 | yes | 0/0 |
| 44 | 228.00 | 326.74 | 0.70 | yes | 0/0 |
| 45 | 227.29 | 369.39 | 0.62 | yes | 0/0 |
| 46 | 201.04 | 386.41 | 0.52 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 135 | 135 | 0 | 0 | 0 | 0 | 1.000 | 285.1 | 218.9 | 37.5 | 3277.7 |
| control | 42 | 135 | 135 | 0 | 0 | 0 | 0 | 1.000 | 707.8 | 379.5 | 402.7 | 3964.1 |
| attack | 43 | 143 | 143 | 0 | 0 | 0 | 0 | 0.993 | 927.6 | 233.9 | 813.4 | 3770.3 |
| control | 43 | 143 | 143 | 0 | 0 | 0 | 0 | 0.965 | 1569.2 | 374.6 | 1381.2 | 4711.4 |
| attack | 44 | 142 | 142 | 0 | 0 | 0 | 0 | 0.986 | 467.6 | 228.0 | 294.8 | 3539.4 |
| control | 44 | 142 | 142 | 0 | 0 | 0 | 0 | 0.986 | 619.1 | 326.7 | 544.5 | 4300.9 |
| attack | 45 | 138 | 138 | 0 | 0 | 0 | 0 | 1.000 | 472.8 | 227.3 | 409.9 | 3505.2 |
| control | 45 | 138 | 138 | 0 | 0 | 0 | 0 | 1.000 | 794.9 | 369.4 | 637.2 | 4486.5 |
| attack | 46 | 148 | 148 | 0 | 0 | 0 | 0 | 1.000 | 462.4 | 201.0 | 343.0 | 3445.6 |
| control | 46 | 148 | 148 | 0 | 0 | 0 | 0 | 1.000 | 1041.0 | 386.4 | 864.1 | 4748.9 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 0.607 | [0.556, 0.659] | supported |
| Victim user-facing TTFT P95 | ms | 0.558 | [0.449, 0.661] | supported |
| Victim gateway queue time P95 | ms | 0.453 | [0.264, 0.601] | supported |
| Victim end-to-end latency P95 | ms | 0.791 | [0.757, 0.820] | inconclusive |
| Victim offered-load SLO success | fraction of offered | 1.006 | [1.000, 1.017] | negative |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.982 | [0.975, 0.988] | negative |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.982 | [0.975, 0.988] | negative |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.983 | [0.974, 0.990] | negative |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.880 | [0.871, 0.889] | negative |

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
| attack | 42 | 114681 | 139380 | 48212 | 19360 | 19.53 | 420.46 | 115.93 | 32826.9 | 34872.3 | 304.8 | 0.050 | 0 | False |
| control | 42 | 114681 | 139380 | 95876 | 19360 | 30.15 | 463.13 | 116.51 | 33885.8 | 36101.9 | 311.6 | 0.069 | 0 | False |
| attack | 43 | 119267 | 145529 | 51129 | 20416 | 20.20 | 452.82 | 113.42 | 32945.2 | 35189.2 | 303.6 | 0.055 | 0 | False |
| control | 43 | 119267 | 145529 | 98873 | 20416 | 31.36 | 501.54 | 114.76 | 33302.3 | 35546.8 | 305.8 | 0.092 | 0 | False |
| attack | 44 | 130379 | 160850 | 59298 | 20576 | 22.39 | 461.15 | 115.75 | 33755.9 | 35993.8 | 311.3 | 0.057 | 0 | False |
| control | 44 | 130379 | 160850 | 114642 | 20576 | 35.00 | 510.98 | 117.02 | 34161.0 | 36297.7 | 315.5 | 0.091 | 0 | False |
| attack | 45 | 134502 | 163114 | 55754 | 20384 | 22.40 | 457.79 | 118.26 | 33893.3 | 36210.9 | 310.2 | 0.062 | 0 | False |
| control | 45 | 134502 | 163109 | 117946 | 20379 | 36.93 | 513.66 | 119.74 | 34609.6 | 36815.7 | 315.7 | 0.114 | 0 | False |
| attack | 46 | 137998 | 167943 | 58167 | 21568 | 23.11 | 487.28 | 119.83 | 34181.4 | 36445.1 | 312.0 | 0.058 | 0 | False |
| control | 46 | 137998 | 167943 | 119191 | 21568 | 37.53 | 552.82 | 120.39 | 34693.0 | 37007.5 | 316.3 | 0.088 | 0 | False |

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

