# QuotaShift attack-effect report — `a9_rate_prefill`

> Live target measurements.

- Control: `rate_matched_short`  ·  seeds: 5  ·  degradation metric: `gpu_energy_per_1k_authorized_tokens`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **supported** (seeds with metric: 5).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.29×**  (median 0.29×, 95% bootstrap CI [0.28, 0.30])
- **Attack success rate: 100%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 71408 tokens, 75 requests per run.
- Victim slowdown per 1k competing tokens: -0.0100
- Victim slowdown per 100 competing requests: -0.9532

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 416.09 | 1456.25 | 0.29 | yes | 0/0 |
| 43 | 408.69 | 1308.77 | 0.31 | yes | 0/0 |
| 44 | 380.12 | 1276.89 | 0.30 | yes | 0/0 |
| 45 | 353.93 | 1302.84 | 0.27 | yes | 0/0 |
| 46 | 347.97 | 1255.73 | 0.28 | yes | 0/0 |

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
| attack | 42 | 75302 | 136699 | 8416 | 38.50 | 220.09 | 94.57 | 31332.6 | 0.163 | 0 | False |
| control | 42 | 21097 | 22628 | 10496 | 11.01 | 214.46 | 97.82 | 30722.4 | 0.014 | 0 | False |
| attack | 43 | 76924 | 138610 | 9152 | 39.95 | 247.35 | 96.00 | 31438.4 | 0.138 | 2 | False |
| control | 43 | 23047 | 25100 | 11264 | 12.32 | 233.71 | 99.71 | 30163.2 | 0.021 | 0 | False |
| attack | 44 | 86889 | 158268 | 9504 | 45.65 | 253.08 | 102.29 | 33027.9 | 0.141 | 2 | False |
| control | 44 | 24698 | 27259 | 11904 | 13.06 | 245.91 | 105.81 | 31536.5 | 0.019 | 0 | False |
| attack | 45 | 94770 | 174181 | 9504 | 53.41 | 277.27 | 100.41 | 33541.9 | 0.185 | 2 | False |
| control | 45 | 24653 | 26552 | 12224 | 13.05 | 252.52 | 105.63 | 32119.0 | 0.015 | 0 | False |
| attack | 46 | 94407 | 172543 | 9984 | 51.96 | 283.04 | 103.84 | 32850.4 | 0.139 | 1 | False |
| control | 46 | 25500 | 27513 | 12608 | 13.87 | 260.63 | 106.37 | 32021.2 | 0.018 | 0 | False |

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

