# QuotaShift attack-effect report — `v4_r1_prefill_vs_short_L200_direct`

> Live target measurements.

- Control: `token_matched_fixed`  ·  seeds: 5  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **inconclusive** (seeds with metric: 5).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **1.15×**  (median 1.16×, 95% bootstrap CI [1.06, 1.25])
- **Threshold-crossing rate: 20%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 24288 tokens, 23 requests per run.
- Victim slowdown per 1k competing tokens: 0.0062
- Victim slowdown per 100 competing requests: 0.6544

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 189.98 | 186.48 | 1.02 | no | 0/0 |
| 43 | 191.28 | 182.90 | 1.05 | no | 0/0 |
| 44 | 203.79 | 176.16 | 1.16 | no | 0/0 |
| 45 | 229.70 | 170.62 | 1.35 | yes | 0/0 |
| 46 | 204.46 | 172.55 | 1.18 | no | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 190.0 | 190.0 | 0.0 | 1594.4 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 186.5 | 186.5 | 0.0 | 1498.0 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 191.3 | 191.3 | 0.0 | 1675.9 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 182.9 | 182.9 | 0.0 | 1515.7 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 203.8 | 203.8 | 0.0 | 1637.7 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 176.2 | 176.2 | 0.0 | 1492.2 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 229.7 | 229.7 | 0.0 | 1644.2 |
| control | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 170.6 | 170.6 | 0.0 | 1471.9 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 204.5 | 204.5 | 0.0 | 1698.0 |
| control | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 172.6 | 172.6 | 0.0 | 1490.5 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.151 | [1.057, 1.254] | inconclusive |
| Victim user-facing TTFT P95 | ms | 1.151 | [1.057, 1.254] | inconclusive |
| Victim end-to-end latency P95 | ms | 1.105 | [1.082, 1.126] | negative |
| Victim offered-load SLO success | fraction of offered | 1.000 | [1.000, 1.000] | negative |
| Absolute GPU Dynamic Energy per Arm | J per arm | 0.875 | [0.861, 0.889] | negative |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.876 | [0.862, 0.890] | negative |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.876 | [0.862, 0.890] | negative |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.881 | [0.868, 0.893] | negative |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.417 | [0.406, 0.427] | supported |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.000 | 0.000 | False/False |
| 43 | control→attack | 0.000 | 0.000 | False/False |
| 44 | attack→control | 0.000 | 0.000 | False/False |
| 45 | control→attack | 0.000 | 0.000 | False/False |
| 46 | attack→control | 0.000 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 37067 | 37067 | 29995 | 7072 | 9.97 | 144.86 | 84.47 | 28111.8 | 30281.5 | 272.7 | 0.029 | 0 | False |
| control | 42 | 37099 | 37099 | 18603 | 18496 | 14.77 | 374.75 | 113.80 | 32746.6 | 34925.5 | 305.0 | 0.013 | 0 | False |
| attack | 43 | 38887 | 38887 | 31111 | 7776 | 10.34 | 161.36 | 85.44 | 28630.0 | 30718.7 | 272.0 | 0.031 | 0 | False |
| control | 43 | 38919 | 38919 | 19719 | 19200 | 15.94 | 390.84 | 113.61 | 32615.0 | 34839.1 | 304.4 | 0.015 | 0 | False |
| attack | 44 | 39390 | 39390 | 31550 | 7840 | 10.63 | 160.39 | 87.81 | 29166.2 | 31290.9 | 277.5 | 0.031 | 0 | False |
| control | 44 | 39422 | 39422 | 20158 | 19264 | 15.71 | 392.87 | 113.94 | 32843.8 | 35005.3 | 305.4 | 0.015 | 0 | False |
| attack | 45 | 38061 | 38061 | 30541 | 7520 | 9.92 | 154.97 | 82.70 | 28510.7 | 30669.1 | 272.2 | 0.043 | 0 | False |
| control | 45 | 38093 | 38093 | 19149 | 18944 | 15.09 | 383.32 | 117.46 | 33326.3 | 35599.4 | 307.7 | 0.011 | 0 | False |
| attack | 46 | 39292 | 39292 | 31196 | 8096 | 10.96 | 167.96 | 89.88 | 29626.7 | 31527.3 | 281.4 | 0.044 | 0 | False |
| control | 46 | 39324 | 39324 | 19804 | 19520 | 15.99 | 396.77 | 115.68 | 33101.9 | 35219.6 | 306.5 | 0.013 | 0 | False |

### Per-request prefix-cache hits (reported-only; null = missing, not 0)

| arm | seed | victim coverage | victim hit ratio | competitor hit ratio |
|---|---|---|---|---|
| attack | 42 | 1.000 | 0.000 | 0.000 |
| control | 42 | 1.000 | 0.000 | 0.000 |
| attack | 43 | 1.000 | 0.000 | 0.000 |
| control | 43 | 1.000 | 0.000 | 0.000 |
| attack | 44 | 1.000 | 0.000 | 0.000 |
| control | 44 | 1.000 | 0.000 | 0.000 |
| attack | 45 | 1.000 | 0.000 | 0.000 |
| control | 45 | 1.000 | 0.000 | 0.000 |
| attack | 46 | 1.000 | 0.000 | 0.000 |
| control | 46 | 1.000 | 0.000 | 0.000 |

### Validity gates (fail closed; ADR-Q17)

Overall: **PASS**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | pass | lowest arm 1.000 (min 0.95) |
| primary_metric_present | pass | 5/5 seeds have a finite Victim user-facing TTFT P95 |
| tokenized_context | pass | max completed prompt+max_output 1056.0 <= 4096; pre-run check ok |
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 2147/2147 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 6c5615b0e019, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.191 (max 0.25), earliest last arrival 0.947 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation does NOT reach the pre-registered threshold on a majority of seeds (reported as a negative result, per the plan).
Pre-registered CI classification: **inconclusive**.

