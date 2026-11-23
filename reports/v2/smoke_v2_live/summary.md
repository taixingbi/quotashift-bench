# QuotaShift attack-effect report — `smoke_v2_live`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 2  ·  degradation metric: `ttft_p95`
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **1.52×**  (median 1.52×, 95% bootstrap CI [0.72, 2.31])
- **Attack success rate: 50%** of 2 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 4353 tokens, 8 requests per run.
- Victim slowdown per 1k competing tokens: 0.1184
- Victim slowdown per 100 competing requests: 6.0611

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 125.58 | 173.95 | 0.72 | no | 0/0 |
| 43 | 318.80 | 138.10 | 2.31 | yes | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.

