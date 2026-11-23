# QuotaShift attack-effect report — `a9_rate_prefix_reuse`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/v3/a9_rate_prefix_reuse/.

- Control: `rate_matched_short`  ·  seeds: 5  ·  pre-registered metric: **GPU Dynamic Energy per 1,000 Authorized Tokens** (`gpu_energy_per_1k_authorized_tokens`, unit: J per 1,000 authorized tokens)
- Definition: arm-window GPU dynamic energy (board power minus pre-arm idle) / (planned input + requested output tokens of all requests in the arm / 1000)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **supported** (seeds with metric: 5).

## GPU Dynamic Energy per 1,000 Authorized Tokens: attack vs matched control

- Mean attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens: **0.27×**  (median 0.27×, 95% bootstrap CI [0.26, 0.29])
- **Threshold-crossing rate: 100%** of 5 seeds crossed the threshold.

### Per-seed detail (matched pairs; values in J per 1,000 authorized tokens)

| seed | attack (J per 1,000 authorized tokens) | control (J per 1,000 authorized tokens) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 394.49 | 1455.23 | 0.27 | yes | 0/0 |
| 43 | 387.69 | 1314.63 | 0.29 | yes | 0/0 |
| 44 | 355.75 | 1280.79 | 0.28 | yes | 0/0 |
| 45 | 328.68 | 1295.80 | 0.25 | yes | 0/0 |
| 46 | 329.82 | 1246.63 | 0.26 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 188.1 | 188.1 | 0.0 | 1683.0 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 155.1 | 155.1 | 0.0 | 1498.6 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 177.9 | 177.9 | 0.0 | 1735.1 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 151.2 | 151.2 | 0.0 | 1576.0 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 262.2 | 252.7 | 0.0 | 1768.5 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 203.2 | 181.3 | 0.0 | 1578.5 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 180.2 | 180.2 | 0.0 | 1748.4 |
| control | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 153.2 | 152.0 | 0.0 | 1508.6 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 204.3 | 204.3 | 0.0 | 1679.8 |
| control | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 148.6 | 148.6 | 0.0 | 1514.9 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.269 | [1.187, 1.350] | inconclusive |
| Victim user-facing TTFT P95 | ms | 1.246 | [1.184, 1.318] | inconclusive |
| Victim end-to-end latency P95 | ms | 1.122 | [1.108, 1.142] | negative |
| Victim offered-load SLO success | fraction of offered | 1.000 | [1.000, 1.000] | negative |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.272 | [0.261, 0.285] | supported |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.339 | [0.326, 0.354] | supported |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.272 | [0.261, 0.285] | supported |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.237 | [0.226, 0.249] | supported |

### Per-arm engine prefix-cache hit ratio (engine-global) and arm order

| seed | order | attack hit ratio | control hit ratio | unrelated traffic (a/c) |
|---|---|---|---|---|
| 42 | attack→control | 0.547 | 0.000 | False/False |
| 43 | control→attack | 0.536 | 0.000 | False/False |
| 44 | attack→control | 0.549 | 0.000 | False/False |
| 45 | control→attack | 0.567 | 0.000 | False/False |
| 46 | attack→control | 0.558 | 0.000 | False/False |

### Cost accounting per arm (engine-global; n/a = not measured)

| arm | seed | authorized tok | realized tok | prefill-computed tok | generation tok | engine prefill s | engine decode s | engine busy s | GPU dyn. energy J | GPU dyn. energy incl. tail J | GPU W mean | KV max | waiting max | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 75302 | 95576 | 39496 | 8416 | 14.90 | 176.10 | 87.61 | 29706.2 | 31829.2 | 284.3 | 0.033 | 0 | False |
| control | 42 | 21097 | 33124 | 22628 | 10496 | 11.07 | 214.21 | 94.24 | 30701.1 | 32872.5 | 289.7 | 0.014 | 0 | False |
| attack | 43 | 76924 | 98146 | 41266 | 9152 | 15.32 | 196.22 | 90.19 | 29822.4 | 31968.7 | 280.9 | 0.044 | 0 | False |
| control | 43 | 23047 | 36364 | 25100 | 11264 | 11.99 | 233.37 | 97.97 | 30298.3 | 32499.6 | 287.8 | 0.019 | 0 | False |
| attack | 44 | 86889 | 110336 | 45504 | 9504 | 17.01 | 202.60 | 97.17 | 30910.6 | 33084.4 | 289.0 | 0.035 | 0 | False |
| control | 44 | 24698 | 39163 | 27259 | 11904 | 13.24 | 245.64 | 104.43 | 31633.0 | 33911.5 | 296.3 | 0.021 | 0 | False |
| attack | 45 | 94770 | 119228 | 47532 | 9504 | 17.52 | 205.65 | 97.04 | 31148.9 | 33378.9 | 291.5 | 0.038 | 0 | False |
| control | 45 | 24653 | 38776 | 26552 | 12224 | 12.95 | 252.20 | 104.95 | 31945.3 | 34183.7 | 297.0 | 0.018 | 0 | False |
| attack | 46 | 94407 | 119273 | 48265 | 9984 | 19.00 | 213.92 | 95.73 | 31136.8 | 33331.5 | 291.8 | 0.034 | 0 | False |
| control | 46 | 25500 | 40121 | 27513 | 12608 | 13.86 | 260.58 | 102.94 | 31789.2 | 34028.0 | 297.1 | 0.016 | 0 | False |

### Per-request prefix-cache hits (reported-only; null = missing, not 0)

| arm | seed | victim coverage | victim hit ratio | competitor hit ratio |
|---|---|---|---|---|
| attack | 42 | 1.000 | 0.000 | 0.650 |
| control | 42 | 1.000 | 0.000 | 0.000 |
| attack | 43 | 1.000 | 0.000 | 0.656 |
| control | 43 | 1.000 | 0.000 | 0.000 |
| attack | 44 | 1.000 | 0.000 | 0.661 |
| control | 44 | 1.000 | 0.000 | 0.000 |
| attack | 45 | 1.000 | 0.000 | 0.657 |
| control | 45 | 1.000 | 0.000 | 0.000 |
| attack | 46 | 1.000 | 0.000 | 0.657 |
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

