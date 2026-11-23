# QuotaShift attack-effect report — `a9_tok_longctx`

> Live target measurements.

> **INVALID (Suite S audit): 112/116 attack-arm competitor requests HTTP 400 (context length); superseded by protocol v3.1 a9_tok_longctx_v31.** CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/v3/a9_tok_longctx/.

- Control: `matched_total_short`  ·  seeds: 5  ·  pre-registered metric: **GPU Dynamic Energy per 1,000 Authorized Tokens** (`gpu_energy_per_1k_authorized_tokens`, unit: J per 1,000 authorized tokens)
- Definition: arm-window GPU dynamic energy (board power minus pre-arm idle) / (planned input + requested output tokens of all requests in the arm / 1000)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **inconclusive** (seeds with metric: 5).

## GPU Dynamic Energy per 1,000 Authorized Tokens: attack vs matched control

- Mean attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens: **0.78×**  (median 0.77×, 95% bootstrap CI [0.76, 0.81])
- **Threshold-crossing rate: 60%** of 5 seeds crossed the threshold.

### Per-seed detail (matched pairs; values in J per 1,000 authorized tokens)

| seed | attack (J per 1,000 authorized tokens) | control (J per 1,000 authorized tokens) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 416.78 | 508.70 | 0.82 | no | 0/0 |
| 43 | 355.96 | 435.86 | 0.82 | no | 0/0 |
| 44 | 301.23 | 400.30 | 0.75 | yes | 0/8 |
| 45 | 238.69 | 314.78 | 0.76 | yes | 0/12 |
| 46 | 239.15 | 310.08 | 0.77 | yes | 0/16 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 159.5 | 159.5 | 0.0 | 1447.7 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 0.263 | 25646.7 | 178.7 | 25546.7 | 27149.2 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 239.5 | 239.5 | 0.0 | 1676.0 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.018 | 44511.0 | 246.2 | 44281.2 | 45896.9 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 236.6 | 236.6 | 0.0 | 1594.4 |
| control | 44 | 111 | 103 | 0 | 8 | 0 | 0 | 0.000 | 58015.4 | 302.0 | 57764.0 | 59349.0 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 150.9 | 150.9 | 0.0 | 1497.5 |
| control | 45 | 106 | 94 | 0 | 12 | 0 | 0 | 0.019 | 59754.2 | 335.5 | 59609.5 | 61214.9 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 186.9 | 186.9 | 0.0 | 1485.1 |
| control | 46 | 115 | 99 | 0 | 16 | 0 | 0 | 0.000 | 60021.8 | 299.8 | 59764.7 | 61360.9 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 0.744 | [0.573, 0.903] | inconclusive |
| Victim user-facing TTFT P95 | ms | 0.004 | [0.003, 0.005] | supported |
| Victim gateway queue time P95 | ms | 0.000 | [0.000, 0.000] | supported |
| Victim end-to-end latency P95 | ms | 0.033 | [0.025, 0.044] | supported |
| Victim offered-load SLO success | fraction of offered | 37.269 | [3.808, 55.000] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.784 | [0.759, 0.809] | inconclusive |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 3.876 | [3.598, 4.136] | supported |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.795 | [0.770, 0.820] | inconclusive |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.161 | [0.153, 0.170] | supported |

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
| attack | 42 | 64689 | 20156 | 13820 | 6336 | 6.08 | 126.75 | 75.09 | 26960.8 | 29120.3 | 261.3 | 0.009 | 0 | False |
| control | 42 | 64745 | 101172 | 68852 | 32320 | 40.79 | 745.95 | 113.78 | 32935.8 | 35066.6 | 310.7 | 0.021 | 0 | False |
| attack | 43 | 77811 | 29177 | 21625 | 7552 | 8.25 | 155.33 | 80.19 | 27697.4 | 29921.4 | 264.8 | 0.048 | 0 | False |
| control | 43 | 77831 | 121769 | 83113 | 38656 | 75.04 | 858.82 | 120.87 | 33923.2 | 36083.6 | 315.5 | 0.022 | 0 | False |
| attack | 44 | 93032 | 27540 | 20180 | 7360 | 8.00 | 149.84 | 86.12 | 28024.4 | 30189.4 | 267.0 | 0.051 | 0 | False |
| control | 44 | 93050 | 133982 | 91678 | 42304 | 113.15 | 899.11 | 131.02 | 37248.2 | 39472.0 | 316.5 | 0.024 | 0 | False |
| attack | 45 | 118240 | 25602 | 18562 | 7040 | 7.30 | 143.26 | 81.22 | 28222.4 | 30380.2 | 270.4 | 0.058 | 0 | False |
| control | 45 | 118221 | 133073 | 90577 | 42496 | 110.44 | 903.85 | 131.07 | 37213.8 | 39469.3 | 316.0 | 0.023 | 0 | False |
| attack | 46 | 119770 | 23728 | 16368 | 7360 | 7.25 | 148.22 | 84.00 | 28643.5 | 30726.4 | 272.2 | 0.011 | 0 | False |
| control | 46 | 119708 | 131024 | 89232 | 41792 | 95.51 | 904.99 | 129.95 | 37119.4 | 39344.6 | 316.6 | 0.022 | 0 | False |

### Per-request prefix-cache hits (reported-only; null = missing, not 0)

| arm | seed | victim coverage | victim hit ratio | competitor hit ratio |
|---|---|---|---|---|
| attack | 42 | 1.000 | 0.000 | n/a |
| control | 42 | 1.000 | 0.000 | 0.000 |
| attack | 43 | 1.000 | 0.000 | 0.000 |
| control | 43 | 1.000 | 0.000 | 0.000 |
| attack | 44 | 1.000 | 0.000 | 0.000 |
| control | 44 | 1.000 | 0.000 | 0.000 |
| attack | 45 | 1.000 | 0.000 | 0.000 |
| control | 45 | 1.000 | 0.000 | 0.000 |
| attack | 46 | 1.000 | 0.000 | n/a |
| control | 46 | 1.000 | 0.000 | 0.000 |

### Validity gates (fail closed; ADR-Q17)

Overall: **FAIL**

| gate | result | detail |
|---|---|---|
| backend_error_rate | FAIL | worst arm 0.2132 (max 0.01) |
| http_400_rate | FAIL | worst arm 0.2132 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | FAIL | lowest arm 0.000 (min 0.95) |
| primary_metric_present | pass | 5/5 seeds have a finite GPU Dynamic Energy per 1,000 Authorized Tokens |
| tokenized_context | FAIL | no pre-run tokenization check recorded |
| provenance | FAIL | dirty ['True']; model revision status not recorded |
| victim_latency_censoring | FAIL | worst arm censored fraction 0.139 (max 0.05); secondary latency endpoints only |

## Verdict

Under matched budgets, the attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens crosses the pre-registered threshold on a majority of seeds (a cost-per-unit difference, not a victim-performance effect).
Pre-registered CI classification: **inconclusive**.

