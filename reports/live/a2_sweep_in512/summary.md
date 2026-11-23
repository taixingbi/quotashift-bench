# QuotaShift attack-effect report — `a2_sweep_in512`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 5  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **2.14×**  (median 2.03×, 95% bootstrap CI [1.62, 2.69])
- **Attack success rate: 80%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 27879 tokens, 57 requests per run.
- Victim slowdown per 1k competing tokens: 0.0408
- Victim slowdown per 100 competing requests: 2.0116

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 196.59 | 128.52 | 1.53 | yes | 0/0 |
| 43 | 290.03 | 142.53 | 2.03 | yes | 0/2 |
| 44 | 266.90 | 106.98 | 2.49 | yes | 0/0 |
| 45 | 230.12 | 154.38 | 1.49 | no | 0/0 |
| 46 | 316.19 | 100.61 | 3.14 | yes | 0/0 |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.

