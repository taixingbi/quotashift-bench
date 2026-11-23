# QuotaShift attack-effect report — `v4_r1_prefill_vs_short_L200`

> Live target measurements.

- Control: `token_matched_fixed`  ·  seeds: 5  ·  pre-registered metric: **Victim user-facing TTFT P95** (`user_ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_offered (includes gateway queue)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **negative** (seeds with metric: 5).

## Victim user-facing TTFT P95: victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim user-facing TTFT P95: **1.05×**  (median 1.09×, 95% bootstrap CI [0.88, 1.22])
- **Threshold-crossing rate: 40%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 24288 tokens, 23 requests per run.
- Victim slowdown per 1k competing tokens: 0.0019
- Victim slowdown per 100 competing requests: 0.2038

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 184.06 | 168.81 | 1.09 | no | 0/0 |
| 43 | 164.70 | 213.30 | 0.77 | yes | 0/0 |
| 44 | 186.80 | 213.02 | 0.88 | no | 0/0 |
| 45 | 193.21 | 157.58 | 1.23 | no | 0/0 |
| 46 | 221.26 | 174.37 | 1.27 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 184.1 | 184.1 | 0.0 | 1647.1 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 168.8 | 167.7 | 0.0 | 1482.4 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 164.7 | 164.7 | 0.0 | 1672.1 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 213.3 | 160.0 | 80.5 | 1532.2 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 186.8 | 186.8 | 0.0 | 1595.6 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 213.0 | 175.7 | 77.4 | 1526.3 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 193.2 | 193.2 | 0.0 | 1587.9 |
| control | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 157.6 | 156.6 | 0.0 | 1463.2 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 221.3 | 221.3 | 0.0 | 1722.5 |
| control | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 174.4 | 170.7 | 0.0 | 1484.4 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.144 | [1.057, 1.237] | negative |
| Victim user-facing TTFT P95 | ms | 1.047 | [0.878, 1.216] | negative |
| Victim gateway queue time P95 | ms | 0.000 | [0.000, 0.000] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 1.099 | [1.067, 1.132] | negative |
| Victim offered-load SLO success | fraction of offered | 1.000 | [1.000, 1.000] | negative |
| Absolute GPU Dynamic Energy per Arm | J per arm | 0.882 | [0.869, 0.894] | negative |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.883 | [0.870, 0.895] | negative |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.883 | [0.870, 0.895] | negative |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.889 | [0.878, 0.901] | negative |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.418 | [0.407, 0.428] | supported |

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
| attack | 42 | 37067 | 37067 | 29995 | 7072 | 9.89 | 145.04 | 82.44 | 28520.8 | 30694.1 | 275.9 | 0.029 | 0 | False |
| control | 42 | 37099 | 37099 | 18603 | 18496 | 14.69 | 374.48 | 114.91 | 32613.5 | 34809.4 | 305.1 | 0.011 | 0 | False |
| attack | 43 | 38887 | 38887 | 31111 | 7776 | 10.24 | 160.74 | 87.11 | 28761.5 | 30830.6 | 272.4 | 0.043 | 0 | False |
| control | 43 | 38919 | 38919 | 19719 | 19200 | 15.54 | 390.33 | 111.05 | 32628.1 | 34885.8 | 305.7 | 0.012 | 0 | False |
| attack | 44 | 39390 | 39390 | 31550 | 7840 | 10.82 | 160.44 | 86.60 | 29472.6 | 31657.9 | 277.9 | 0.031 | 0 | False |
| control | 44 | 39422 | 39422 | 20158 | 19264 | 15.65 | 391.99 | 113.12 | 32886.3 | 35037.5 | 305.2 | 0.013 | 0 | False |
| attack | 45 | 38061 | 38061 | 30541 | 7520 | 10.11 | 154.29 | 82.99 | 28513.3 | 30676.6 | 273.5 | 0.043 | 0 | False |
| control | 45 | 38093 | 38093 | 19149 | 18944 | 14.89 | 383.36 | 117.86 | 33215.4 | 35331.4 | 307.5 | 0.011 | 0 | False |
| attack | 46 | 39292 | 39292 | 31196 | 8096 | 11.00 | 168.17 | 87.82 | 29716.5 | 31912.4 | 278.5 | 0.045 | 0 | False |
| control | 46 | 39324 | 39324 | 19804 | 19520 | 15.79 | 396.63 | 113.78 | 33066.6 | 35283.9 | 306.5 | 0.012 | 0 | False |

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
| provenance | pass | sha 05ae0ed77433, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |
| arrival_coverage | pass | latest first arrival 0.191 (max 0.25), earliest last arrival 0.947 (min 0.75) of the window |
| realized_output_equals_authorized | pass | 0 completed request(s) with output_tokens != max_output_tokens |

## Verdict

Under matched budgets, the victim degradation does NOT reach the pre-registered threshold on a majority of seeds (reported as a negative result, per the plan).
Pre-registered CI classification: **negative**.

