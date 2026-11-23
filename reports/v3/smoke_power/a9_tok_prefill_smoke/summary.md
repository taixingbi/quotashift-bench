# QuotaShift attack-effect report — `a9_tok_prefill_smoke`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 1  ·  degradation metric: `gpu_energy_per_1k_authorized_tokens`
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **supported** (seeds with metric: 1).

## Victim degradation (attack vs matched control)

- Mean victim slowdown ratio: **3.12×**  (median 3.12×, 95% bootstrap CI [3.12, 3.12])
- **Attack success rate: 100%** of 1 runs crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 7604 tokens, 8 requests per run.
- Victim slowdown per 1k competing tokens: 0.2786
- Victim slowdown per 100 competing requests: 26.4779

### Per-seed detail (matched pairs)

| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 443.62 | 142.27 | 3.12 | yes | 0/0 |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 10004 | 17628 | 1408 | 4.76 | 32.37 | 13.59 | 4438.0 | 0.061 | 0 | False |
| control | 42 | 9952 | 10674 | 4928 | 5.97 | 111.91 | 16.10 | 1415.8 | 0.022 | 0 | False |

## Verdict

Under matched budgets, the effect crosses the pre-registered threshold on a majority of runs.
Pre-registered CI classification: **supported**.

