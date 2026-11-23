# QuotaShift attack-effect report — `a7_prefix_cache`

> Live target measurements.

- Control: `prefix_unique`  ·  seeds: 5  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **supported** (seeds with metric: 5).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.61×**  (median 0.62×, 95% bootstrap CI [0.56, 0.66])
- **Attack success rate: 100%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 71408 tokens, 75 requests per run.
- Victim slowdown per 1k competing tokens: -0.0055
- Victim slowdown per 100 competing requests: -0.5269

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 218.92 | 379.48 | 0.58 | yes | 0/0 |
| 43 | 233.93 | 374.65 | 0.62 | yes | 0/0 |
| 44 | 228.00 | 326.74 | 0.70 | yes | 0/0 |
| 45 | 227.29 | 369.39 | 0.62 | yes | 0/0 |
| 46 | 201.04 | 386.41 | 0.52 | yes | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.598 | 0.201 | False/False |
| 43 | control→attack | 0.591 | 0.210 | False/False |
| 44 | attack→control | 0.577 | 0.183 | False/False |
| 45 | control→attack | 0.609 | 0.174 | False/False |
| 46 | attack→control | 0.603 | 0.186 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 114681 | 48212 | 19360 | 19.53 | 420.46 | 115.93 | 32826.9 | 0.050 | 0 | False |
| control | 42 | 114681 | 95876 | 19360 | 30.15 | 463.13 | 116.51 | 33885.8 | 0.069 | 0 | False |
| attack | 43 | 119267 | 51129 | 20416 | 20.20 | 452.82 | 113.42 | 32945.2 | 0.055 | 0 | False |
| control | 43 | 119267 | 98873 | 20416 | 31.36 | 501.54 | 114.76 | 33302.3 | 0.092 | 0 | False |
| attack | 44 | 130379 | 59298 | 20576 | 22.39 | 461.15 | 115.75 | 33755.9 | 0.057 | 0 | False |
| control | 44 | 130379 | 114642 | 20576 | 35.00 | 510.98 | 117.02 | 34161.0 | 0.091 | 0 | False |
| attack | 45 | 134502 | 55754 | 20384 | 22.40 | 457.79 | 118.26 | 33893.3 | 0.062 | 0 | False |
| control | 45 | 134502 | 117946 | 20379 | 36.93 | 513.66 | 119.74 | 34609.6 | 0.114 | 0 | False |
| attack | 46 | 137998 | 58167 | 21568 | 23.11 | 487.28 | 119.83 | 34181.4 | 0.058 | 0 | False |
| control | 46 | 137998 | 119191 | 21568 | 37.53 | 552.82 | 120.39 | 34693.0 | 0.088 | 0 | False |

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

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.
Pre-registered CI classification: **supported**.

