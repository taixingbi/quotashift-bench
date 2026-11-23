# QuotaShift attack-effect report — `a8_lifecycle_churn`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/v3/a8_lifecycle_churn/.

- Control: `lifecycle_normal`  ·  seeds: 5  ·  pre-registered metric: **Victim backend TTFT P95 (historical `ttft_p95`)** (`ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_sent (backend dispatch); excludes gateway queue time (ADR-Q16)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **negative** (seeds with metric: 5).

## Victim backend TTFT P95 (historical `ttft_p95`): victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim backend TTFT P95 (historical `ttft_p95`): **0.98×**  (median 0.98×, 95% bootstrap CI [0.87, 1.06])
- **Threshold-crossing rate: 0%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 8525 tokens, 29 requests per run.
- Victim slowdown per 1k competing tokens: -0.0029
- Victim slowdown per 100 competing requests: -0.0862

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 129.58 | 133.10 | 0.97 | no | 0/0 |
| 43 | 135.95 | 170.63 | 0.80 | no | 0/0 |
| 44 | 151.41 | 153.77 | 0.98 | no | 0/0 |
| 45 | 136.50 | 136.57 | 1.00 | no | 0/0 |
| 46 | 144.59 | 128.84 | 1.12 | no | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 129.6 | 129.6 | 0.0 | 1481.8 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 0.970 | 799.4 | 133.1 | 724.8 | 2171.7 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 147.1 | 136.0 | 0.0 | 1601.4 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.927 | 2289.1 | 170.6 | 2187.3 | 3650.5 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 171.7 | 151.4 | 0.0 | 1580.9 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 0.955 | 1524.0 | 153.8 | 1422.4 | 2953.1 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 273.9 | 136.5 | 188.7 | 1632.8 |
| control | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 0.943 | 2082.8 | 136.6 | 1953.3 | 3421.3 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 171.1 | 144.6 | 12.3 | 1574.8 |
| control | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 0.887 | 2436.3 | 128.8 | 2336.3 | 3766.6 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 0.975 | [0.873, 1.065] | negative |
| Victim user-facing TTFT P95 | ms | 0.108 | [0.078, 0.140] | negative |
| Victim gateway queue time P95 | ms | 0.020 | [0.000, 0.059] | negative |
| Victim end-to-end latency P95 | ms | 0.510 | [0.442, 0.600] | negative |
| Victim offered-load SLO success | fraction of offered | 1.069 | [1.043, 1.098] | negative |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.969 | [0.957, 0.981] | negative |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 1.453 | [1.425, 1.476] | supported |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.972 | [0.960, 0.983] | negative |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.549 | [0.540, 0.557] | negative |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |
| 45 | control→attack | 0.000 | 0.000 | False/False |
| 46 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 32709 | 28551 | 20860 | 13132 | 8.29 | 249.71 | 89.56 | 25164.2 | 27357.2 | 307.5 | 0.017 | 0 | False |
| control | 42 | 32709 | 43451 | 20860 | 22591 | 10.86 | 472.40 | 94.94 | 26530.8 | 28738.7 | 310.9 | 0.028 | 0 | False |
| attack | 43 | 34815 | 32164 | 23282 | 14117 | 9.35 | 274.65 | 87.89 | 24765.4 | 26993.6 | 306.7 | 0.027 | 0 | False |
| control | 43 | 34815 | 46694 | 23282 | 23412 | 12.12 | 494.30 | 91.59 | 25710.6 | 27971.0 | 309.2 | 0.031 | 0 | False |
| attack | 44 | 38084 | 34315 | 25205 | 15246 | 9.79 | 296.50 | 90.13 | 25175.0 | 27379.7 | 310.6 | 0.025 | 0 | False |
| control | 44 | 38084 | 51081 | 25205 | 25876 | 12.76 | 549.84 | 91.34 | 25464.8 | 27617.3 | 309.3 | 0.032 | 0 | False |
| attack | 45 | 39890 | 34259 | 24350 | 16740 | 9.20 | 324.63 | 91.94 | 25818.3 | 28012.2 | 310.0 | 0.031 | 0 | False |
| control | 45 | 39890 | 52207 | 24350 | 27857 | 12.64 | 587.84 | 95.16 | 26509.5 | 28668.5 | 310.8 | 0.031 | 0 | False |
| attack | 46 | 40033 | 34790 | 25063 | 16388 | 10.12 | 317.53 | 90.53 | 25449.3 | 27714.0 | 304.9 | 0.026 | 0 | False |
| control | 46 | 40033 | 52603 | 25063 | 27540 | 13.31 | 583.16 | 93.62 | 26194.7 | 28414.3 | 309.6 | 0.030 | 0 | False |

### Per-request prefix-cache hits (reported-only; null = missing, not 0)

| arm | seed | victim coverage | victim hit ratio | competitor hit ratio |
|---|---|---|---|---|
| attack | 42 | 1.000 | 0.000 | 0.000 |
| control | 42 | 1.000 | 0.000 | 0.000 |
| attack | 43 | 1.000 | 0.000 | 0.000 |
| control | 43 | 1.000 | 0.000 | 0.000 |
| attack | 44 | 1.000 | 0.000 | 0.000 |
| control | 44 | 1.000 | 0.000 | 0.000 |
| attack | 45 | 1.000 | 0.000 | 0.000 |
| control | 45 | 1.000 | 0.000 | 0.000 |
| attack | 46 | 1.000 | 0.000 | 0.000 |
| control | 46 | 1.000 | 0.000 | 0.000 |

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

