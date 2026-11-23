# QuotaShift attack-effect report — `a8_retry_churn_smoke`

> Live target measurements.

- Control: `lifecycle_normal`  ·  seeds: 2  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **negative** (seeds with metric: 2).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **1.05×**  (median 1.05×, 95% bootstrap CI [1.01, 1.09])
- **Attack success rate: 0%** of 2 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 3912 tokens, 13 requests per run.
- Victim slowdown per 1k competing tokens: 0.0135
- Victim slowdown per 100 competing requests: 0.4074

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 135.04 | 133.12 | 1.01 | no | 0/0 |
| 43 | 148.35 | 135.91 | 1.09 | no | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.112 | 0.112 | False/False |
| 43 | control→attack | 0.097 | 0.097 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 8611 | 4939 | 4661 | 2.41 | 90.93 | 23.12 | n/a | 0.019 | 0 | False |
| control | 42 | 8611 | 4939 | 5939 | 2.80 | 123.65 | 23.63 | n/a | 0.020 | 0 | False |
| attack | 43 | 9735 | 5235 | 5752 | 2.58 | 115.31 | 22.83 | n/a | 0.022 | 0 | False |
| control | 43 | 9735 | 5235 | 6584 | 3.09 | 138.23 | 23.11 | n/a | 0.022 | 0 | False |

## Verdict

Under matched budgets, the effect does NOT reach the pre-registered threshold on a majority of runs (reported as a negative result, per the plan).
Pre-registered CI classification: **negative**.

