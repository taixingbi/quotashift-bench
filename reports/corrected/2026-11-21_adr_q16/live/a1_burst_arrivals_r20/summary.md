# QuotaShift attack-effect report — `a1_burst_arrivals`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/live/a1_burst_arrivals_r20/.

- Control: `uniform_arrivals`  ·  seeds: 20  ·  pre-registered metric: **Victim backend TTFT P95 (historical `ttft_p95`)** (`ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_sent (backend dispatch); excludes gateway queue time (ADR-Q16)
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **n/a (protocol v1: majority-of-seeds verdict)** (seeds with metric: 20).

## Victim backend TTFT P95 (historical `ttft_p95`): victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim backend TTFT P95 (historical `ttft_p95`): **1.59×**  (median 1.58×, 95% bootstrap CI [1.53, 1.65])
- **Threshold-crossing rate: 70%** of 20 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 14147 tokens, 108 requests per run.
- Victim slowdown per 1k competing tokens: 0.0417
- Victim slowdown per 100 competing requests: 0.5469

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 136.45 | 83.84 | 1.63 | yes | 0/0 |
| 43 | 139.33 | 85.36 | 1.63 | yes | 0/0 |
| 44 | 124.68 | 82.99 | 1.50 | yes | 0/0 |
| 45 | 123.70 | 85.62 | 1.44 | no | 0/0 |
| 46 | 124.98 | 87.22 | 1.43 | no | 0/0 |
| 47 | 124.56 | 87.12 | 1.43 | no | 0/0 |
| 48 | 132.09 | 90.20 | 1.46 | no | 0/0 |
| 49 | 141.61 | 84.02 | 1.69 | yes | 0/0 |
| 50 | 139.39 | 84.19 | 1.66 | yes | 0/0 |
| 51 | 123.97 | 82.94 | 1.49 | no | 0/0 |
| 52 | 152.51 | 81.25 | 1.88 | yes | 0/0 |
| 53 | 129.27 | 84.20 | 1.54 | yes | 0/0 |
| 54 | 127.99 | 83.96 | 1.52 | yes | 0/0 |
| 55 | 130.64 | 83.16 | 1.57 | yes | 0/0 |
| 56 | 122.39 | 89.03 | 1.37 | no | 0/0 |
| 57 | 162.30 | 84.24 | 1.93 | yes | 0/0 |
| 58 | 138.96 | 86.59 | 1.60 | yes | 0/0 |
| 59 | 155.90 | 89.72 | 1.74 | yes | 0/0 |
| 60 | 137.87 | 86.32 | 1.60 | yes | 0/0 |
| 61 | 136.30 | 81.18 | 1.68 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 0.970 | 1376.7 | 136.4 | 1293.6 | 2632.2 |
| control | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 1.000 | 756.8 | 83.8 | 697.7 | 2020.1 |
| attack | 43 | 37 | 37 | 0 | 0 | 0 | 0 | 0.514 | 4316.3 | 139.3 | 4241.8 | 5607.8 |
| control | 43 | 37 | 37 | 0 | 0 | 0 | 0 | 1.000 | 567.2 | 85.4 | 508.9 | 1833.5 |
| attack | 44 | 42 | 42 | 0 | 0 | 0 | 0 | 0.905 | 2652.3 | 124.7 | 2547.8 | 4011.2 |
| control | 44 | 42 | 42 | 0 | 0 | 0 | 0 | 1.000 | 240.1 | 83.0 | 179.3 | 1504.3 |
| attack | 45 | 36 | 36 | 0 | 0 | 0 | 0 | 0.806 | 2521.2 | 123.7 | 2445.8 | 3877.1 |
| control | 45 | 36 | 36 | 0 | 0 | 0 | 0 | 1.000 | 671.0 | 85.6 | 597.1 | 1939.2 |
| attack | 46 | 26 | 26 | 0 | 0 | 0 | 0 | 0.538 | 5355.9 | 125.0 | 5271.8 | 6657.9 |
| control | 46 | 26 | 26 | 0 | 0 | 0 | 0 | 1.000 | 512.1 | 87.2 | 447.6 | 1778.5 |
| attack | 47 | 42 | 42 | 0 | 0 | 0 | 0 | 0.286 | 6551.7 | 124.6 | 6479.5 | 7870.0 |
| control | 47 | 42 | 42 | 0 | 0 | 0 | 0 | 1.000 | 562.2 | 87.1 | 503.1 | 1829.3 |
| attack | 48 | 34 | 34 | 0 | 0 | 0 | 0 | 0.882 | 2484.6 | 132.1 | 2372.6 | 3815.5 |
| control | 48 | 34 | 34 | 0 | 0 | 0 | 0 | 1.000 | 455.0 | 90.2 | 395.5 | 1721.9 |
| attack | 49 | 32 | 32 | 0 | 0 | 0 | 0 | 0.969 | 1644.3 | 141.6 | 1560.3 | 3008.3 |
| control | 49 | 32 | 32 | 0 | 0 | 0 | 0 | 1.000 | 484.6 | 84.0 | 424.8 | 1752.3 |
| attack | 50 | 30 | 30 | 0 | 0 | 0 | 0 | 0.900 | 2119.5 | 139.4 | 2013.1 | 3463.3 |
| control | 50 | 30 | 30 | 0 | 0 | 0 | 0 | 1.000 | 380.5 | 84.2 | 300.6 | 1644.6 |
| attack | 51 | 45 | 45 | 0 | 0 | 0 | 0 | 0.178 | 11060.4 | 124.0 | 10980.8 | 12405.1 |
| control | 51 | 45 | 45 | 0 | 0 | 0 | 0 | 0.711 | 3596.6 | 82.9 | 3517.0 | 4864.2 |
| attack | 52 | 43 | 43 | 0 | 0 | 0 | 0 | 0.302 | 16173.9 | 152.5 | 16078.5 | 17465.2 |
| control | 52 | 43 | 43 | 0 | 0 | 0 | 0 | 0.233 | 8803.7 | 81.3 | 8728.1 | 10067.4 |
| attack | 53 | 32 | 32 | 0 | 0 | 0 | 0 | 0.812 | 4817.9 | 129.3 | 4714.8 | 6081.8 |
| control | 53 | 32 | 32 | 0 | 0 | 0 | 0 | 1.000 | 763.9 | 84.2 | 706.1 | 2033.4 |
| attack | 54 | 33 | 33 | 0 | 0 | 0 | 0 | 0.939 | 1747.2 | 128.0 | 1654.0 | 3029.2 |
| control | 54 | 33 | 33 | 0 | 0 | 0 | 0 | 1.000 | 631.5 | 84.0 | 564.6 | 1900.7 |
| attack | 55 | 34 | 34 | 0 | 0 | 0 | 0 | 0.765 | 3188.7 | 130.6 | 3092.6 | 4515.8 |
| control | 55 | 34 | 34 | 0 | 0 | 0 | 0 | 1.000 | 669.4 | 83.2 | 609.5 | 1937.5 |
| attack | 56 | 34 | 34 | 0 | 0 | 0 | 0 | 1.000 | 1611.3 | 122.4 | 1507.4 | 2919.1 |
| control | 56 | 34 | 34 | 0 | 0 | 0 | 0 | 1.000 | 316.4 | 89.0 | 249.9 | 1582.9 |
| attack | 57 | 31 | 31 | 0 | 0 | 0 | 0 | 0.968 | 884.7 | 162.3 | 801.6 | 2242.5 |
| control | 57 | 31 | 31 | 0 | 0 | 0 | 0 | 1.000 | 86.9 | 84.2 | 5.1 | 1353.1 |
| attack | 58 | 38 | 38 | 0 | 0 | 0 | 0 | 0.605 | 5365.1 | 139.0 | 5287.4 | 6720.0 |
| control | 58 | 38 | 38 | 0 | 0 | 0 | 0 | 1.000 | 868.7 | 86.6 | 787.7 | 2138.3 |
| attack | 59 | 31 | 31 | 0 | 0 | 0 | 0 | 0.806 | 2711.2 | 155.9 | 2613.5 | 4035.3 |
| control | 59 | 31 | 31 | 0 | 0 | 0 | 0 | 1.000 | 355.2 | 89.7 | 286.0 | 1620.5 |
| attack | 60 | 34 | 34 | 0 | 0 | 0 | 0 | 0.647 | 3546.8 | 137.9 | 3444.8 | 4876.2 |
| control | 60 | 34 | 34 | 0 | 0 | 0 | 0 | 1.000 | 798.0 | 86.3 | 718.5 | 2063.3 |
| attack | 61 | 40 | 40 | 0 | 0 | 0 | 0 | 1.000 | 1566.0 | 136.3 | 1492.8 | 2947.3 |
| control | 61 | 40 | 40 | 0 | 0 | 0 | 0 | 1.000 | 585.3 | 81.2 | 526.5 | 1854.3 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.590 | [1.532, 1.655] | supported |
| Victim user-facing TTFT P95 | ms | 5.786 | [4.515, 7.141] | supported |
| Victim gateway queue time P95 | ms | 13.799 | [5.102, 29.800] | supported |
| Victim end-to-end latency P95 | ms | 2.370 | [2.056, 2.715] | supported |
| Victim offered-load SLO success | fraction of offered | 0.793 | [0.684, 0.897] | negative |

### Validity gates (fail closed; ADR-Q17)

Overall: **FAIL**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | pass | lowest arm 1.000 (min 0.95) |
| primary_metric_present | pass | 20/20 seeds have a finite Victim backend TTFT P95 (historical `ttft_p95`) |
| tokenized_context | FAIL | no pre-run tokenization check recorded |
| provenance | FAIL | server start ['None']; vllm version; model revision status not recorded |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **n/a (protocol v1: majority-of-seeds verdict)**.

