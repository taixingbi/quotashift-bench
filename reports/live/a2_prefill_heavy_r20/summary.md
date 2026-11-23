# QuotaShift attack-effect report — `a2_prefill_heavy`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 20  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **3.19×**  (median 2.83×, 95% bootstrap CI [2.66, 3.75])
- **Attack success rate: 95%** of 20 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 36474 tokens, 38 requests per run.
- Victim slowdown per 1k competing tokens: 0.0601
- Victim slowdown per 100 competing requests: 5.7292

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 427.05 | 168.69 | 2.53 | yes | 0/6 |
| 43 | 501.74 | 129.02 | 3.89 | yes | 0/2 |
| 44 | 560.53 | 112.06 | 5.00 | yes | 0/5 |
| 45 | 229.50 | 129.41 | 1.77 | yes | 0/0 |
| 46 | 296.76 | 108.74 | 2.73 | yes | 0/2 |
| 47 | 786.92 | 160.68 | 4.90 | yes | 0/7 |
| 48 | 574.67 | 156.98 | 3.66 | yes | 0/0 |
| 49 | 601.03 | 389.54 | 1.54 | yes | 0/4 |
| 50 | 507.66 | 120.92 | 4.20 | yes | 0/7 |
| 51 | 489.35 | 199.48 | 2.45 | yes | 0/5 |
| 52 | 513.12 | 118.12 | 4.34 | yes | 0/5 |
| 53 | 465.91 | 81.63 | 5.71 | yes | 0/2 |
| 54 | 408.86 | 117.31 | 3.49 | yes | 0/3 |
| 55 | 379.46 | 152.95 | 2.48 | yes | 0/4 |
| 56 | 469.48 | 110.43 | 4.25 | yes | 0/2 |
| 57 | 647.43 | 367.82 | 1.76 | yes | 0/1 |
| 58 | 237.88 | 114.85 | 2.07 | yes | 0/0 |
| 59 | 474.54 | 162.96 | 2.91 | yes | 0/3 |
| 60 | 448.77 | 163.67 | 2.74 | yes | 0/10 |
| 61 | 828.91 | 593.72 | 1.40 | no | 0/2 |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.

