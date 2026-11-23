# QuotaShift attack-effect report — `a9_tok_prefill_smoke`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 2  ·  degradation metric: `gpu_energy_per_1k_authorized_tokens`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **unavailable** (seeds with metric: 0).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **n/a×**  (median n/a×, 95% bootstrap CI [n/a, n/a])
- **Attack success rate: 0%** of 2 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 9726 tokens, 10 requests per run.
- Victim slowdown per 1k competing tokens: n/a
- Victim slowdown per 100 competing requests: n/a

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | n/a | n/a | n/a | no | 0/0 |
| 43 | n/a | n/a | n/a | no | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 10004 | 17628 | 1408 | 4.71 | 33.05 | 13.87 | n/a | 0.047 | 0 | False |
| control | 42 | 9952 | 10674 | 4928 | 5.79 | 113.55 | 17.76 | n/a | 0.015 | 0 | False |
| attack | 43 | 13947 | 25439 | 1472 | 7.87 | 41.04 | 14.47 | n/a | 0.085 | 0 | False |
| control | 43 | 14004 | 14772 | 7040 | 9.08 | 160.09 | 22.20 | n/a | 0.017 | 0 | False |

## Verdict

Under matched budgets, the effect does NOT reach the pre-registered threshold on a majority of runs (reported as a negative result, per the plan).
Pre-registered CI classification: **unavailable**.

