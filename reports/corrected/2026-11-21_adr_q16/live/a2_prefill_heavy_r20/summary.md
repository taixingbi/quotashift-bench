# QuotaShift attack-effect report — `a2_prefill_heavy`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/live/a2_prefill_heavy_r20/.

- Control: `matched_total_short`  ·  seeds: 20  ·  pre-registered metric: **Victim backend TTFT P95 (historical `ttft_p95`)** (`ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_sent (backend dispatch); excludes gateway queue time (ADR-Q16)
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **n/a (protocol v1: majority-of-seeds verdict)** (seeds with metric: 20).

## Victim backend TTFT P95 (historical `ttft_p95`): victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim backend TTFT P95 (historical `ttft_p95`): **3.19×**  (median 2.83×, 95% bootstrap CI [2.66, 3.75])
- **Threshold-crossing rate: 95%** of 20 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 36474 tokens, 38 requests per run.
- Victim slowdown per 1k competing tokens: 0.0601
- Victim slowdown per 100 competing requests: 5.7292

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 427.05 | 168.69 | 2.53 | yes | 0/6 |
| 43 | 501.74 | 129.02 | 3.89 | yes | 0/2 |
| 44 | 560.53 | 112.06 | 5.00 | yes | 0/5 |
| 45 | 229.50 | 129.41 | 1.77 | yes | 0/0 |
| 46 | 296.76 | 108.74 | 2.73 | yes | 0/2 |
| 47 | 786.92 | 160.68 | 4.90 | yes | 0/7 |
| 48 | 574.67 | 156.98 | 3.66 | yes | 0/0 |
| 49 | 601.03 | 389.54 | 1.54 | yes | 0/4 |
| 50 | 507.66 | 120.92 | 4.20 | yes | 0/7 |
| 51 | 489.35 | 199.48 | 2.45 | yes | 0/5 |
| 52 | 513.12 | 118.12 | 4.34 | yes | 0/5 |
| 53 | 465.91 | 81.63 | 5.71 | yes | 0/2 |
| 54 | 408.86 | 117.31 | 3.49 | yes | 0/3 |
| 55 | 379.46 | 152.95 | 2.48 | yes | 0/4 |
| 56 | 469.48 | 110.43 | 4.25 | yes | 0/2 |
| 57 | 647.43 | 367.82 | 1.76 | yes | 0/1 |
| 58 | 237.88 | 114.85 | 2.07 | yes | 0/0 |
| 59 | 474.54 | 162.96 | 2.91 | yes | 0/3 |
| 60 | 448.77 | 163.67 | 2.74 | yes | 0/10 |
| 61 | 828.91 | 593.72 | 1.40 | no | 0/2 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 1.000 | 608.5 | 427.1 | 204.8 | 2476.9 |
| control | 42 | 33 | 14 | 0 | 6 | 0 | 13 | 0.000 | 57738.3 | 168.7 | 59662.7 | 59066.4 |
| attack | 43 | 37 | 37 | 0 | 0 | 0 | 0 | 1.000 | 552.5 | 501.7 | 192.9 | 2644.7 |
| control | 43 | 37 | 19 | 0 | 2 | 0 | 16 | 0.054 | 59995.8 | 129.0 | 59882.4 | 61328.3 |
| attack | 44 | 42 | 42 | 0 | 0 | 0 | 0 | 1.000 | 1090.5 | 560.5 | 964.3 | 3047.6 |
| control | 44 | 42 | 18 | 0 | 5 | 0 | 19 | 0.024 | 52805.4 | 112.1 | 52739.0 | 54171.2 |
| attack | 45 | 36 | 36 | 0 | 0 | 0 | 0 | 1.000 | 752.2 | 229.5 | 550.9 | 2421.5 |
| control | 45 | 36 | 15 | 0 | 0 | 0 | 21 | 0.000 | 58674.5 | 129.4 | 58242.6 | 60028.1 |
| attack | 46 | 26 | 26 | 0 | 0 | 0 | 0 | 1.000 | 604.4 | 296.8 | 402.9 | 2658.8 |
| control | 46 | 26 | 8 | 0 | 2 | 0 | 16 | 0.000 | 59174.9 | 108.7 | 58556.1 | 60502.9 |
| attack | 47 | 42 | 42 | 0 | 0 | 0 | 0 | 0.833 | 3046.4 | 786.9 | 2547.9 | 4950.4 |
| control | 47 | 42 | 16 | 0 | 7 | 0 | 19 | 0.000 | 56083.3 | 160.7 | 58426.4 | 57413.2 |
| attack | 48 | 34 | 34 | 0 | 0 | 0 | 0 | 1.000 | 993.3 | 574.7 | 507.5 | 2627.0 |
| control | 48 | 34 | 12 | 0 | 0 | 0 | 22 | 0.000 | 56459.8 | 157.0 | 56373.9 | 57798.8 |
| attack | 49 | 32 | 32 | 0 | 0 | 0 | 0 | 1.000 | 1158.7 | 601.0 | 1062.7 | 3225.4 |
| control | 49 | 32 | 8 | 0 | 4 | 0 | 20 | 0.000 | 58628.1 | 389.5 | 58632.1 | 59767.5 |
| attack | 50 | 30 | 30 | 0 | 0 | 0 | 0 | 1.000 | 831.6 | 507.7 | 434.6 | 2942.4 |
| control | 50 | 30 | 12 | 0 | 7 | 0 | 11 | 0.000 | 56160.5 | 120.9 | 59216.4 | 57532.5 |
| attack | 51 | 45 | 45 | 0 | 0 | 0 | 0 | 0.911 | 2467.0 | 489.4 | 2376.7 | 4947.6 |
| control | 51 | 45 | 10 | 0 | 5 | 0 | 30 | 0.000 | 60047.4 | 199.5 | 59903.9 | 61436.2 |
| attack | 52 | 43 | 43 | 0 | 0 | 0 | 0 | 1.000 | 959.3 | 513.1 | 839.4 | 2769.0 |
| control | 52 | 43 | 15 | 0 | 5 | 0 | 23 | 0.000 | 60092.6 | 118.1 | 59988.1 | 61513.6 |
| attack | 53 | 32 | 32 | 0 | 0 | 0 | 0 | 1.000 | 585.1 | 465.9 | 26.8 | 2592.8 |
| control | 53 | 32 | 15 | 0 | 2 | 0 | 15 | 0.000 | 59722.5 | 81.6 | 59640.8 | 61065.7 |
| attack | 54 | 33 | 33 | 0 | 0 | 0 | 0 | 1.000 | 1057.4 | 408.9 | 948.8 | 2553.1 |
| control | 54 | 33 | 10 | 0 | 3 | 0 | 20 | 0.000 | 59587.4 | 117.3 | 59519.2 | 60951.3 |
| attack | 55 | 34 | 34 | 0 | 0 | 0 | 0 | 1.000 | 1272.4 | 379.5 | 1192.2 | 3522.4 |
| control | 55 | 34 | 12 | 0 | 4 | 0 | 18 | 0.000 | 59962.6 | 153.0 | 59803.7 | 61256.7 |
| attack | 56 | 34 | 34 | 0 | 0 | 0 | 0 | 1.000 | 472.6 | 469.5 | 49.0 | 2281.0 |
| control | 56 | 34 | 15 | 0 | 2 | 0 | 17 | 0.029 | 57280.0 | 110.4 | 58186.1 | 58611.6 |
| attack | 57 | 31 | 31 | 0 | 0 | 0 | 0 | 1.000 | 882.4 | 647.4 | 550.9 | 2611.0 |
| control | 57 | 31 | 19 | 0 | 1 | 0 | 11 | 0.065 | 60004.1 | 367.8 | 59443.3 | 61333.3 |
| attack | 58 | 38 | 38 | 0 | 0 | 0 | 0 | 1.000 | 341.8 | 237.9 | 28.7 | 2468.1 |
| control | 58 | 38 | 23 | 0 | 0 | 0 | 15 | 0.026 | 52719.1 | 114.8 | 52362.2 | 53997.1 |
| attack | 59 | 31 | 31 | 0 | 0 | 0 | 0 | 1.000 | 595.3 | 474.5 | 471.9 | 2973.9 |
| control | 59 | 31 | 11 | 0 | 3 | 0 | 17 | 0.000 | 59956.1 | 163.0 | 59822.9 | 61279.6 |
| attack | 60 | 34 | 34 | 0 | 0 | 0 | 0 | 1.000 | 1074.1 | 448.8 | 894.3 | 3225.6 |
| control | 60 | 34 | 9 | 0 | 10 | 0 | 15 | 0.029 | 51972.2 | 163.7 | 57997.9 | 53328.9 |
| attack | 61 | 40 | 40 | 0 | 0 | 0 | 0 | 0.975 | 1569.0 | 828.9 | 1195.2 | 4146.9 |
| control | 61 | 40 | 18 | 0 | 2 | 0 | 20 | 0.050 | 55107.1 | 593.7 | 54988.2 | 56563.0 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 3.191 | [2.663, 3.746] | supported |
| Victim user-facing TTFT P95 | ms | 0.018 | [0.014, 0.024] | negative |
| Victim gateway queue time P95 | ms | 0.013 | [0.009, 0.019] | negative |
| Victim end-to-end latency P95 | ms | 0.052 | [0.047, 0.058] | negative |
| Victim offered-load SLO success | fraction of offered | 28.786 | [21.786, 35.786] | supported |

### Validity gates (fail closed; ADR-Q17)

Overall: **FAIL**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | FAIL | lowest arm 0.618 (min 0.95) |
| primary_metric_present | pass | 20/20 seeds have a finite Victim backend TTFT P95 (historical `ttft_p95`) |
| tokenized_context | FAIL | no pre-run tokenization check recorded |
| provenance | FAIL | dirty ['False', 'True']; server start ['None']; vllm version; model revision status not recorded |
| victim_latency_censoring | FAIL | worst arm censored fraction 0.778 (max 0.05); primary |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **n/a (protocol v1: majority-of-seeds verdict)**.

