# QuotaShift attack-effect report — `a8_retry_churn`

> Live target measurements.

- Control: `lifecycle_normal`  ·  seeds: 5  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **negative** (seeds with metric: 5).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **1.12×**  (median 1.18×, 95% bootstrap CI [0.98, 1.23])
- **Attack success rate: 20%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 22223 tokens, 75 requests per run.
- Victim slowdown per 1k competing tokens: 0.0052
- Victim slowdown per 100 competing requests: 0.1550

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 131.47 | 145.50 | 0.90 | no | 0/0 |
| 43 | 179.02 | 137.02 | 1.31 | yes | 0/0 |
| 44 | 174.06 | 147.74 | 1.18 | no | 0/0 |
| 45 | 224.11 | 189.72 | 1.18 | no | 0/0 |
| 46 | 196.13 | 194.47 | 1.01 | no | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.130 | 0.130 | False/False |
| 43 | control→attack | 0.118 | 0.118 | False/False |
| 44 | attack→control | 0.148 | 0.148 | False/False |
| 45 | control→attack | 0.143 | 0.143 | False/False |
| 46 | attack→control | 0.124 | 0.124 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 42786 | 21173 | 24010 | 10.37 | 471.70 | 94.23 | 26495.6 | 0.029 | 0 | False |
| control | 42 | 42786 | 21173 | 30730 | 12.65 | 646.01 | 99.70 | 27705.0 | 0.030 | 0 | False |
| attack | 43 | 44630 | 23568 | 24894 | 11.92 | 496.22 | 92.07 | 25801.6 | 0.032 | 0 | False |
| control | 43 | 44630 | 23568 | 30950 | 13.28 | 654.82 | 92.77 | 26041.7 | 0.030 | 0 | False |
| attack | 44 | 52158 | 25667 | 27436 | 12.20 | 537.90 | 93.12 | 26072.7 | 0.031 | 0 | False |
| control | 44 | 52158 | 25667 | 37170 | 14.69 | 784.80 | 106.31 | 29918.1 | 0.032 | 0 | False |
| attack | 45 | 52503 | 24737 | 29350 | 12.16 | 580.81 | 96.08 | 26760.9 | 0.029 | 0 | False |
| control | 45 | 52503 | 24737 | 37815 | 15.15 | 795.30 | 107.37 | 29870.0 | 0.031 | 0 | False |
| attack | 46 | 51069 | 25373 | 29510 | 13.04 | 590.82 | 94.41 | 26315.5 | 0.031 | 0 | False |
| control | 46 | 51069 | 25373 | 36857 | 15.50 | 777.80 | 105.69 | 29583.5 | 0.030 | 0 | False |

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

## Verdict

Under matched budgets, the effect does NOT reach the pre-registered threshold on a majority of runs (reported as a negative result, per the plan).
Pre-registered CI classification: **negative**.

