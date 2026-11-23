# QuotaShift attack-effect report — `v4_smoke_r1_prefill_vs_short`

> Live target measurements.

- Control: `token_matched_fixed`  ·  seeds: 1  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **insufficient_seeds** (seeds with metric: 1).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **1.50×**  (median 1.50×, 95% bootstrap CI [1.50, 1.50])
- **Threshold-crossing rate: 100%** of 1 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 8448 tokens, 8 requests per run.
- Victim slowdown per 1k competing tokens: 0.0594
- Victim slowdown per 100 competing requests: 6.2685

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 900 | 182.34 | 121.44 | 1.50 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 900 | 34 | 34 | 0 | 0 | 0 | 0 | 1.000 | 182.3 | 182.3 | 0.0 | 1590.9 |
| control | 900 | 34 | 34 | 0 | 0 | 0 | 0 | 1.000 | 121.4 | 121.4 | 0.0 | 1431.1 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.501 | [1.501, 1.501] | insufficient_seeds |
| Victim user-facing TTFT P95 | ms | 1.501 | [1.501, 1.501] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 1.112 | [1.112, 1.112] | insufficient_seeds |
| Victim offered-load SLO success | fraction of offered | 1.000 | [1.000, 1.000] | insufficient_seeds |
| Absolute GPU Dynamic Energy per Arm | J per arm | 0.882 | [0.882, 0.882] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.882 | [0.882, 0.882] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.882 | [0.882, 0.882] | insufficient_seeds |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.894 | [0.894, 0.894] | insufficient_seeds |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.393 | [0.393, 0.393] | insufficient_seeds |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 900 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 900 | 13070 | 13070 | 10638 | 2432 | 3.54 | 49.12 | 30.96 | 9558.3 | 11644.2 | 269.1 | 0.018 | 0 | False |
| control | 900 | 13070 | 13070 | 6670 | 6400 | 5.16 | 128.96 | 38.62 | 10838.3 | 13018.4 | 296.7 | 0.010 | 0 | False |

### Per-request prefix-cache hits (reported-only; null = missing, not 0)

| arm | seed | victim coverage | victim hit ratio | competitor hit ratio |
|---|---|---|---|---|
| attack | 900 | 1.000 | 0.000 | 0.000 |
| control | 900 | 1.000 | 0.000 | 0.000 |

### Validity gates (fail closed; ADR-Q17)

Overall: **PASS**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | pass | lowest arm 1.000 (min 0.95) |
| primary_metric_present | pass | 1/1 seeds have a finite Victim user-facing TTFT P95 |
| tokenized_context | pass | max completed prompt+max_output 1056.0 <= 4096; pre-run check ok |
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 142/142 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 46e37f686c25, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.204 (max 0.25), earliest last arrival 0.988 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **insufficient_seeds**.

