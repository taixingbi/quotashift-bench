# QuotaShift attack-effect report — `a7_prefix_cache_smoke`

> Live target measurements.

- Control: `prefix_unique`  ·  seeds: 1  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 1).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.84×**  (median 0.84×, 95% bootstrap CI [0.84, 0.84])
- **Attack success rate: 0%** of 1 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 7604 tokens, 8 requests per run.
- Victim slowdown per 1k competing tokens: -0.0206
- Victim slowdown per 100 competing requests: -1.9618

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 228.95 | 271.57 | 0.84 | no | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.516 | 0.232 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 17862 | 8826 | 3584 | 3.22 | 76.94 | 19.13 | 5653.8 | 0.047 | 0 | False |
| control | 42 | 17862 | 14010 | 3584 | 4.30 | 82.12 | 20.40 | 5677.9 | 0.064 | 0 | False |

### Per-request prefix-cache hits (reported-only; null = missing, not 0)

| arm | seed | victim coverage | victim hit ratio | competitor hit ratio |
|---|---|---|---|---|
| attack | 42 | 1.000 | 0.452 | 0.585 |
| control | 42 | 1.000 | 0.452 | 0.000 |

## Verdict

Under matched budgets, the effect does NOT reach the pre-registered threshold on a majority of runs (reported as a negative result, per the plan).
Pre-registered CI classification: **insufficient_seeds**.

