# QuotaShift attack-effect report — `a9_rate_prefix_reuse`

> Live target measurements.

- Control: `rate_matched_short`  ·  seeds: 5  ·  degradation metric: `gpu_energy_per_1k_authorized_tokens`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **supported** (seeds with metric: 5).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.27×**  (median 0.27×, 95% bootstrap CI [0.26, 0.29])
- **Attack success rate: 100%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 71408 tokens, 75 requests per run.
- Victim slowdown per 1k competing tokens: -0.0102
- Victim slowdown per 100 competing requests: -0.9753

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 394.49 | 1455.23 | 0.27 | yes | 0/0 |
| 43 | 387.69 | 1314.63 | 0.29 | yes | 0/0 |
| 44 | 355.75 | 1280.79 | 0.28 | yes | 0/0 |
| 45 | 328.68 | 1295.80 | 0.25 | yes | 0/0 |
| 46 | 329.82 | 1246.63 | 0.26 | yes | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.547 | 0.000 | False/False |
| 43 | control→attack | 0.536 | 0.000 | False/False |
| 44 | attack→control | 0.549 | 0.000 | False/False |
| 45 | control→attack | 0.567 | 0.000 | False/False |
| 46 | attack→control | 0.558 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 75302 | 39496 | 8416 | 14.90 | 176.10 | 87.61 | 29706.2 | 0.033 | 0 | False |
| control | 42 | 21097 | 22628 | 10496 | 11.07 | 214.21 | 94.24 | 30701.1 | 0.014 | 0 | False |
| attack | 43 | 76924 | 41266 | 9152 | 15.32 | 196.22 | 90.19 | 29822.4 | 0.044 | 0 | False |
| control | 43 | 23047 | 25100 | 11264 | 11.99 | 233.37 | 97.97 | 30298.3 | 0.019 | 0 | False |
| attack | 44 | 86889 | 45504 | 9504 | 17.01 | 202.60 | 97.17 | 30910.6 | 0.035 | 0 | False |
| control | 44 | 24698 | 27259 | 11904 | 13.24 | 245.64 | 104.43 | 31633.0 | 0.021 | 0 | False |
| attack | 45 | 94770 | 47532 | 9504 | 17.52 | 205.65 | 97.04 | 31148.9 | 0.038 | 0 | False |
| control | 45 | 24653 | 26552 | 12224 | 12.95 | 252.20 | 104.95 | 31945.3 | 0.018 | 0 | False |
| attack | 46 | 94407 | 48265 | 9984 | 19.00 | 213.92 | 95.73 | 31136.8 | 0.034 | 0 | False |
| control | 46 | 25500 | 27513 | 12608 | 13.86 | 260.58 | 102.94 | 31789.2 | 0.016 | 0 | False |

### Per-request prefix-cache hits (reported-only; null = missing, not 0)

| arm | seed | victim coverage | victim hit ratio | competitor hit ratio |
|---|---|---|---|---|
| attack | 42 | 1.000 | 0.000 | 0.650 |
| control | 42 | 1.000 | 0.000 | 0.000 |
| attack | 43 | 1.000 | 0.000 | 0.656 |
| control | 43 | 1.000 | 0.000 | 0.000 |
| attack | 44 | 1.000 | 0.000 | 0.661 |
| control | 44 | 1.000 | 0.000 | 0.000 |
| attack | 45 | 1.000 | 0.000 | 0.657 |
| control | 45 | 1.000 | 0.000 | 0.000 |
| attack | 46 | 1.000 | 0.000 | 0.657 |
| control | 46 | 1.000 | 0.000 | 0.000 |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.
Pre-registered CI classification: **supported**.

