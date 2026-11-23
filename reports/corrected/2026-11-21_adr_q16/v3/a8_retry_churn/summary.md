# QuotaShift attack-effect report — `a8_retry_churn`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/v3/a8_retry_churn/.

- Control: `lifecycle_normal`  ·  seeds: 5  ·  pre-registered metric: **Victim backend TTFT P95 (historical `ttft_p95`)** (`ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_sent (backend dispatch); excludes gateway queue time (ADR-Q16)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **negative** (seeds with metric: 5).

## Victim backend TTFT P95 (historical `ttft_p95`): victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim backend TTFT P95 (historical `ttft_p95`): **1.12×**  (median 1.18×, 95% bootstrap CI [0.98, 1.23])
- **Threshold-crossing rate: 20%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 22223 tokens, 75 requests per run.
- Victim slowdown per 1k competing tokens: 0.0052
- Victim slowdown per 100 competing requests: 0.1550

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 131.47 | 145.50 | 0.90 | no | 0/0 |
| 43 | 179.02 | 137.02 | 1.31 | yes | 0/0 |
| 44 | 174.06 | 147.74 | 1.18 | no | 0/0 |
| 45 | 224.11 | 189.72 | 1.18 | no | 0/0 |
| 46 | 196.13 | 194.47 | 1.01 | no | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 1105.4 | 131.5 | 1004.5 | 2428.1 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 0.687 | 4607.2 | 145.5 | 4490.9 | 6001.5 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.936 | 2060.5 | 179.0 | 1974.5 | 3404.3 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.600 | 6811.9 | 137.0 | 6700.7 | 8162.3 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 769.4 | 174.1 | 666.0 | 2128.1 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 0.369 | 13199.3 | 147.7 | 13114.7 | 14532.8 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 0.934 | 2104.2 | 224.1 | 2012.4 | 3466.6 |
| control | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 0.170 | 10809.6 | 189.7 | 10661.3 | 12195.6 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 0.791 | 3798.9 | 196.1 | 3703.5 | 5170.9 |
| control | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 0.104 | 12481.9 | 194.5 | 12385.2 | 13930.6 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.116 | [0.980, 1.231] | negative |
| Victim user-facing TTFT P95 | ms | 0.220 | [0.134, 0.291] | negative |
| Victim gateway queue time P95 | ms | 0.211 | [0.127, 0.282] | negative |
| Victim end-to-end latency P95 | ms | 0.325 | [0.228, 0.403] | negative |
| Victim offered-load SLO success | fraction of offered | 3.761 | [1.748, 5.962] | supported |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.921 | [0.884, 0.964] | negative |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 1.170 | [1.134, 1.206] | negative |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.925 | [0.891, 0.965] | negative |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.735 | [0.711, 0.755] | negative |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.130 | 0.130 | False/False |
| 43 | control→attack | 0.118 | 0.118 | False/False |
| 44 | attack→control | 0.148 | 0.148 | False/False |
| 45 | control→attack | 0.143 | 0.143 | False/False |
| 46 | attack→control | 0.124 | 0.124 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 42786 | 43408 | 21173 | 24010 | 10.37 | 471.70 | 94.23 | 26495.6 | 28704.1 | 310.5 | 0.029 | 0 | False |
| control | 42 | 42786 | 55071 | 21173 | 30730 | 12.65 | 646.01 | 99.70 | 27705.0 | 29929.5 | 309.7 | 0.030 | 0 | False |
| attack | 43 | 44630 | 46793 | 23568 | 24894 | 11.92 | 496.22 | 92.07 | 25801.6 | 28041.8 | 306.7 | 0.032 | 0 | False |
| control | 43 | 44630 | 57686 | 23568 | 30950 | 13.28 | 654.82 | 92.77 | 26041.7 | 28318.4 | 307.9 | 0.030 | 0 | False |
| attack | 44 | 52158 | 50629 | 25667 | 27436 | 12.20 | 537.90 | 93.12 | 26072.7 | 28325.9 | 312.2 | 0.031 | 0 | False |
| control | 44 | 52158 | 67301 | 25667 | 37170 | 14.69 | 784.80 | 106.31 | 29918.1 | 32101.0 | 312.5 | 0.032 | 0 | False |
| attack | 45 | 52503 | 51887 | 24737 | 29350 | 12.16 | 580.81 | 96.08 | 26760.9 | 28787.5 | 311.2 | 0.029 | 0 | False |
| control | 45 | 52503 | 66696 | 24737 | 37815 | 15.15 | 795.30 | 107.37 | 29870.0 | 32113.5 | 311.5 | 0.031 | 0 | False |
| attack | 46 | 51069 | 52990 | 25373 | 29510 | 13.04 | 590.82 | 94.41 | 26315.5 | 28513.2 | 308.1 | 0.031 | 0 | False |
| control | 46 | 51069 | 65830 | 25373 | 36857 | 15.50 | 777.80 | 105.69 | 29583.5 | 31729.4 | 309.5 | 0.030 | 0 | False |

### Per-request prefix-cache hits (reported-only; null = missing, not 0)

| arm | seed | victim coverage | victim hit ratio | competitor hit ratio |
|---|---|---|---|---|
| attack | 42 | 1.000 | 0.000 | 0.450 |
| control | 42 | 1.000 | 0.000 | 0.301 |
| attack | 43 | 1.000 | 0.000 | 0.447 |
| control | 43 | 1.000 | 0.000 | 0.300 |
| attack | 44 | 1.000 | 0.000 | 0.550 |
| control | 44 | 1.000 | 0.000 | 0.342 |
| attack | 45 | 1.000 | 0.000 | 0.443 |
| control | 45 | 1.000 | 0.000 | 0.299 |
| attack | 46 | 1.000 | 0.000 | 0.414 |
| control | 46 | 1.000 | 0.000 | 0.286 |

### Validity gates (fail closed; ADR-Q17)

Overall: **FAIL**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | pass | lowest arm 1.000 (min 0.95; designed client cancels/timeouts counted) |
| primary_metric_present | pass | 5/5 seeds have a finite Victim backend TTFT P95 (historical `ttft_p95`) |
| tokenized_context | FAIL | no pre-run tokenization check recorded |
| provenance | FAIL | dirty ['True']; model revision status not recorded |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |

## Verdict

Under matched budgets, the victim degradation does NOT reach the pre-registered threshold on a majority of seeds (reported as a negative result, per the plan).
Pre-registered CI classification: **negative**.

