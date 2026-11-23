# QuotaShift attack-effect report — `a7v_cache_isolation_validation`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/v3/a7v_cache_isolation_validation/.

- Control: `identical_workload`  ·  seeds: 5  ·  pre-registered metric: **Victim backend TTFT P95 (historical `ttft_p95`)** (`ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_sent (backend dispatch); excludes gateway queue time (ADR-Q16)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **negative** (seeds with metric: 5).

## Victim backend TTFT P95 (historical `ttft_p95`): victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim backend TTFT P95 (historical `ttft_p95`): **0.96×**  (median 0.95×, 95% bootstrap CI [0.92, 1.01])
- **Threshold-crossing rate: 0%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 71408 tokens, 75 requests per run.
- Victim slowdown per 1k competing tokens: -0.0005
- Victim slowdown per 100 competing requests: -0.0511

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 553.63 | 545.84 | 1.01 | no | 0/0 |
| 43 | 601.70 | 661.70 | 0.91 | no | 0/0 |
| 44 | 495.04 | 521.53 | 0.95 | no | 0/0 |
| 45 | 692.26 | 674.99 | 1.03 | no | 0/0 |
| 46 | 634.48 | 696.44 | 0.91 | no | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 135 | 135 | 0 | 0 | 0 | 0 | 0.904 | 2957.9 | 553.6 | 2681.3 | 6923.1 |
| control | 42 | 135 | 135 | 0 | 0 | 0 | 0 | 0.896 | 2905.8 | 545.8 | 2620.1 | 6907.9 |
| attack | 43 | 143 | 143 | 0 | 0 | 0 | 0 | 0.902 | 3119.7 | 601.7 | 2861.1 | 7126.4 |
| control | 43 | 143 | 143 | 0 | 0 | 0 | 0 | 0.902 | 3124.2 | 661.7 | 2817.3 | 7105.5 |
| attack | 44 | 142 | 142 | 0 | 0 | 0 | 0 | 0.894 | 2165.0 | 495.0 | 1940.1 | 6727.3 |
| control | 44 | 142 | 142 | 0 | 0 | 0 | 0 | 0.894 | 2175.9 | 521.5 | 1941.2 | 6735.6 |
| attack | 45 | 138 | 138 | 0 | 0 | 0 | 0 | 0.906 | 2189.9 | 692.3 | 2026.6 | 7199.4 |
| control | 45 | 138 | 138 | 0 | 0 | 0 | 0 | 0.920 | 2210.9 | 675.0 | 2021.8 | 7139.2 |
| attack | 46 | 148 | 148 | 0 | 0 | 0 | 0 | 0.723 | 4023.8 | 634.5 | 3735.9 | 8700.5 |
| control | 46 | 148 | 148 | 0 | 0 | 0 | 0 | 0.723 | 4042.3 | 696.4 | 3632.9 | 8731.3 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 0.962 | [0.918, 1.006] | negative |
| Victim user-facing TTFT P95 | ms | 0.999 | [0.993, 1.009] | negative |
| Victim gateway queue time P95 | ms | 1.014 | [1.004, 1.024] | negative |
| Victim end-to-end latency P95 | ms | 1.002 | [0.999, 1.005] | negative |
| Victim offered-load SLO success | fraction of offered | 0.999 | [0.991, 1.005] | negative |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.992 | [0.988, 0.996] | negative |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.992 | [0.988, 0.996] | negative |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.991 | [0.986, 0.997] | negative |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 1.001 | [0.998, 1.004] | negative |

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
| attack | 42 | 114681 | 213935 | 194575 | 19360 | 52.48 | 577.44 | 121.09 | 35332.9 | 37401.9 | 318.0 | 0.129 | 1 | False |
| control | 42 | 114681 | 213935 | 194575 | 19360 | 53.34 | 579.43 | 121.67 | 35773.6 | 37923.0 | 320.4 | 0.138 | 1 | False |
| attack | 43 | 119267 | 222246 | 201830 | 20416 | 58.22 | 638.63 | 116.03 | 34305.3 | 36328.3 | 316.0 | 0.146 | 1 | False |
| control | 43 | 119267 | 222246 | 201830 | 20416 | 58.86 | 636.95 | 116.22 | 34706.8 | 36875.1 | 316.7 | 0.146 | 1 | False |
| attack | 44 | 130379 | 244795 | 224219 | 20576 | 61.48 | 665.28 | 118.81 | 35024.7 | 37212.6 | 322.7 | 0.141 | 1 | False |
| control | 44 | 130379 | 244795 | 224219 | 20576 | 62.22 | 663.30 | 118.90 | 35452.8 | 37739.2 | 324.3 | 0.141 | 1 | False |
| attack | 45 | 134502 | 253286 | 232902 | 20384 | 67.65 | 671.74 | 122.07 | 36018.8 | 38291.2 | 324.5 | 0.154 | 1 | False |
| control | 45 | 134502 | 253286 | 232902 | 20384 | 68.54 | 669.27 | 122.37 | 36110.0 | 38313.9 | 324.3 | 0.154 | 0 | False |
| attack | 46 | 137998 | 259259 | 237691 | 21568 | 67.30 | 727.20 | 120.43 | 35586.6 | 37750.9 | 324.3 | 0.145 | 1 | False |
| control | 46 | 137998 | 259259 | 237691 | 21568 | 73.41 | 716.90 | 120.87 | 35665.2 | 37803.1 | 323.5 | 0.145 | 0 | False |

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
| competitor_completion | pass | lowest arm 1.000 (min 0.95) |
| primary_metric_present | pass | 5/5 seeds have a finite Victim backend TTFT P95 (historical `ttft_p95`) |
| tokenized_context | FAIL | no pre-run tokenization check recorded |
| provenance | FAIL | dirty ['True']; model revision status not recorded |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |

## Verdict

Under matched budgets, the victim degradation does NOT reach the pre-registered threshold on a majority of seeds (reported as a negative result, per the plan).
Pre-registered CI classification: **negative**.

