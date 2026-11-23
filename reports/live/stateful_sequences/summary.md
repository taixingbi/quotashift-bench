# QuotaShift attack-effect report — `a5_stateful_sequence`

> Live target measurements.

- Control: `shuffled_phase_order`  ·  seeds: 5  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **1.28×**  (median 1.39×, 95% bootstrap CI [1.08, 1.46])
- **Attack success rate: 20%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 27630 tokens, 56 requests per run.
- Victim slowdown per 1k competing tokens: 0.0101
- Victim slowdown per 100 competing requests: 0.4960

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 211.17 | 136.71 | 1.54 | yes | 0/0 |
| 43 | 193.94 | 168.98 | 1.15 | no | 0/0 |
| 44 | 186.49 | 134.40 | 1.39 | no | 0/0 |
| 45 | 193.85 | 137.41 | 1.41 | no | 0/0 |
| 46 | 187.03 | 205.99 | 0.91 | no | 0/0 |

## Verdict

Under matched budgets, the effect does NOT reach the pre-registered threshold on a majority of runs (reported as a negative result, per the plan).

