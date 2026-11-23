# QuotaShift attack-effect report — `a9_tok_prefill`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 5  ·  degradation metric: `gpu_energy_per_1k_authorized_tokens`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **negative** (seeds with metric: 5).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.90×**  (median 0.91×, 95% bootstrap CI [0.89, 0.92])
- **Attack success rate: 0%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 71408 tokens, 75 requests per run.
- Victim slowdown per 1k competing tokens: -0.0014
- Victim slowdown per 100 competing requests: -0.1293

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 414.18 | 450.96 | 0.92 | no | 0/0 |
| 43 | 406.96 | 443.88 | 0.92 | no | 0/0 |
| 44 | 377.93 | 428.86 | 0.88 | no | 0/2 |
| 45 | 350.45 | 392.06 | 0.89 | no | 0/3 |
| 46 | 352.65 | 388.61 | 0.91 | no | 0/7 |

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
| attack | 42 | 75302 | 136699 | 8416 | 39.01 | 218.92 | 93.71 | 31188.9 | 0.160 | 0 | False |
| control | 42 | 75241 | 79949 | 37568 | 73.39 | 838.63 | 119.83 | 33930.5 | 0.022 | 0 | False |
| attack | 43 | 76924 | 138610 | 9152 | 42.75 | 246.56 | 97.95 | 31304.7 | 0.136 | 0 | False |
| control | 43 | 76935 | 82165 | 38208 | 88.37 | 829.01 | 119.95 | 34149.8 | 0.022 | 0 | False |
| attack | 44 | 86889 | 158268 | 9504 | 46.26 | 254.42 | 99.96 | 32838.4 | 0.141 | 2 | False |
| control | 44 | 86906 | 89824 | 41381 | 65.56 | 949.42 | 130.82 | 37270.8 | 0.023 | 0 | False |
| attack | 45 | 94770 | 174181 | 9504 | 56.11 | 277.44 | 102.07 | 33212.6 | 0.184 | 2 | False |
| control | 45 | 94797 | 89353 | 41920 | 112.49 | 885.83 | 129.82 | 37165.9 | 0.023 | 0 | False |
| attack | 46 | 94407 | 172543 | 9984 | 51.31 | 284.00 | 104.52 | 33292.4 | 0.139 | 0 | False |
| control | 46 | 94364 | 87048 | 40640 | 97.84 | 878.61 | 126.98 | 36670.7 | 0.023 | 0 | False |

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

