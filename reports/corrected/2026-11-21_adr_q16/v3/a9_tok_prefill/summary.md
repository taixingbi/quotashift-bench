# QuotaShift attack-effect report — `a9_tok_prefill`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/v3/a9_tok_prefill/.

- Control: `matched_total_short`  ·  seeds: 5  ·  pre-registered metric: **GPU Dynamic Energy per 1,000 Authorized Tokens** (`gpu_energy_per_1k_authorized_tokens`, unit: J per 1,000 authorized tokens)
- Definition: arm-window GPU dynamic energy (board power minus pre-arm idle) / (planned input + requested output tokens of all requests in the arm / 1000)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **negative** (seeds with metric: 5).

## GPU Dynamic Energy per 1,000 Authorized Tokens: attack vs matched control

- Mean attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens: **0.90×**  (median 0.91×, 95% bootstrap CI [0.89, 0.92])
- **Threshold-crossing rate: 0%** of 5 seeds crossed the threshold.

### Per-seed detail (matched pairs; values in J per 1,000 authorized tokens)

| seed | attack (J per 1,000 authorized tokens) | control (J per 1,000 authorized tokens) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 414.18 | 450.96 | 0.92 | no | 0/0 |
| 43 | 406.96 | 443.88 | 0.92 | no | 0/0 |
| 44 | 377.93 | 428.86 | 0.88 | no | 0/2 |
| 45 | 350.45 | 392.06 | 0.89 | no | 0/3 |
| 46 | 352.65 | 388.61 | 0.91 | no | 0/7 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 522.8 | 522.8 | 0.0 | 2995.5 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 0.071 | 42741.2 | 386.0 | 42536.7 | 44111.0 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 591.8 | 530.5 | 14.4 | 3247.1 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.018 | 43408.5 | 329.7 | 43096.0 | 44694.0 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 585.2 | 510.5 | 144.6 | 2924.3 |
| control | 44 | 111 | 109 | 0 | 2 | 0 | 0 | 0.000 | 58283.2 | 247.0 | 58136.4 | 59762.1 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 777.0 | 738.2 | 61.5 | 3486.4 |
| control | 45 | 106 | 103 | 0 | 3 | 0 | 0 | 0.028 | 59478.4 | 355.9 | 59220.1 | 60801.5 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 734.0 | 700.9 | 0.0 | 3015.6 |
| control | 46 | 115 | 108 | 0 | 7 | 0 | 0 | 0.000 | 58762.0 | 377.0 | 58479.0 | 60062.8 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.793 | [1.548, 2.028] | supported |
| Victim user-facing TTFT P95 | ms | 0.012 | [0.011, 0.013] | supported |
| Victim gateway queue time P95 | ms | 0.001 | [0.000, 0.002] | supported |
| Victim end-to-end latency P95 | ms | 0.059 | [0.051, 0.068] | supported |
| Victim offered-load SLO success | fraction of offered | 34.825 | [14.143, 55.000] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.904 | [0.891, 0.916] | negative |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.691 | [0.647, 0.734] | supported |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.909 | [0.896, 0.920] | negative |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.314 | [0.295, 0.334] | supported |

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
| attack | 42 | 75302 | 145115 | 136699 | 8416 | 39.01 | 218.92 | 93.71 | 31188.9 | 33229.7 | 297.9 | 0.160 | 0 | False |
| control | 42 | 75241 | 117517 | 79949 | 37568 | 73.39 | 838.63 | 119.83 | 33930.5 | 36046.9 | 316.1 | 0.022 | 0 | False |
| attack | 43 | 76924 | 147762 | 138610 | 9152 | 42.75 | 246.56 | 97.95 | 31304.7 | 33435.2 | 293.9 | 0.136 | 0 | False |
| control | 43 | 76935 | 120373 | 82165 | 38208 | 88.37 | 829.01 | 119.95 | 34149.8 | 36317.2 | 316.1 | 0.022 | 0 | False |
| attack | 44 | 86889 | 167772 | 158268 | 9504 | 46.26 | 254.42 | 99.96 | 32838.4 | 35039.0 | 305.7 | 0.141 | 2 | False |
| control | 44 | 86906 | 131205 | 89824 | 41381 | 65.56 | 949.42 | 130.82 | 37270.8 | 39534.8 | 316.1 | 0.023 | 0 | False |
| attack | 45 | 94770 | 183685 | 174181 | 9504 | 56.11 | 277.44 | 102.07 | 33212.6 | 35392.4 | 309.7 | 0.184 | 2 | False |
| control | 45 | 94797 | 131273 | 89353 | 41920 | 112.49 | 885.83 | 129.82 | 37165.9 | 39330.5 | 316.3 | 0.023 | 0 | False |
| attack | 46 | 94407 | 182527 | 172543 | 9984 | 51.31 | 284.00 | 104.52 | 33292.4 | 35580.0 | 309.2 | 0.139 | 0 | False |
| control | 46 | 94364 | 127688 | 87048 | 40640 | 97.84 | 878.61 | 126.98 | 36670.7 | 38905.3 | 316.6 | 0.023 | 0 | False |

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
| competitor_completion | FAIL | lowest arm 0.850 (min 0.95) |
| primary_metric_present | pass | 5/5 seeds have a finite GPU Dynamic Energy per 1,000 Authorized Tokens |
| tokenized_context | FAIL | no pre-run tokenization check recorded |
| provenance | FAIL | dirty ['True']; model revision status not recorded |
| victim_latency_censoring | FAIL | worst arm censored fraction 0.061 (max 0.05); secondary latency endpoints only |

## Verdict

Under matched budgets, the attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens does NOT reach the pre-registered threshold on a majority of seeds (reported as a negative result, per the plan).
Pre-registered CI classification: **negative**.

