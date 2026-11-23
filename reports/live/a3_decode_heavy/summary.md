# QuotaShift attack-effect report — `a3_decode_heavy`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 5  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **1.06×**  (median 1.11×, 95% bootstrap CI [0.87, 1.26])
- **Attack success rate: 0%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 9998 tokens, 35 requests per run.
- Victim slowdown per 1k competing tokens: 0.0062
- Victim slowdown per 100 competing requests: 0.1739

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 134.14 | 154.01 | 0.87 | no | 0/0 |
| 43 | 123.45 | 108.98 | 1.13 | no | 0/0 |
| 44 | 124.05 | 86.39 | 1.44 | no | 0/0 |
| 45 | 124.49 | 164.59 | 0.76 | no | 0/0 |
| 46 | 162.74 | 146.40 | 1.11 | no | 0/0 |

## Verdict

Under matched budgets, the effect does NOT reach the pre-registered threshold on a majority of runs (reported as a negative result, per the plan).

