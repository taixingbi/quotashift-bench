# QuotaShift attack-effect report — `a9_rate_prefill`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/v3/a9_rate_prefill/.

- Control: `rate_matched_short`  ·  seeds: 5  ·  pre-registered metric: **GPU Dynamic Energy per 1,000 Authorized Tokens** (`gpu_energy_per_1k_authorized_tokens`, unit: J per 1,000 authorized tokens)
- Definition: arm-window GPU dynamic energy (board power minus pre-arm idle) / (planned input + requested output tokens of all requests in the arm / 1000)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **supported** (seeds with metric: 5).

## GPU Dynamic Energy per 1,000 Authorized Tokens: attack vs matched control

- Mean attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens: **0.29×**  (median 0.29×, 95% bootstrap CI [0.28, 0.30])
- **Threshold-crossing rate: 100%** of 5 seeds crossed the threshold.

### Per-seed detail (matched pairs; values in J per 1,000 authorized tokens)

| seed | attack (J per 1,000 authorized tokens) | control (J per 1,000 authorized tokens) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 416.09 | 1456.25 | 0.29 | yes | 0/0 |
| 43 | 408.69 | 1308.77 | 0.31 | yes | 0/0 |
| 44 | 380.12 | 1276.89 | 0.30 | yes | 0/0 |
| 45 | 353.93 | 1302.84 | 0.27 | yes | 0/0 |
| 46 | 347.97 | 1255.73 | 0.28 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 486.5 | 486.5 | 0.0 | 2949.2 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 151.8 | 151.8 | 0.0 | 1483.4 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 553.1 | 494.4 | 0.0 | 3113.7 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 314.7 | 314.7 | 0.0 | 1675.1 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 557.3 | 481.9 | 69.9 | 2900.4 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 178.5 | 165.4 | 0.0 | 1580.0 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 748.8 | 651.7 | 111.4 | 3319.7 |
| control | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 153.2 | 146.5 | 0.0 | 1512.1 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 734.4 | 728.4 | 0.0 | 2878.6 |
| control | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 144.2 | 144.2 | 0.0 | 1507.7 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 3.437 | [2.376, 4.502] | supported |
| Victim user-facing TTFT P95 | ms | 3.612 | [2.576, 4.657] | supported |
| Victim end-to-end latency P95 | ms | 1.957 | [1.860, 2.082] | supported |
| Victim offered-load SLO success | fraction of offered | 1.000 | [1.000, 1.000] | negative |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.289 | [0.277, 0.302] | supported |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.236 | [0.225, 0.248] | supported |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.288 | [0.275, 0.301] | supported |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.331 | [0.324, 0.340] | supported |

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
| attack | 42 | 75302 | 145115 | 136699 | 8416 | 38.50 | 220.09 | 94.57 | 31332.6 | 33520.9 | 297.3 | 0.163 | 0 | False |
| control | 42 | 21097 | 33124 | 22628 | 10496 | 11.01 | 214.46 | 97.82 | 30722.4 | 32889.8 | 290.2 | 0.014 | 0 | False |
| attack | 43 | 76924 | 147762 | 138610 | 9152 | 39.95 | 247.35 | 96.00 | 31438.4 | 33588.2 | 293.8 | 0.138 | 2 | False |
| control | 43 | 23047 | 36364 | 25100 | 11264 | 12.32 | 233.71 | 99.71 | 30163.2 | 32280.7 | 285.2 | 0.021 | 0 | False |
| attack | 44 | 86889 | 167772 | 158268 | 9504 | 45.65 | 253.08 | 102.29 | 33027.9 | 35134.1 | 306.4 | 0.141 | 2 | False |
| control | 44 | 24698 | 39163 | 27259 | 11904 | 13.06 | 245.91 | 105.81 | 31536.5 | 33734.2 | 295.9 | 0.019 | 0 | False |
| attack | 45 | 94770 | 183685 | 174181 | 9504 | 53.41 | 277.27 | 100.41 | 33541.9 | 35704.0 | 308.3 | 0.185 | 2 | False |
| control | 45 | 24653 | 38776 | 26552 | 12224 | 13.05 | 252.52 | 105.63 | 32119.0 | 34446.0 | 298.5 | 0.015 | 0 | False |
| attack | 46 | 94407 | 182527 | 172543 | 9984 | 51.96 | 283.04 | 103.84 | 32850.4 | 34949.6 | 306.5 | 0.139 | 1 | False |
| control | 46 | 25500 | 40121 | 27513 | 12608 | 13.87 | 260.63 | 106.37 | 32021.2 | 34226.4 | 297.7 | 0.018 | 0 | False |

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

Overall: **FAIL**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | pass | lowest arm 1.000 (min 0.95) |
| primary_metric_present | pass | 5/5 seeds have a finite GPU Dynamic Energy per 1,000 Authorized Tokens |
| tokenized_context | FAIL | no pre-run tokenization check recorded |
| provenance | FAIL | dirty ['True']; model revision status not recorded |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); secondary latency endpoints only |

## Verdict

Under matched budgets, the attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens crosses the pre-registered threshold on a majority of seeds (a cost-per-unit difference, not a victim-performance effect).
Pre-registered CI classification: **supported**.

