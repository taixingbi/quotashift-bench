# QuotaShift attack-effect report — `a2_sweep_in256`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 5  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **2.22×**  (median 2.22×, 95% bootstrap CI [1.54, 2.90])
- **Attack success rate: 60%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 29374 tokens, 112 requests per run.
- Victim slowdown per 1k competing tokens: 0.0416
- Victim slowdown per 100 competing requests: 1.0923

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 175.82 | 127.73 | 1.38 | no | 0/0 |
| 43 | 201.73 | 148.46 | 1.36 | no | 0/2 |
| 44 | 277.70 | 81.88 | 3.39 | yes | 0/0 |
| 45 | 252.91 | 114.02 | 2.22 | yes | 0/2 |
| 46 | 229.05 | 82.95 | 2.76 | yes | 0/0 |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.

