# QuotaShift attack-effect report — `a9_tok_prefix_reuse`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/v3/a9_tok_prefix_reuse/.

- Control: `matched_total_short`  ·  seeds: 5  ·  pre-registered metric: **GPU Dynamic Energy per 1,000 Authorized Tokens** (`gpu_energy_per_1k_authorized_tokens`, unit: J per 1,000 authorized tokens)
- Definition: arm-window GPU dynamic energy (board power minus pre-arm idle) / (planned input + requested output tokens of all requests in the arm / 1000)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **negative** (seeds with metric: 5).

## GPU Dynamic Energy per 1,000 Authorized Tokens: attack vs matched control

- Mean attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens: **0.86×**  (median 0.86×, 95% bootstrap CI [0.84, 0.88])
- **Threshold-crossing rate: 0%** of 5 seeds crossed the threshold.

### Per-seed detail (matched pairs; values in J per 1,000 authorized tokens)

| seed | attack (J per 1,000 authorized tokens) | control (J per 1,000 authorized tokens) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 394.19 | 449.65 | 0.88 | no | 0/0 |
| 43 | 389.45 | 434.21 | 0.90 | no | 0/0 |
| 44 | 350.96 | 426.54 | 0.82 | no | 0/2 |
| 45 | 329.82 | 391.03 | 0.84 | no | 0/5 |
| 46 | 330.68 | 386.10 | 0.86 | no | 0/6 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 206.4 | 206.4 | 0.0 | 1638.1 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 0.081 | 43190.7 | 158.5 | 43071.3 | 44670.6 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 166.9 | 166.9 | 0.0 | 1711.3 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.018 | 43308.9 | 229.2 | 43065.5 | 44676.8 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 189.4 | 180.0 | 0.0 | 1690.9 |
| control | 44 | 111 | 109 | 0 | 2 | 0 | 0 | 0.000 | 57343.2 | 184.2 | 57248.5 | 58845.3 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 153.5 | 153.5 | 0.0 | 1756.8 |
| control | 45 | 106 | 101 | 0 | 5 | 0 | 0 | 0.028 | 58339.3 | 269.5 | 58106.9 | 59666.7 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 195.6 | 195.6 | 0.0 | 1670.6 |
| control | 46 | 115 | 109 | 0 | 6 | 0 | 0 | 0.000 | 59258.7 | 231.9 | 59077.8 | 60704.2 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 0.884 | [0.683, 1.119] | inconclusive |
| Victim user-facing TTFT P95 | ms | 0.004 | [0.003, 0.004] | supported |
| Victim gateway queue time P95 | ms | 0.000 | [0.000, 0.000] | supported |
| Victim end-to-end latency P95 | ms | 0.032 | [0.028, 0.036] | supported |
| Victim offered-load SLO success | fraction of offered | 34.236 | [12.375, 55.000] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.859 | [0.838, 0.882] | negative |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 1.003 | [0.937, 1.069] | negative |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.866 | [0.845, 0.889] | negative |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.222 | [0.213, 0.230] | supported |

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
| attack | 42 | 75302 | 95576 | 39496 | 8416 | 14.90 | 176.13 | 88.90 | 29683.1 | 31841.0 | 284.2 | 0.032 | 0 | False |
| control | 42 | 75241 | 117517 | 79949 | 37568 | 45.46 | 874.53 | 118.47 | 33831.9 | 35991.2 | 316.7 | 0.022 | 0 | False |
| attack | 43 | 76924 | 98146 | 41266 | 9152 | 15.24 | 196.21 | 89.15 | 29958.3 | 32100.0 | 281.8 | 0.039 | 0 | False |
| control | 43 | 76935 | 120373 | 82165 | 38208 | 57.70 | 863.60 | 119.93 | 33406.1 | 35492.5 | 316.3 | 0.022 | 0 | False |
| attack | 44 | 86889 | 110336 | 45504 | 9504 | 16.82 | 202.48 | 96.15 | 30494.8 | 32653.4 | 288.5 | 0.035 | 0 | False |
| control | 44 | 86906 | 132434 | 90642 | 41792 | 55.16 | 966.61 | 131.20 | 37069.1 | 39253.5 | 316.9 | 0.023 | 0 | False |
| attack | 45 | 94770 | 119228 | 47532 | 9504 | 17.59 | 205.54 | 94.00 | 31257.4 | 33403.6 | 293.2 | 0.038 | 0 | False |
| control | 45 | 94797 | 131184 | 89328 | 41856 | 76.17 | 916.21 | 130.54 | 37068.5 | 39355.6 | 316.0 | 0.023 | 0 | False |
| attack | 46 | 94407 | 119273 | 48265 | 9984 | 18.46 | 214.13 | 100.64 | 31218.3 | 33450.0 | 293.7 | 0.034 | 0 | False |
| control | 46 | 94364 | 128267 | 87371 | 40896 | 67.36 | 928.16 | 128.29 | 36434.2 | 38747.4 | 315.3 | 0.022 | 0 | False |

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
| competitor_completion | FAIL | lowest arm 0.855 (min 0.95) |
| primary_metric_present | pass | 5/5 seeds have a finite GPU Dynamic Energy per 1,000 Authorized Tokens |
| tokenized_context | FAIL | no pre-run tokenization check recorded |
| provenance | FAIL | dirty ['True']; model revision status not recorded |
| victim_latency_censoring | FAIL | worst arm censored fraction 0.052 (max 0.05); secondary latency endpoints only |

## Verdict

Under matched budgets, the attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens does NOT reach the pre-registered threshold on a majority of seeds (reported as a negative result, per the plan).
Pre-registered CI classification: **negative**.

