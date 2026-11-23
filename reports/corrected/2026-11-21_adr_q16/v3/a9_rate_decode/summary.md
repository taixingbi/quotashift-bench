# QuotaShift attack-effect report — `a9_rate_decode`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/v3/a9_rate_decode/.

- Control: `rate_matched_short`  ·  seeds: 5  ·  pre-registered metric: **GPU Dynamic Energy per 1,000 Authorized Tokens** (`gpu_energy_per_1k_authorized_tokens`, unit: J per 1,000 authorized tokens)
- Definition: arm-window GPU dynamic energy (board power minus pre-arm idle) / (planned input + requested output tokens of all requests in the arm / 1000)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **supported** (seeds with metric: 5).

## GPU Dynamic Energy per 1,000 Authorized Tokens: attack vs matched control

- Mean attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens: **0.62×**  (median 0.63×, 95% bootstrap CI [0.61, 0.64])
- **Threshold-crossing rate: 100%** of 5 seeds crossed the threshold.

### Per-seed detail (matched pairs; values in J per 1,000 authorized tokens)

| seed | attack (J per 1,000 authorized tokens) | control (J per 1,000 authorized tokens) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 743.45 | 1164.84 | 0.64 | yes | 0/0 |
| 43 | 683.67 | 1068.65 | 0.64 | yes | 0/0 |
| 44 | 683.38 | 1086.13 | 0.63 | yes | 0/0 |
| 45 | 639.05 | 1056.00 | 0.61 | yes | 0/0 |
| 46 | 615.34 | 1013.78 | 0.61 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 0.929 | 2216.2 | 143.2 | 2105.4 | 3586.1 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 141.7 | 141.7 | 0.0 | 1503.8 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.882 | 3421.3 | 132.8 | 3347.3 | 4776.6 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 147.5 | 147.5 | 0.0 | 1581.2 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 0.766 | 3639.4 | 145.5 | 3505.8 | 5036.3 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 282.1 | 184.6 | 6.0 | 1720.3 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 0.698 | 3695.7 | 146.4 | 3607.3 | 5032.5 |
| control | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 1.000 | 215.5 | 173.4 | 0.0 | 1578.3 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 0.765 | 3212.6 | 135.1 | 3081.1 | 4549.4 |
| control | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 140.2 | 140.2 | 0.0 | 1530.8 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 0.902 | [0.833, 0.970] | negative |
| Victim user-facing TTFT P95 | ms | 18.363 | [14.847, 21.879] | supported |
| Victim gateway queue time P95 | ms | 580.798 | [580.798, 580.798] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 2.899 | [2.621, 3.093] | supported |
| Victim offered-load SLO success | fraction of offered | 0.808 | [0.738, 0.887] | inconclusive |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.624 | [0.611, 0.637] | supported |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.768 | [0.755, 0.782] | supported |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.621 | [0.608, 0.633] | supported |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 1.416 | [1.407, 1.426] | supported |

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
| attack | 42 | 45978 | 59232 | 25703 | 33529 | 13.58 | 702.43 | 122.25 | 34182.5 | 36395.0 | 311.5 | 0.033 | 0 | False |
| control | 42 | 26601 | 41709 | 28461 | 13248 | 14.61 | 274.90 | 106.10 | 30985.8 | 33151.3 | 300.3 | 0.017 | 0 | False |
| attack | 43 | 51993 | 66215 | 29347 | 36868 | 15.45 | 776.31 | 126.33 | 35545.9 | 37697.9 | 310.0 | 0.031 | 0 | False |
| control | 43 | 30215 | 47535 | 32687 | 14848 | 16.53 | 311.87 | 106.80 | 32289.3 | 34543.1 | 300.3 | 0.020 | 0 | False |
| attack | 44 | 50391 | 65095 | 29637 | 35458 | 15.30 | 749.05 | 121.97 | 34436.1 | 36569.6 | 311.4 | 0.031 | 0 | False |
| control | 44 | 29818 | 47161 | 32697 | 14464 | 16.83 | 303.77 | 109.66 | 32386.4 | 34572.3 | 302.5 | 0.023 | 0 | False |
| attack | 45 | 54987 | 69936 | 29821 | 40115 | 15.89 | 845.43 | 124.43 | 35139.4 | 37408.2 | 312.0 | 0.032 | 0 | False |
| control | 45 | 30925 | 48557 | 33197 | 15360 | 17.11 | 322.94 | 112.10 | 32656.9 | 34904.8 | 302.3 | 0.019 | 0 | False |
| attack | 46 | 56119 | 70863 | 30467 | 40396 | 16.44 | 852.54 | 122.73 | 34532.3 | 36743.5 | 311.2 | 0.031 | 0 | False |
| control | 46 | 32284 | 50706 | 34706 | 16000 | 17.99 | 335.91 | 113.94 | 32728.9 | 34933.5 | 305.0 | 0.020 | 0 | False |

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

