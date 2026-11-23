# QuotaShift attack-effect report — `a9_tok_prefix_reuse`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 5  ·  degradation metric: `gpu_energy_per_1k_authorized_tokens`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **negative** (seeds with metric: 5).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.86×**  (median 0.86×, 95% bootstrap CI [0.84, 0.88])
- **Attack success rate: 0%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 71408 tokens, 75 requests per run.
- Victim slowdown per 1k competing tokens: -0.0020
- Victim slowdown per 100 competing requests: -0.1887

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 394.19 | 449.65 | 0.88 | no | 0/0 |
| 43 | 389.45 | 434.21 | 0.90 | no | 0/0 |
| 44 | 350.96 | 426.54 | 0.82 | no | 0/2 |
| 45 | 329.82 | 391.03 | 0.84 | no | 0/5 |
| 46 | 330.68 | 386.10 | 0.86 | no | 0/6 |

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
| attack | 42 | 75302 | 39496 | 8416 | 14.90 | 176.13 | 88.90 | 29683.1 | 0.032 | 0 | False |
| control | 42 | 75241 | 79949 | 37568 | 45.46 | 874.53 | 118.47 | 33831.9 | 0.022 | 0 | False |
| attack | 43 | 76924 | 41266 | 9152 | 15.24 | 196.21 | 89.15 | 29958.3 | 0.039 | 0 | False |
| control | 43 | 76935 | 82165 | 38208 | 57.70 | 863.60 | 119.93 | 33406.1 | 0.022 | 0 | False |
| attack | 44 | 86889 | 45504 | 9504 | 16.82 | 202.48 | 96.15 | 30494.8 | 0.035 | 0 | False |
| control | 44 | 86906 | 90642 | 41792 | 55.16 | 966.61 | 131.20 | 37069.1 | 0.023 | 0 | False |
| attack | 45 | 94770 | 47532 | 9504 | 17.59 | 205.54 | 94.00 | 31257.4 | 0.038 | 0 | False |
| control | 45 | 94797 | 89328 | 41856 | 76.17 | 916.21 | 130.54 | 37068.5 | 0.023 | 0 | False |
| attack | 46 | 94407 | 48265 | 9984 | 18.46 | 214.13 | 100.64 | 31218.3 | 0.034 | 0 | False |
| control | 46 | 94364 | 87371 | 40896 | 67.36 | 928.16 | 128.29 | 36434.2 | 0.022 | 0 | False |

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

Under matched budgets, the effect does NOT reach the pre-registered threshold on a majority of runs (reported as a negative result, per the plan).
Pre-registered CI classification: **negative**.

