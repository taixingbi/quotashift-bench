# QuotaShift attack-effect report — `a9_rate_longctx`

> Live target measurements.

- Control: `rate_matched_short`  ·  seeds: 5  ·  degradation metric: `gpu_energy_per_1k_authorized_tokens`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **supported** (seeds with metric: 5).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.18×**  (median 0.18×, 95% bootstrap CI [0.15, 0.21])
- **Attack success rate: 100%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 1394 tokens, 1 requests per run.
- Victim slowdown per 1k competing tokens: -0.5873
- Victim slowdown per 100 competing requests: -102.3218

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 416.69 | 1905.96 | 0.22 | yes | 0/0 |
| 43 | 357.72 | 1649.66 | 0.22 | yes | 0/0 |
| 44 | 301.51 | 1684.20 | 0.18 | yes | 0/0 |
| 45 | 237.30 | 1651.37 | 0.14 | yes | 0/0 |
| 46 | 238.15 | 1598.95 | 0.15 | yes | 0/0 |

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
| attack | 42 | 64689 | 13820 | 6336 | 6.04 | 126.76 | 72.70 | 26955.1 | 0.010 | 0 | False |
| control | 42 | 14697 | 15858 | 7296 | 7.28 | 146.88 | 80.43 | 28012.0 | 0.012 | 0 | False |
| attack | 43 | 77811 | 21625 | 7552 | 8.25 | 155.19 | 82.12 | 27834.4 | 0.047 | 0 | False |
| control | 43 | 17031 | 18765 | 8256 | 8.56 | 168.37 | 84.49 | 28095.3 | 0.021 | 0 | False |
| attack | 44 | 93032 | 20180 | 7360 | 8.05 | 149.65 | 80.85 | 28050.1 | 0.050 | 0 | False |
| control | 44 | 17914 | 20067 | 8512 | 8.87 | 173.66 | 90.78 | 30170.8 | 0.021 | 0 | False |
| attack | 45 | 118240 | 18562 | 7040 | 7.56 | 143.21 | 80.93 | 28058.5 | 0.059 | 0 | False |
| control | 45 | 17613 | 19086 | 8704 | 8.78 | 176.75 | 86.23 | 29085.6 | 0.016 | 0 | False |
| attack | 46 | 119770 | 16368 | 7360 | 7.12 | 148.35 | 82.88 | 28523.0 | 0.011 | 0 | False |
| control | 46 | 18844 | 20448 | 9280 | 9.53 | 188.10 | 91.75 | 30130.7 | 0.013 | 0 | False |

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
Pre-registered CI classification: **supported**.

