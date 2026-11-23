# QuotaShift attack-effect report — `a2_sweep_in768`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 5  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **3.00×**  (median 2.78×, 95% bootstrap CI [2.53, 3.47])
- **Attack success rate: 100%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 27794 tokens, 38 requests per run.
- Victim slowdown per 1k competing tokens: 0.0719
- Victim slowdown per 100 competing requests: 5.2065

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 521.31 | 148.99 | 3.50 | yes | 0/0 |
| 43 | 413.95 | 148.93 | 2.78 | yes | 0/1 |
| 44 | 368.46 | 143.78 | 2.56 | yes | 0/1 |
| 45 | 340.53 | 89.76 | 3.79 | yes | 0/0 |
| 46 | 189.46 | 80.22 | 2.36 | yes | 0/0 |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.

