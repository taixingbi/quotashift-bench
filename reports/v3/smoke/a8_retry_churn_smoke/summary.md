# QuotaShift attack-effect report — `a8_retry_churn_smoke`

> Live target measurements.

- Control: `lifecycle_normal`  ·  seeds: 2  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **negative** (seeds with metric: 2).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.82×**  (median 0.82×, 95% bootstrap CI [0.78, 0.86])
- **Attack success rate: 0%** of 2 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 3912 tokens, 13 requests per run.
- Victim slowdown per 1k competing tokens: -0.0452
- Victim slowdown per 100 competing requests: -1.3589

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 145.20 | 185.13 | 0.78 | no | 0/0 |
| 43 | 134.98 | 156.51 | 0.86 | no | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.112 | 0.112 | True/False |
| 43 | control→attack | 0.097 | 0.097 | True/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 8611 | 4939 | 4661 | 2.39 | 90.94 | 23.18 | n/a | 0.019 | 0 | False |
| control | 42 | 8611 | 4939 | 5939 | 2.82 | 123.87 | 23.52 | n/a | 0.020 | 0 | False |
| attack | 43 | 9735 | 5235 | 5752 | 2.59 | 115.35 | 22.83 | n/a | 0.022 | 0 | False |
| control | 43 | 9735 | 5235 | 6584 | 3.17 | 138.05 | 23.25 | n/a | 0.023 | 0 | False |

## Verdict

Under matched budgets, the effect does NOT reach the pre-registered threshold on a majority of runs (reported as a negative result, per the plan).
Pre-registered CI classification: **negative**.

