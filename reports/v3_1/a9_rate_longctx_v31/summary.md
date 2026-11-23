# QuotaShift attack-effect report — `a9_rate_longctx_v31`

> Live target measurements.

- Control: `rate_matched_short`  ·  seeds: 5  ·  pre-registered metric: **GPU Dynamic Energy per 1,000 Authorized Tokens** (`gpu_energy_per_1k_authorized_tokens`, unit: J per 1,000 authorized tokens)
- Definition: arm-window GPU dynamic energy (board power minus pre-arm idle) / (planned input + requested output tokens of all requests in the arm / 1000)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **supported** (seeds with metric: 5).

## GPU Dynamic Energy per 1,000 Authorized Tokens: attack vs matched control

- Mean attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens: **0.21×**  (median 0.21×, 95% bootstrap CI [0.19, 0.24])
- **Threshold-crossing rate: 100%** of 5 seeds crossed the threshold.

### Per-seed detail (matched pairs; values in J per 1,000 authorized tokens)

| seed | attack (J per 1,000 authorized tokens) | control (J per 1,000 authorized tokens) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 482.83 | 1870.92 | 0.26 | yes | 0/0 |
| 43 | 395.97 | 1674.68 | 0.24 | yes | 0/0 |
| 44 | 355.69 | 1654.48 | 0.21 | yes | 0/0 |
| 45 | 287.68 | 1646.47 | 0.17 | yes | 0/0 |
| 46 | 287.26 | 1587.83 | 0.18 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 198.4 | 198.4 | 0.0 | 2147.6 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 143.5 | 143.5 | 0.0 | 1400.4 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 817.1 | 238.1 | 252.7 | 2773.1 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 112.5 | 112.5 | 0.0 | 1413.0 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 904.8 | 608.3 | 99.9 | 2779.6 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 165.4 | 165.4 | 0.0 | 1457.3 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 0.962 | 1150.1 | 760.0 | 732.6 | 4025.2 |
| control | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 130.0 | 130.0 | 0.0 | 1405.1 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 623.3 | 623.3 | 0.0 | 2875.9 |
| control | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 134.0 | 134.0 | 0.0 | 1413.8 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 3.534 | [2.135, 4.933] | supported |
| Victim user-facing TTFT P95 | ms | 5.522 | [3.212, 7.537] | supported |
| Victim end-to-end latency P95 | ms | 2.060 | [1.719, 2.493] | supported |
| Victim offered-load SLO success | fraction of offered | 0.992 | [0.977, 1.000] | negative |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.213 | [0.185, 0.241] | supported |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.213 | [0.185, 0.241] | supported |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.211 | [0.183, 0.238] | supported |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.357 | [0.341, 0.373] | supported |

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
| attack | 42 | 64691 | 64496 | 54515 | 9981 | 17.54 | 219.77 | 101.18 | 31234.7 | 33328.4 | 291.1 | 0.144 | 1 | False |
| control | 42 | 14699 | 14699 | 7403 | 7296 | 4.81 | 144.49 | 78.39 | 27500.6 | 29785.2 | 268.2 | 0.006 | 0 | False |
| attack | 43 | 77811 | 77800 | 65907 | 11893 | 21.03 | 279.14 | 101.57 | 30810.8 | 32979.5 | 287.3 | 0.198 | 1 | False |
| control | 43 | 17031 | 17020 | 8775 | 8245 | 5.75 | 164.00 | 85.35 | 28521.5 | 30713.0 | 270.5 | 0.009 | 0 | False |
| attack | 44 | 93036 | 93036 | 80300 | 12736 | 27.60 | 302.38 | 108.63 | 33091.7 | 35131.0 | 302.2 | 0.206 | 0 | False |
| control | 44 | 17918 | 17918 | 9406 | 8512 | 5.88 | 169.44 | 89.73 | 29645.0 | 31875.5 | 281.2 | 0.011 | 0 | False |
| attack | 45 | 118240 | 118240 | 103776 | 14464 | 33.70 | 366.87 | 114.79 | 34014.7 | 36020.1 | 304.9 | 0.329 | 1 | False |
| control | 45 | 17613 | 17613 | 8909 | 8704 | 5.88 | 172.84 | 90.39 | 28999.2 | 31122.5 | 275.3 | 0.008 | 0 | False |
| attack | 46 | 119770 | 119721 | 104730 | 14991 | 34.04 | 377.91 | 116.61 | 34405.7 | 36535.5 | 308.4 | 0.288 | 1 | False |
| control | 46 | 18844 | 18844 | 9564 | 9280 | 6.29 | 184.13 | 92.93 | 29921.1 | 32104.2 | 282.9 | 0.008 | 0 | False |

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
| primary_metric_present | pass | 5/5 seeds have a finite GPU Dynamic Energy per 1,000 Authorized Tokens |
| tokenized_context | pass | max completed prompt+max_output 3840.0 <= 4096; pre-run check ok |
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 1314/1314 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 02448f8cb6ad, clean, server start 1795268683.89 |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); secondary latency endpoints only |

## Verdict

Under matched budgets, the attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens crosses the pre-registered threshold on a majority of seeds (a cost-per-unit difference, not a victim-performance effect).
Pre-registered CI classification: **supported**.

