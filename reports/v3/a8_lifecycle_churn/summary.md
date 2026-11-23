# QuotaShift attack-effect report — `a8_lifecycle_churn`

> Live target measurements.

- Control: `lifecycle_normal`  ·  seeds: 5  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **negative** (seeds with metric: 5).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.98×**  (median 0.98×, 95% bootstrap CI [0.87, 1.06])
- **Attack success rate: 0%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 8525 tokens, 29 requests per run.
- Victim slowdown per 1k competing tokens: -0.0029
- Victim slowdown per 100 competing requests: -0.0862

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 129.58 | 133.10 | 0.97 | no | 0/0 |
| 43 | 135.95 | 170.63 | 0.80 | no | 0/0 |
| 44 | 151.41 | 153.77 | 0.98 | no | 0/0 |
| 45 | 136.50 | 136.57 | 1.00 | no | 0/0 |
| 46 | 144.59 | 128.84 | 1.12 | no | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |
| 45 | control→attack | 0.000 | 0.000 | False/False |
| 46 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 32709 | 20860 | 13132 | 8.29 | 249.71 | 89.56 | 25164.2 | 0.017 | 0 | False |
| control | 42 | 32709 | 20860 | 22591 | 10.86 | 472.40 | 94.94 | 26530.8 | 0.028 | 0 | False |
| attack | 43 | 34815 | 23282 | 14117 | 9.35 | 274.65 | 87.89 | 24765.4 | 0.027 | 0 | False |
| control | 43 | 34815 | 23282 | 23412 | 12.12 | 494.30 | 91.59 | 25710.6 | 0.031 | 0 | False |
| attack | 44 | 38084 | 25205 | 15246 | 9.79 | 296.50 | 90.13 | 25175.0 | 0.025 | 0 | False |
| control | 44 | 38084 | 25205 | 25876 | 12.76 | 549.84 | 91.34 | 25464.8 | 0.032 | 0 | False |
| attack | 45 | 39890 | 24350 | 16740 | 9.20 | 324.63 | 91.94 | 25818.3 | 0.031 | 0 | False |
| control | 45 | 39890 | 24350 | 27857 | 12.64 | 587.84 | 95.16 | 26509.5 | 0.031 | 0 | False |
| attack | 46 | 40033 | 25063 | 16388 | 10.12 | 317.53 | 90.53 | 25449.3 | 0.026 | 0 | False |
| control | 46 | 40033 | 25063 | 27540 | 13.31 | 583.16 | 93.62 | 26194.7 | 0.030 | 0 | False |

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

## Verdict

Under matched budgets, the effect does NOT reach the pre-registered threshold on a majority of runs (reported as a negative result, per the plan).
Pre-registered CI classification: **negative**.

