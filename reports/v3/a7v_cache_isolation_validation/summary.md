# QuotaShift attack-effect report — `a7v_cache_isolation_validation`

> Live target measurements.

- Control: `identical_workload`  ·  seeds: 5  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **negative** (seeds with metric: 5).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.96×**  (median 0.95×, 95% bootstrap CI [0.92, 1.01])
- **Attack success rate: 0%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 71408 tokens, 75 requests per run.
- Victim slowdown per 1k competing tokens: -0.0005
- Victim slowdown per 100 competing requests: -0.0511

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 553.63 | 545.84 | 1.01 | no | 0/0 |
| 43 | 601.70 | 661.70 | 0.91 | no | 0/0 |
| 44 | 495.04 | 521.53 | 0.95 | no | 0/0 |
| 45 | 692.26 | 674.99 | 1.03 | no | 0/0 |
| 46 | 634.48 | 696.44 | 0.91 | no | 0/0 |

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
| attack | 42 | 114681 | 194575 | 19360 | 52.48 | 577.44 | 121.09 | 35332.9 | 0.129 | 1 | False |
| control | 42 | 114681 | 194575 | 19360 | 53.34 | 579.43 | 121.67 | 35773.6 | 0.138 | 1 | False |
| attack | 43 | 119267 | 201830 | 20416 | 58.22 | 638.63 | 116.03 | 34305.3 | 0.146 | 1 | False |
| control | 43 | 119267 | 201830 | 20416 | 58.86 | 636.95 | 116.22 | 34706.8 | 0.146 | 1 | False |
| attack | 44 | 130379 | 224219 | 20576 | 61.48 | 665.28 | 118.81 | 35024.7 | 0.141 | 1 | False |
| control | 44 | 130379 | 224219 | 20576 | 62.22 | 663.30 | 118.90 | 35452.8 | 0.141 | 1 | False |
| attack | 45 | 134502 | 232902 | 20384 | 67.65 | 671.74 | 122.07 | 36018.8 | 0.154 | 1 | False |
| control | 45 | 134502 | 232902 | 20384 | 68.54 | 669.27 | 122.37 | 36110.0 | 0.154 | 0 | False |
| attack | 46 | 137998 | 237691 | 21568 | 67.30 | 727.20 | 120.43 | 35586.6 | 0.145 | 1 | False |
| control | 46 | 137998 | 237691 | 21568 | 73.41 | 716.90 | 120.87 | 35665.2 | 0.145 | 0 | False |

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

