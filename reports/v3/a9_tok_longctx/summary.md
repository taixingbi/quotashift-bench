# QuotaShift attack-effect report — `a9_tok_longctx`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 5  ·  degradation metric: `gpu_energy_per_1k_authorized_tokens`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **inconclusive** (seeds with metric: 5).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.78×**  (median 0.77×, 95% bootstrap CI [0.76, 0.81])
- **Attack success rate: 60%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 1394 tokens, 1 requests per run.
- Victim slowdown per 1k competing tokens: -0.1553
- Victim slowdown per 100 competing requests: -27.0496

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 416.78 | 508.70 | 0.82 | no | 0/0 |
| 43 | 355.96 | 435.86 | 0.82 | no | 0/0 |
| 44 | 301.23 | 400.30 | 0.75 | yes | 0/8 |
| 45 | 238.69 | 314.78 | 0.76 | yes | 0/12 |
| 46 | 239.15 | 310.08 | 0.77 | yes | 0/16 |

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
| attack | 42 | 64689 | 13820 | 6336 | 6.08 | 126.75 | 75.09 | 26960.8 | 0.009 | 0 | False |
| control | 42 | 64745 | 68852 | 32320 | 40.79 | 745.95 | 113.78 | 32935.8 | 0.021 | 0 | False |
| attack | 43 | 77811 | 21625 | 7552 | 8.25 | 155.33 | 80.19 | 27697.4 | 0.048 | 0 | False |
| control | 43 | 77831 | 83113 | 38656 | 75.04 | 858.82 | 120.87 | 33923.2 | 0.022 | 0 | False |
| attack | 44 | 93032 | 20180 | 7360 | 8.00 | 149.84 | 86.12 | 28024.4 | 0.051 | 0 | False |
| control | 44 | 93050 | 91678 | 42304 | 113.15 | 899.11 | 131.02 | 37248.2 | 0.024 | 0 | False |
| attack | 45 | 118240 | 18562 | 7040 | 7.30 | 143.26 | 81.22 | 28222.4 | 0.058 | 0 | False |
| control | 45 | 118221 | 90577 | 42496 | 110.44 | 903.85 | 131.07 | 37213.8 | 0.023 | 0 | False |
| attack | 46 | 119770 | 16368 | 7360 | 7.25 | 148.22 | 84.00 | 28643.5 | 0.011 | 0 | False |
| control | 46 | 119708 | 89232 | 41792 | 95.51 | 904.99 | 129.95 | 37119.4 | 0.022 | 0 | False |

### Per-request prefix-cache hits (reported-only; null = missing, not 0)

| arm | seed | victim coverage | victim hit ratio | competitor hit ratio |
|---|---|---|---|---|
| attack | 42 | 1.000 | 0.000 | n/a |
| control | 42 | 1.000 | 0.000 | 0.000 |
| attack | 43 | 1.000 | 0.000 | 0.000 |
| control | 43 | 1.000 | 0.000 | 0.000 |
| attack | 44 | 1.000 | 0.000 | 0.000 |
| control | 44 | 1.000 | 0.000 | 0.000 |
| attack | 45 | 1.000 | 0.000 | 0.000 |
| control | 45 | 1.000 | 0.000 | 0.000 |
| attack | 46 | 1.000 | 0.000 | n/a |
| control | 46 | 1.000 | 0.000 | 0.000 |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.
Pre-registered CI classification: **inconclusive**.

