# QuotaShift attack-effect report — `a9_tok_decode`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 5  ·  degradation metric: `gpu_energy_per_1k_authorized_tokens`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **negative** (seeds with metric: 5).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **1.10×**  (median 1.09×, 95% bootstrap CI [1.07, 1.13])
- **Attack success rate: 0%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 36725 tokens, 123 requests per run.
- Victim slowdown per 1k competing tokens: 0.0027
- Victim slowdown per 100 competing requests: 0.0803

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 733.91 | 671.74 | 1.09 | no | 0/0 |
| 43 | 683.28 | 610.52 | 1.12 | no | 0/0 |
| 44 | 682.27 | 640.16 | 1.07 | no | 0/0 |
| 45 | 640.45 | 558.15 | 1.15 | no | 0/0 |
| 46 | 607.55 | 568.95 | 1.07 | no | 0/0 |

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
| attack | 42 | 45978 | 25703 | 33286 | 13.80 | 698.48 | 121.11 | 33743.5 | 0.032 | 0 | False |
| control | 42 | 45929 | 48929 | 22912 | 29.14 | 520.86 | 99.85 | 30852.4 | 0.021 | 0 | False |
| attack | 43 | 51993 | 29347 | 37139 | 15.74 | 782.31 | 126.29 | 35525.8 | 0.032 | 0 | False |
| control | 43 | 51975 | 55715 | 25698 | 31.84 | 590.08 | 103.60 | 31731.9 | 0.021 | 0 | False |
| attack | 44 | 50391 | 29637 | 35637 | 15.87 | 753.54 | 121.68 | 34380.5 | 0.032 | 0 | False |
| control | 44 | 50426 | 54514 | 24768 | 33.39 | 562.85 | 108.09 | 32280.8 | 0.023 | 0 | False |
| attack | 45 | 54987 | 29821 | 40247 | 16.49 | 847.65 | 125.25 | 35216.6 | 0.032 | 0 | False |
| control | 45 | 54989 | 58681 | 27392 | 73.27 | 565.77 | 102.37 | 30691.9 | 0.023 | 0 | False |
| attack | 46 | 56119 | 30467 | 40907 | 16.32 | 865.75 | 122.72 | 34095.1 | 0.032 | 0 | False |
| control | 46 | 56092 | 59900 | 27904 | 34.97 | 639.84 | 108.92 | 31913.4 | 0.020 | 0 | False |

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

