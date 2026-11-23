# QuotaShift attack-effect report — `a8_lifecycle_churn_smoke`

> Live target measurements.

- Control: `lifecycle_normal`  ·  seeds: 2  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **inconclusive** (seeds with metric: 2).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **1.60×**  (median 1.60×, 95% bootstrap CI [0.38, 2.82])
- **Attack success rate: 50%** of 2 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 2098 tokens, 7 requests per run.
- Victim slowdown per 1k competing tokens: 0.2861
- Victim slowdown per 100 competing requests: 8.5739

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 516.73 | 183.19 | 2.82 | yes | 0/0 |
| 43 | 131.12 | 345.43 | 0.38 | no | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | True/False |
| 43 | control→attack | 0.000 | 0.000 | True/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 6765 | 4900 | 3550 | 2.32 | 70.98 | 21.87 | n/a | 0.013 | 0 | False |
| control | 42 | 6765 | 4900 | 4480 | 2.45 | 92.58 | 22.60 | n/a | 0.017 | 0 | False |
| attack | 43 | 7919 | 5193 | 3622 | 2.18 | 71.76 | 21.60 | n/a | 0.019 | 0 | False |
| control | 43 | 7919 | 5193 | 5347 | 3.15 | 112.32 | 22.74 | n/a | 0.024 | 0 | False |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.
Pre-registered CI classification: **inconclusive**.

