# QuotaShift attack-effect report — `a9_rate_longctx`

> Live target measurements.

> **INVALID (Suite S audit): 112/116 attack-arm competitor requests HTTP 400 (context length); superseded by protocol v3.1 a9_rate_longctx_v31.** CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/v3/a9_rate_longctx/.

- Control: `rate_matched_short`  ·  seeds: 5  ·  pre-registered metric: **GPU Dynamic Energy per 1,000 Authorized Tokens** (`gpu_energy_per_1k_authorized_tokens`, unit: J per 1,000 authorized tokens)
- Definition: arm-window GPU dynamic energy (board power minus pre-arm idle) / (planned input + requested output tokens of all requests in the arm / 1000)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **supported** (seeds with metric: 5).

## GPU Dynamic Energy per 1,000 Authorized Tokens: attack vs matched control

- Mean attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens: **0.18×**  (median 0.18×, 95% bootstrap CI [0.15, 0.21])
- **Threshold-crossing rate: 100%** of 5 seeds crossed the threshold.

### Per-seed detail (matched pairs; values in J per 1,000 authorized tokens)

| seed | attack (J per 1,000 authorized tokens) | control (J per 1,000 authorized tokens) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 416.69 | 1905.96 | 0.22 | yes | 0/0 |
| 43 | 357.72 | 1649.66 | 0.22 | yes | 0/0 |
| 44 | 301.51 | 1684.20 | 0.18 | yes | 0/0 |
| 45 | 237.30 | 1651.37 | 0.14 | yes | 0/0 |
| 46 | 238.15 | 1598.95 | 0.15 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 203.4 | 203.4 | 0.0 | 1488.4 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 158.5 | 158.5 | 0.0 | 1488.0 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 155.0 | 155.0 | 0.0 | 1547.4 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 168.7 | 168.7 | 0.0 | 1581.5 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 214.5 | 214.5 | 0.0 | 1574.6 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 158.8 | 156.1 | 0.0 | 1525.7 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 271.0 | 271.0 | 0.0 | 1636.0 |
| control | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 151.4 | 151.4 | 0.0 | 1512.1 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 159.7 | 159.7 | 0.0 | 1473.2 |
| control | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 617.6 | 617.6 | 0.0 | 1771.4 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.125 | [0.668, 1.533] | inconclusive |
| Victim user-facing TTFT P95 | ms | 1.120 | [0.668, 1.527] | inconclusive |
| Victim end-to-end latency P95 | ms | 0.985 | [0.901, 1.049] | negative |
| Victim offered-load SLO success | fraction of offered | 1.000 | [1.000, 1.000] | negative |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.181 | [0.153, 0.210] | supported |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 1.044 | [0.962, 1.126] | negative |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.182 | [0.153, 0.211] | supported |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.162 | [0.131, 0.192] | supported |

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
| attack | 42 | 64689 | 20156 | 13820 | 6336 | 6.04 | 126.76 | 72.70 | 26955.1 | 29187.1 | 264.3 | 0.010 | 0 | False |
| control | 42 | 14697 | 23154 | 15858 | 7296 | 7.28 | 146.88 | 80.43 | 28012.0 | 30115.1 | 271.5 | 0.012 | 0 | False |
| attack | 43 | 77811 | 29177 | 21625 | 7552 | 8.25 | 155.19 | 82.12 | 27834.4 | 30015.1 | 265.3 | 0.047 | 0 | False |
| control | 43 | 17031 | 27021 | 18765 | 8256 | 8.56 | 168.37 | 84.49 | 28095.3 | 30292.8 | 269.2 | 0.021 | 0 | False |
| attack | 44 | 93032 | 27540 | 20180 | 7360 | 8.05 | 149.65 | 80.85 | 28050.1 | 30199.5 | 267.6 | 0.050 | 0 | False |
| control | 44 | 17914 | 28579 | 20067 | 8512 | 8.87 | 173.66 | 90.78 | 30170.8 | 32420.4 | 282.7 | 0.021 | 0 | False |
| attack | 45 | 118240 | 25602 | 18562 | 7040 | 7.56 | 143.21 | 80.93 | 28058.5 | 30165.6 | 268.7 | 0.059 | 0 | False |
| control | 45 | 17613 | 27790 | 19086 | 8704 | 8.78 | 176.75 | 86.23 | 29085.6 | 31162.2 | 277.8 | 0.016 | 0 | False |
| attack | 46 | 119770 | 23728 | 16368 | 7360 | 7.12 | 148.35 | 82.88 | 28523.0 | 30583.5 | 271.6 | 0.011 | 0 | False |
| control | 46 | 18844 | 29728 | 20448 | 9280 | 9.53 | 188.10 | 91.75 | 30130.7 | 32383.5 | 283.3 | 0.013 | 0 | False |

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
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); secondary latency endpoints only |

## Verdict

Under matched budgets, the attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens crosses the pre-registered threshold on a majority of seeds (a cost-per-unit difference, not a victim-performance effect).
Pre-registered CI classification: **supported**.

