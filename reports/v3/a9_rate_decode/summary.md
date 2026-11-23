# QuotaShift attack-effect report — `a9_rate_decode`

> Live target measurements.

- Control: `rate_matched_short`  ·  seeds: 5  ·  degradation metric: `gpu_energy_per_1k_authorized_tokens`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **supported** (seeds with metric: 5).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.62×**  (median 0.63×, 95% bootstrap CI [0.61, 0.64])
- **Attack success rate: 100%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 36555 tokens, 123 requests per run.
- Victim slowdown per 1k competing tokens: -0.0103
- Victim slowdown per 100 competing requests: -0.3063

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 743.45 | 1164.84 | 0.64 | yes | 0/0 |
| 43 | 683.67 | 1068.65 | 0.64 | yes | 0/0 |
| 44 | 683.38 | 1086.13 | 0.63 | yes | 0/0 |
| 45 | 639.05 | 1056.00 | 0.61 | yes | 0/0 |
| 46 | 615.34 | 1013.78 | 0.61 | yes | 0/0 |

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
| attack | 42 | 45978 | 25703 | 33529 | 13.58 | 702.43 | 122.25 | 34182.5 | 0.033 | 0 | False |
| control | 42 | 26601 | 28461 | 13248 | 14.61 | 274.90 | 106.10 | 30985.8 | 0.017 | 0 | False |
| attack | 43 | 51993 | 29347 | 36868 | 15.45 | 776.31 | 126.33 | 35545.9 | 0.031 | 0 | False |
| control | 43 | 30215 | 32687 | 14848 | 16.53 | 311.87 | 106.80 | 32289.3 | 0.020 | 0 | False |
| attack | 44 | 50391 | 29637 | 35458 | 15.30 | 749.05 | 121.97 | 34436.1 | 0.031 | 0 | False |
| control | 44 | 29818 | 32697 | 14464 | 16.83 | 303.77 | 109.66 | 32386.4 | 0.023 | 0 | False |
| attack | 45 | 54987 | 29821 | 40115 | 15.89 | 845.43 | 124.43 | 35139.4 | 0.032 | 0 | False |
| control | 45 | 30925 | 33197 | 15360 | 17.11 | 322.94 | 112.10 | 32656.9 | 0.019 | 0 | False |
| attack | 46 | 56119 | 30467 | 40396 | 16.44 | 852.54 | 122.73 | 34532.3 | 0.031 | 0 | False |
| control | 46 | 32284 | 34706 | 16000 | 17.99 | 335.91 | 113.94 | 32728.9 | 0.020 | 0 | False |

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

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.
Pre-registered CI classification: **supported**.

