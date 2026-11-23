# QuotaShift attack-effect report — `a9_tok_decode`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/v3/a9_tok_decode/.

- Control: `matched_total_short`  ·  seeds: 5  ·  pre-registered metric: **GPU Dynamic Energy per 1,000 Authorized Tokens** (`gpu_energy_per_1k_authorized_tokens`, unit: J per 1,000 authorized tokens)
- Definition: arm-window GPU dynamic energy (board power minus pre-arm idle) / (planned input + requested output tokens of all requests in the arm / 1000)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **negative** (seeds with metric: 5).

## GPU Dynamic Energy per 1,000 Authorized Tokens: attack vs matched control

- Mean attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens: **1.10×**  (median 1.09×, 95% bootstrap CI [1.07, 1.13])
- **Threshold-crossing rate: 0%** of 5 seeds crossed the threshold.

### Per-seed detail (matched pairs; values in J per 1,000 authorized tokens)

| seed | attack (J per 1,000 authorized tokens) | control (J per 1,000 authorized tokens) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 733.91 | 671.74 | 1.09 | no | 0/0 |
| 43 | 683.28 | 610.52 | 1.12 | no | 0/0 |
| 44 | 682.27 | 640.16 | 1.07 | no | 0/0 |
| 45 | 640.45 | 558.15 | 1.15 | no | 0/0 |
| 46 | 607.55 | 568.95 | 1.07 | no | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 0.939 | 2241.2 | 233.1 | 1991.9 | 3397.9 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 0.808 | 3951.7 | 226.5 | 3711.1 | 5366.1 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.873 | 3403.1 | 190.6 | 3310.0 | 4750.2 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.427 | 8550.7 | 195.6 | 8447.5 | 10056.3 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 0.820 | 2815.2 | 259.2 | 2667.6 | 4247.3 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 0.559 | 5656.1 | 232.4 | 5446.3 | 7097.0 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 0.689 | 3473.1 | 166.8 | 3389.4 | 4817.8 |
| control | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 0.481 | 14176.0 | 314.0 | 13871.1 | 15463.1 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 0.652 | 3249.3 | 138.6 | 3123.8 | 4585.0 |
| control | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 0.400 | 19525.5 | 164.0 | 19398.4 | 21017.5 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 0.899 | [0.709, 1.053] | inconclusive |
| Victim user-facing TTFT P95 | ms | 0.375 | [0.244, 0.506] | supported |
| Victim gateway queue time P95 | ms | 0.365 | [0.241, 0.489] | supported |
| Victim end-to-end latency P95 | ms | 0.447 | [0.306, 0.587] | supported |
| Victim offered-load SLO success | fraction of offered | 1.547 | [1.317, 1.805] | supported |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 1.099 | [1.072, 1.125] | negative |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 1.344 | [1.310, 1.379] | supported |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 1.093 | [1.069, 1.119] | negative |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 1.305 | [1.288, 1.329] | supported |

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
| attack | 42 | 45978 | 58989 | 25703 | 33286 | 13.80 | 698.48 | 121.11 | 33743.5 | 35922.9 | 310.2 | 0.032 | 0 | False |
| control | 42 | 45929 | 71841 | 48929 | 22912 | 29.14 | 520.86 | 99.85 | 30852.4 | 33084.7 | 294.9 | 0.021 | 0 | False |
| attack | 43 | 51993 | 66486 | 29347 | 37139 | 15.74 | 782.31 | 126.29 | 35525.8 | 37731.8 | 309.1 | 0.032 | 0 | False |
| control | 43 | 51975 | 81413 | 55715 | 25698 | 31.84 | 590.08 | 103.60 | 31731.9 | 33873.7 | 295.6 | 0.021 | 0 | False |
| attack | 44 | 50391 | 65274 | 29637 | 35637 | 15.87 | 753.54 | 121.68 | 34380.5 | 36583.1 | 311.0 | 0.032 | 0 | False |
| control | 44 | 50426 | 79282 | 54514 | 24768 | 33.39 | 562.85 | 108.09 | 32280.8 | 34340.3 | 300.1 | 0.023 | 0 | False |
| attack | 45 | 54987 | 70068 | 29821 | 40247 | 16.49 | 847.65 | 125.25 | 35216.6 | 37354.9 | 312.1 | 0.032 | 0 | False |
| control | 45 | 54989 | 86073 | 58681 | 27392 | 73.27 | 565.77 | 102.37 | 30691.9 | 32820.3 | 293.5 | 0.023 | 0 | False |
| attack | 46 | 56119 | 71374 | 30467 | 40907 | 16.32 | 865.75 | 122.72 | 34095.1 | 36273.4 | 309.4 | 0.032 | 0 | False |
| control | 46 | 56092 | 87804 | 59900 | 27904 | 34.97 | 639.84 | 108.92 | 31913.4 | 34041.7 | 303.6 | 0.020 | 0 | False |

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

Under matched budgets, the attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens does NOT reach the pre-registered threshold on a majority of seeds (reported as a negative result, per the plan).
Pre-registered CI classification: **negative**.

