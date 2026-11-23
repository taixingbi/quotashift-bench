# QuotaShift attack-effect report — `a4_mixed_shapes`

> Live target measurements.

- Control: `homogeneous_mixture`  ·  seeds: 5  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **1.35×**  (median 1.26×, 95% bootstrap CI [1.23, 1.47])
- **Attack success rate: 20%** of 5 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 14074 tokens, 35 requests per run.
- Victim slowdown per 1k competing tokens: 0.0246
- Victim slowdown per 100 competing requests: 0.9800

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 154.73 | 128.98 | 1.20 | no | 0/0 |
| 43 | 189.01 | 150.70 | 1.25 | no | 0/0 |
| 44 | 181.83 | 117.36 | 1.55 | yes | 0/0 |
| 45 | 183.68 | 145.68 | 1.26 | no | 0/0 |
| 46 | 163.37 | 111.09 | 1.47 | no | 0/0 |

## Verdict

Under matched budgets, the effect does NOT reach the pre-registered threshold on a majority of runs (reported as a negative result, per the plan).

