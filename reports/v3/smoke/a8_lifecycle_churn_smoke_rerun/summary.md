# QuotaShift attack-effect report — `a8_lifecycle_churn_smoke`

> Live target measurements.

- Control: `lifecycle_normal`  ·  seeds: 2  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **negative** (seeds with metric: 2).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.91×**  (median 0.91×, 95% bootstrap CI [0.85, 0.97])
- **Attack success rate: 0%** of 2 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 2098 tokens, 7 requests per run.
- Victim slowdown per 1k competing tokens: -0.0444
- Victim slowdown per 100 competing requests: -1.3308

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 162.18 | 167.98 | 0.97 | no | 0/0 |
| 43 | 133.91 | 157.88 | 0.85 | no | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 6765 | 4900 | 3551 | 2.24 | 70.31 | 21.87 | n/a | 0.016 | 0 | False |
| control | 42 | 6765 | 4900 | 4480 | 2.50 | 92.27 | 22.18 | n/a | 0.019 | 0 | False |
| attack | 43 | 7919 | 5193 | 3622 | 2.14 | 71.72 | 21.59 | n/a | 0.018 | 0 | False |
| control | 43 | 7919 | 5193 | 5341 | 2.76 | 112.06 | 22.75 | n/a | 0.023 | 0 | False |

## Verdict

Under matched budgets, the effect does NOT reach the pre-registered threshold on a majority of runs (reported as a negative result, per the plan).
Pre-registered CI classification: **negative**.

