# QuotaShift attack-effect report — `a7_prefix_cache_smoke`

> Live target measurements.

- Control: `prefix_unique`  ·  seeds: 2  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **inconclusive** (seeds with metric: 2).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.74×**  (median 0.74×, 95% bootstrap CI [0.57, 0.91])
- **Attack success rate: 50%** of 2 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 9726 tokens, 10 requests per run.
- Victim slowdown per 1k competing tokens: -0.0265
- Victim slowdown per 100 competing requests: -2.5809

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 215.67 | 237.02 | 0.91 | no | 0/0 |
| 43 | 200.88 | 350.03 | 0.57 | yes | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.516 | 0.232 | False/False |
| 43 | control→attack | 0.552 | 0.185 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 17862 | 8826 | 3584 | 3.16 | 77.76 | 20.45 | n/a | 0.032 | 0 | False |
| control | 42 | 17862 | 14010 | 3584 | 4.29 | 82.77 | 20.45 | n/a | 0.044 | 0 | False |
| attack | 43 | 21966 | 10293 | 3712 | 3.83 | 83.79 | 19.32 | n/a | 0.042 | 0 | False |
| control | 43 | 21966 | 18725 | 3712 | 5.69 | 92.97 | 19.87 | n/a | 0.050 | 0 | False |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.
Pre-registered CI classification: **inconclusive**.

