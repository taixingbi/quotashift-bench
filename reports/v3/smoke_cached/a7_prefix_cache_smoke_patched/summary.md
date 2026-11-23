# QuotaShift attack-effect report — `a7_prefix_cache_smoke`

> Live target measurements.

- Control: `prefix_unique`  ·  seeds: 1  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 1).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **1.03×**  (median 1.03×, 95% bootstrap CI [1.03, 1.03])
- **Attack success rate: 0%** of 1 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 7604 tokens, 8 requests per run.
- Victim slowdown per 1k competing tokens: 0.0042
- Victim slowdown per 100 competing requests: 0.3990

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 285.11 | 276.29 | 1.03 | no | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.516 | 0.232 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 17862 | 8826 | 3584 | 3.43 | 76.99 | 20.51 | 5747.8 | 0.041 | 0 | False |
| control | 42 | 17862 | 14010 | 3584 | 4.39 | 82.15 | 20.45 | 5579.4 | 0.064 | 0 | False |

### Per-request prefix-cache hits (reported-only; null = missing, not 0)

| arm | seed | victim coverage | victim hit ratio | competitor hit ratio |
|---|---|---|---|---|
| attack | 42 | 0.885 | 0.520 | 0.686 |
| control | 42 | 0.885 | 0.520 | n/a |

## Verdict

Under matched budgets, the effect does NOT reach the pre-registered threshold on a majority of runs (reported as a negative result, per the plan).
Pre-registered CI classification: **insufficient_seeds**.

