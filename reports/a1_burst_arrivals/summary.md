# QuotaShift attack-effect report — `a1_burst_arrivals`

> **Synthetic backend (mock): plumbing evidence only, not a GPU measurement.**

- Control: `uniform_arrivals`  ·  seeds: 5  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **0.98×**  (median 0.98×, 95% bootstrap CI [0.97, 1.00])
- **Attack success rate: 0%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 11746 tokens, 102 requests per run.
- Victim slowdown per 1k competing tokens: -0.0015
- Victim slowdown per 100 competing requests: -0.0178

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 8.34 | 8.47 | 0.98 | no | 0/0 |
| 43 | 8.63 | 8.81 | 0.98 | no | 0/0 |
| 44 | 8.32 | 8.31 | 1.00 | no | 0/0 |
| 45 | 7.98 | 8.02 | 0.99 | no | 0/0 |
| 46 | 7.75 | 8.16 | 0.95 | no | 0/0 |

## Verdict

Under matched budgets, the effect does NOT reach the pre-registered threshold on a majority of runs (reported as a negative result, per the plan).

