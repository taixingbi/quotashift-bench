# QuotaShift attack-effect report — `a1_burst_arrivals`

> Live target measurements.

- Control: `uniform_arrivals`  ·  seeds: 5  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **1.58×**  (median 1.51×, 95% bootstrap CI [1.45, 1.79])
- **Attack success rate: 60%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 13322 tokens, 102 requests per run.
- Victim slowdown per 1k competing tokens: 0.0437
- Victim slowdown per 100 competing requests: 0.5725

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 127.20 | 87.52 | 1.45 | no | 0/0 |
| 43 | 145.67 | 95.56 | 1.52 | yes | 0/0 |
| 44 | 143.87 | 100.88 | 1.43 | no | 0/0 |
| 45 | 168.01 | 84.28 | 1.99 | yes | 0/0 |
| 46 | 124.10 | 82.13 | 1.51 | yes | 0/0 |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.

