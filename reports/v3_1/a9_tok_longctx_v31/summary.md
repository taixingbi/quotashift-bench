# QuotaShift attack-effect report — `a9_tok_longctx_v31`

> Live target measurements.

- Control: `matched_total_short`  ·  seeds: 5  ·  pre-registered metric: **GPU Dynamic Energy per 1,000 Authorized Tokens** (`gpu_energy_per_1k_authorized_tokens`, unit: J per 1,000 authorized tokens)
- Definition: arm-window GPU dynamic energy (board power minus pre-arm idle) / (planned input + requested output tokens of all requests in the arm / 1000)
- **Pre-registered threshold: 1.25×** (fixed before runs; ADR-Q08), direction `two_sided`; CI-based classification: **invalid** (seeds with metric: 5).

## GPU Dynamic Energy per 1,000 Authorized Tokens: attack vs matched control

- Mean attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens: **0.94×**  (median 0.94×, 95% bootstrap CI [0.92, 0.97])
- **Threshold-crossing rate: 0%** of 5 seeds crossed the threshold.

### Per-seed detail (matched pairs; values in J per 1,000 authorized tokens)

| seed | attack (J per 1,000 authorized tokens) | control (J per 1,000 authorized tokens) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 483.58 | 485.38 | 1.00 | no | 0/0 |
| 43 | 391.45 | 425.34 | 0.92 | no | 0/0 |
| 44 | 357.13 | 396.44 | 0.90 | no | 0/0 |
| 45 | 293.35 | 311.22 | 0.94 | no | 0/9 |
| 46 | 288.70 | 302.49 | 0.95 | no | 0/15 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 1.000 | 185.0 | 185.0 | 0.0 | 2143.1 |
| control | 42 | 99 | 99 | 0 | 0 | 0 | 0 | 0.374 | 16879.3 | 105.2 | 16813.5 | 18243.2 |
| attack | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 1.000 | 810.8 | 354.0 | 236.1 | 2778.0 |
| control | 43 | 110 | 110 | 0 | 0 | 0 | 0 | 0.064 | 34799.3 | 136.2 | 34673.3 | 36128.9 |
| attack | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 1.000 | 841.1 | 517.9 | 96.9 | 2770.7 |
| control | 44 | 111 | 111 | 0 | 0 | 0 | 0 | 0.000 | 55822.1 | 117.1 | 55734.0 | 57177.4 |
| attack | 45 | 106 | 106 | 0 | 0 | 0 | 0 | 0.962 | 1139.1 | 813.6 | 721.1 | 4041.2 |
| control | 45 | 106 | 97 | 0 | 9 | 0 | 0 | 0.019 | 59612.8 | 154.2 | 59460.4 | 60932.7 |
| attack | 46 | 115 | 115 | 0 | 0 | 0 | 0 | 1.000 | 654.0 | 654.0 | 0.0 | 2878.1 |
| control | 46 | 115 | 100 | 0 | 15 | 0 | 0 | 0.000 | 59997.1 | 140.2 | 59914.0 | 61372.7 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 3.745 | [2.508, 4.862] | supported |
| Victim user-facing TTFT P95 | ms | 0.016 | [0.012, 0.020] | supported |
| Victim gateway queue time P95 | ms | 0.004 | [0.000, 0.009] | supported |
| Victim end-to-end latency P95 | ms | 0.071 | [0.051, 0.096] | supported |
| Victim offered-load SLO success | fraction of offered | 23.130 | [2.676, 51.000] | insufficient_seeds |
| GPU Dynamic Energy per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.943 | [0.917, 0.973] | negative |
| GPU Dynamic Energy per 1,000 Realized Tokens | J per 1,000 realized tokens | 0.856 | [0.765, 0.947] | inconclusive |
| GPU Dynamic Energy incl. Post-arm Tail per 1,000 Authorized Tokens | J per 1,000 authorized tokens | 0.945 | [0.922, 0.974] | negative |
| Engine Service Time per 1,000 Authorized Tokens | s per 1,000 authorized tokens | 0.364 | [0.336, 0.391] | supported |

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
| attack | 42 | 64691 | 64691 | 54515 | 10176 | 17.48 | 223.73 | 100.13 | 31283.0 | 33394.9 | 291.1 | 0.148 | 1 | False |
| control | 42 | 64747 | 64747 | 32427 | 32320 | 26.61 | 681.31 | 107.21 | 31427.2 | 33528.3 | 300.8 | 0.012 | 0 | False |
| attack | 43 | 77811 | 77804 | 65907 | 11897 | 21.09 | 278.75 | 102.33 | 30459.1 | 32603.6 | 286.2 | 0.199 | 1 | False |
| control | 43 | 77831 | 77831 | 39175 | 38656 | 38.25 | 813.98 | 114.34 | 33104.4 | 35218.2 | 307.0 | 0.014 | 0 | False |
| attack | 44 | 93036 | 93009 | 80300 | 12709 | 27.16 | 300.78 | 110.81 | 33225.7 | 35411.1 | 301.8 | 0.207 | 0 | False |
| control | 44 | 93054 | 93037 | 46974 | 46063 | 39.34 | 976.41 | 130.45 | 36890.0 | 39117.5 | 313.9 | 0.013 | 0 | False |
| attack | 45 | 118240 | 118240 | 103776 | 14464 | 32.97 | 366.20 | 115.57 | 34685.8 | 36864.4 | 304.9 | 0.331 | 1 | False |
| control | 45 | 118221 | 91988 | 46100 | 45888 | 49.41 | 962.74 | 130.49 | 36793.2 | 38971.8 | 313.4 | 0.014 | 0 | False |
| attack | 46 | 119770 | 119617 | 104730 | 14887 | 34.37 | 374.63 | 118.51 | 34577.7 | 36687.3 | 309.9 | 0.288 | 1 | False |
| control | 46 | 119708 | 91136 | 45705 | 45431 | 43.78 | 959.71 | 129.06 | 36210.7 | 38472.8 | 313.3 | 0.013 | 0 | False |

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
| competitor_completion | FAIL | lowest arm 0.746 (min 0.95) |
| primary_metric_present | pass | 5/5 seeds have a finite GPU Dynamic Energy per 1,000 Authorized Tokens |
| tokenized_context | pass | max completed prompt+max_output 3840.0 <= 4096; pre-run check ok |
| planned_vs_reported_tokens | pass | 0 mismatch(es) among 3913/3913 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it) |
| provenance | pass | sha 02448f8cb6ad, clean, server start 1795268683.89 |
| victim_latency_censoring | FAIL | worst arm censored fraction 0.130 (max 0.05); secondary latency endpoints only |

## Verdict

Under matched budgets, the attack/control ratio of GPU Dynamic Energy per 1,000 Authorized Tokens does NOT reach the pre-registered threshold on a majority of seeds (reported as a negative result, per the plan).
Pre-registered CI classification: **invalid**. (Computed before validity gates: negative.)

