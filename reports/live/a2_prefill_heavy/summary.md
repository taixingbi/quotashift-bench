# QuotaShift attack-effect report — `a2_prefill_heavy`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 5  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **3.16×**  (median 3.14×, 95% bootstrap CI [2.37, 3.94])
- **Attack success rate: 100%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 33882 tokens, 35 requests per run.
- Victim slowdown per 1k competing tokens: 0.0637
- Victim slowdown per 100 competing requests: 6.0950

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 518.97 | 119.03 | 4.36 | yes | 0/3 |
| 43 | 424.55 | 149.54 | 2.84 | yes | 0/2 |
| 44 | 555.33 | 177.09 | 3.14 | yes | 0/3 |
| 45 | 195.74 | 116.62 | 1.68 | yes | 0/0 |
| 46 | 458.75 | 121.53 | 3.77 | yes | 0/2 |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.

