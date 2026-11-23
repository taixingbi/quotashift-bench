# QuotaShift attack-effect report — `a7v_cache_isolation_validation_smoke`

> Live target measurements.

- Control: `identical_workload`  ·  seeds: 2  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **negative** (seeds with metric: 2).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.97×**  (median 0.97×, 95% bootstrap CI [0.96, 0.99])
- **Attack success rate: 0%** of 2 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 9726 tokens, 10 requests per run.
- Victim slowdown per 1k competing tokens: -0.0026
- Victim slowdown per 100 competing requests: -0.2574

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 303.96 | 317.09 | 0.96 | no | 0/0 |
| 43 | 717.36 | 724.68 | 0.99 | no | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 17862 | 29175 | 3584 | 7.67 | 95.57 | 20.73 | n/a | 0.083 | 0 | False |
| control | 42 | 17862 | 29175 | 3584 | 7.90 | 96.37 | 21.18 | n/a | 0.083 | 0 | False |
| attack | 43 | 21966 | 37207 | 3712 | 11.70 | 112.82 | 21.09 | n/a | 0.083 | 1 | False |
| control | 43 | 21966 | 37207 | 3712 | 11.27 | 112.92 | 21.30 | n/a | 0.082 | 0 | False |

## Verdict

Under matched budgets, the effect does NOT reach the pre-registered threshold on a majority of runs (reported as a negative result, per the plan).
Pre-registered CI classification: **negative**.

