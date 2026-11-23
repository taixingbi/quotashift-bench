# QuotaShift attack-effect report — `a9_tok_prefill_smoke`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 1  ·  degradation metric: `gpu_energy_per_1k_authorized_tokens`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 1).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **1.44×**  (median 1.44×, 95% bootstrap CI [1.44, 1.44])
- **Attack success rate: 100%** of 1 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 7604 tokens, 8 requests per run.
- Victim slowdown per 1k competing tokens: 0.0582
- Victim slowdown per 100 competing requests: 5.5311

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 427.70 | 296.50 | 1.44 | yes | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.989 | 0.946 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 10004 | 188 | 1408 | 0.99 | 27.40 | 12.45 | 4278.7 | 0.051 | 0 | False |
| control | 42 | 9952 | 578 | 4928 | 3.11 | 97.62 | 15.03 | 2950.8 | 0.021 | 0 | False |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.
Pre-registered CI classification: **insufficient_seeds**.

