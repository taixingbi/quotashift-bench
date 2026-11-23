# QuotaShift attack-effect report — `a9_tok_prefill_smoke`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 2  ·  degradation metric: `gpu_energy_per_1k_authorized_tokens`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 2).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.83×**  (median 0.83×, 95% bootstrap CI [0.78, 0.88])
- **Attack success rate: 50%** of 2 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 9726 tokens, 10 requests per run.
- Victim slowdown per 1k competing tokens: -0.0174
- Victim slowdown per 100 competing requests: -1.6933

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 415.94 | 471.89 | 0.88 | no | 0/0 |
| 43 | 342.13 | 438.67 | 0.78 | yes | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.989 | 0.946 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 10004 | 188 | 1408 | 1.04 | 27.42 | 12.36 | 4161.0 | 0.051 | 0 | False |
| control | 42 | 9952 | 578 | 4928 | 3.13 | 97.65 | 15.61 | 4696.3 | 0.021 | 0 | False |
| attack | 43 | 13947 | 25439 | 1472 | 7.77 | 40.58 | 13.57 | 4771.7 | 0.109 | 2 | False |
| control | 43 | 14004 | 14772 | 7040 | 8.62 | 158.99 | 21.89 | 6143.1 | 0.022 | 0 | False |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.
Pre-registered CI classification: **insufficient_seeds**.

