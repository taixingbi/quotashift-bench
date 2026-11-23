# QuotaShift attack-effect report — `a7_prefix_cache_reset`

> Live target measurements.

- Control: `prefix_unique`  ·  seeds: 5  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **supported** (seeds with metric: 5).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.62×**  (median 0.61×, 95% bootstrap CI [0.57, 0.67])
- **Attack success rate: 100%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 71408 tokens, 75 requests per run.
- Victim slowdown per 1k competing tokens: -0.0054
- Victim slowdown per 100 competing requests: -0.5157

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 238.14 | 382.59 | 0.62 | yes | 0/0 |
| 43 | 225.66 | 402.90 | 0.56 | yes | 0/0 |
| 44 | 235.59 | 329.85 | 0.71 | yes | 0/0 |
| 45 | 241.61 | 396.10 | 0.61 | yes | 0/0 |
| 46 | 203.66 | 357.36 | 0.57 | yes | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.598 | 0.201 | False/False |
| 43 | control→attack | 0.591 | 0.210 | False/False |
| 44 | attack→control | 0.577 | 0.183 | False/False |
| 45 | control→attack | 0.609 | 0.174 | False/False |
| 46 | attack→control | 0.603 | 0.186 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 114681 | 48212 | 19360 | 19.78 | 422.90 | 115.52 | 33320.6 | 0.050 | 0 | False |
| control | 42 | 114681 | 95876 | 19360 | 31.04 | 463.48 | 116.64 | 33726.4 | 0.069 | 0 | False |
| attack | 43 | 119267 | 51129 | 20416 | 20.36 | 452.99 | 113.60 | 32756.6 | 0.056 | 0 | False |
| control | 43 | 119267 | 98873 | 20416 | 32.32 | 500.23 | 115.13 | 33456.4 | 0.095 | 0 | False |
| attack | 44 | 130379 | 59298 | 20576 | 22.69 | 461.43 | 117.36 | 33654.7 | 0.058 | 0 | False |
| control | 44 | 130379 | 114642 | 20576 | 34.59 | 512.61 | 117.40 | 33200.5 | 0.080 | 0 | False |
| attack | 45 | 134502 | 55754 | 20384 | 22.52 | 457.79 | 117.24 | 33536.0 | 0.062 | 0 | False |
| control | 45 | 134502 | 117946 | 20384 | 37.21 | 515.11 | 118.86 | 34773.6 | 0.100 | 1 | False |
| attack | 46 | 137998 | 58167 | 21568 | 23.04 | 486.99 | 118.93 | 34037.1 | 0.059 | 0 | False |
| control | 46 | 137998 | 119191 | 21568 | 36.04 | 552.17 | 120.43 | 34032.5 | 0.087 | 0 | False |

### Per-request prefix-cache hits (reported-only; null = missing, not 0)

| arm | seed | victim coverage | victim hit ratio | competitor hit ratio |
|---|---|---|---|---|
| attack | 42 | 1.000 | 0.517 | 0.650 |
| control | 42 | 1.000 | 0.517 | 0.000 |
| attack | 43 | 1.000 | 0.502 | 0.656 |
| control | 43 | 1.000 | 0.502 | 0.000 |
| attack | 44 | 1.000 | 0.454 | 0.661 |
| control | 44 | 1.000 | 0.453 | 0.000 |
| attack | 45 | 1.000 | 0.516 | 0.657 |
| control | 45 | 1.000 | 0.516 | 0.000 |
| attack | 46 | 1.000 | 0.509 | 0.657 |
| control | 46 | 1.000 | 0.509 | 0.000 |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.
Pre-registered CI classification: **supported**.

