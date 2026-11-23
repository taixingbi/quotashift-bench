# QuotaShift attack-effect report — `a1_burst_arrivals`

> Live target measurements.

- Control: `uniform_arrivals`  ·  seeds: 20  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **1.59×**  (median 1.58×, 95% bootstrap CI [1.53, 1.65])
- **Attack success rate: 70%** of 20 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 14147 tokens, 108 requests per run.
- Victim slowdown per 1k competing tokens: 0.0417
- Victim slowdown per 100 competing requests: 0.5469

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 136.45 | 83.84 | 1.63 | yes | 0/0 |
| 43 | 139.33 | 85.36 | 1.63 | yes | 0/0 |
| 44 | 124.68 | 82.99 | 1.50 | yes | 0/0 |
| 45 | 123.70 | 85.62 | 1.44 | no | 0/0 |
| 46 | 124.98 | 87.22 | 1.43 | no | 0/0 |
| 47 | 124.56 | 87.12 | 1.43 | no | 0/0 |
| 48 | 132.09 | 90.20 | 1.46 | no | 0/0 |
| 49 | 141.61 | 84.02 | 1.69 | yes | 0/0 |
| 50 | 139.39 | 84.19 | 1.66 | yes | 0/0 |
| 51 | 123.97 | 82.94 | 1.49 | no | 0/0 |
| 52 | 152.51 | 81.25 | 1.88 | yes | 0/0 |
| 53 | 129.27 | 84.20 | 1.54 | yes | 0/0 |
| 54 | 127.99 | 83.96 | 1.52 | yes | 0/0 |
| 55 | 130.64 | 83.16 | 1.57 | yes | 0/0 |
| 56 | 122.39 | 89.03 | 1.37 | no | 0/0 |
| 57 | 162.30 | 84.24 | 1.93 | yes | 0/0 |
| 58 | 138.96 | 86.59 | 1.60 | yes | 0/0 |
| 59 | 155.90 | 89.72 | 1.74 | yes | 0/0 |
| 60 | 137.87 | 86.32 | 1.60 | yes | 0/0 |
| 61 | 136.30 | 81.18 | 1.68 | yes | 0/0 |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.

