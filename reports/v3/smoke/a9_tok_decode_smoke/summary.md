# QuotaShift attack-effect report — `a9_tok_decode_smoke`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 2  ·  degradation metric: `gpu_energy_per_1k_authorized_tokens`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **unavailable** (seeds with metric: 0).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **n/a×**  (median n/a×, 95% bootstrap CI [n/a, n/a])
- **Attack success rate: 0%** of 2 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 4340 tokens, 15 requests per run.
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
| attack | 42 | 6375 | 4068 | 4203 | 1.99 | 86.70 | 21.47 | n/a | 0.019 | 0 | False |
| control | 42 | 6368 | 6879 | 3136 | 3.59 | 67.81 | 16.02 | n/a | 0.016 | 0 | False |
| attack | 43 | 7249 | 3906 | 5273 | 2.15 | 109.85 | 21.60 | n/a | 0.023 | 0 | False |
| control | 43 | 7220 | 7607 | 3648 | 4.43 | 81.04 | 16.58 | n/a | 0.016 | 0 | False |

## Verdict

Under matched budgets, the effect does NOT reach the pre-registered threshold on a majority of runs (reported as a negative result, per the plan).
Pre-registered CI classification: **unavailable**.

