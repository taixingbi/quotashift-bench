# QuotaShift attack-effect report — `a2_sweep_in128`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 5  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **1.73×**  (median 1.93×, 95% bootstrap CI [1.30, 2.05])
- **Attack success rate: 80%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 30222 tokens, 206 requests per run.
- Victim slowdown per 1k competing tokens: 0.0242
- Victim slowdown per 100 competing requests: 0.3554

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 271.80 | 297.34 | 0.91 | no | 0/5 |
| 43 | 230.56 | 111.50 | 2.07 | yes | 0/1 |
| 44 | 156.86 | 81.39 | 1.93 | yes | 0/0 |
| 45 | 181.04 | 109.80 | 1.65 | yes | 0/1 |
| 46 | 173.48 | 82.65 | 2.10 | yes | 0/0 |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.

