# QuotaShift attack-effect report — `a2_sweep_in256`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/live/a2_sweep_in256/.

- Control: `matched_total_short`  ·  seeds: 5  ·  pre-registered metric: **Victim backend TTFT P95 (historical `ttft_p95`)** (`ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_sent (backend dispatch); excludes gateway queue time (ADR-Q16)
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **n/a (protocol v1: majority-of-seeds verdict)** (seeds with metric: 5).

## Victim backend TTFT P95 (historical `ttft_p95`): victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim backend TTFT P95 (historical `ttft_p95`): **2.22×**  (median 2.22×, 95% bootstrap CI [1.54, 2.90])
- **Threshold-crossing rate: 60%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 29374 tokens, 112 requests per run.
- Victim slowdown per 1k competing tokens: 0.0416
- Victim slowdown per 100 competing requests: 1.0923

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 175.82 | 127.73 | 1.38 | no | 0/0 |
| 43 | 201.73 | 148.46 | 1.36 | no | 0/2 |
| 44 | 277.70 | 81.88 | 3.39 | yes | 0/0 |
| 45 | 252.91 | 114.02 | 2.22 | yes | 0/2 |
| 46 | 229.05 | 82.95 | 2.76 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 1.000 | 787.4 | 175.8 | 708.8 | 2457.4 |
| control | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 0.000 | 48339.7 | 127.7 | 48268.4 | 49667.2 |
| attack | 43 | 37 | 37 | 0 | 0 | 0 | 0 | 0.973 | 1643.5 | 201.7 | 1565.1 | 3384.3 |
| control | 43 | 37 | 19 | 0 | 2 | 0 | 16 | 0.054 | 55668.5 | 148.5 | 59314.7 | 56965.0 |
| attack | 44 | 42 | 42 | 0 | 0 | 0 | 0 | 1.000 | 1510.8 | 277.7 | 1415.8 | 3201.4 |
| control | 44 | 42 | 25 | 0 | 0 | 0 | 17 | 0.024 | 55789.6 | 81.9 | 56224.3 | 57077.0 |
| attack | 45 | 36 | 36 | 0 | 0 | 0 | 0 | 0.861 | 2878.1 | 252.9 | 2685.7 | 4423.3 |
| control | 45 | 36 | 12 | 0 | 2 | 0 | 22 | 0.000 | 56275.2 | 114.0 | 56080.3 | 57576.3 |
| attack | 46 | 26 | 26 | 0 | 0 | 0 | 0 | 1.000 | 556.5 | 229.0 | 454.7 | 2278.4 |
| control | 46 | 26 | 18 | 0 | 0 | 0 | 8 | 0.000 | 55233.0 | 83.0 | 54733.7 | 56496.8 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 2.221 | [1.538, 2.905] | supported |
| Victim user-facing TTFT P95 | ms | 0.027 | [0.015, 0.039] | negative |
| Victim gateway queue time P95 | ms | 0.024 | [0.013, 0.037] | negative |
| Victim end-to-end latency P95 | ms | 0.056 | [0.046, 0.067] | negative |
| Victim offered-load SLO success | fraction of offered | 30.000 | [18.000, 42.000] | insufficient_seeds |

### Validity gates (fail closed; ADR-Q17)

Overall: **FAIL**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | FAIL | lowest arm 0.935 (min 0.95) |
| primary_metric_present | pass | 5/5 seeds have a finite Victim backend TTFT P95 (historical `ttft_p95`) |
| tokenized_context | FAIL | no pre-run tokenization check recorded |
| provenance | FAIL | dirty ['True']; server start ['None']; vllm version; model revision status not recorded |
| victim_latency_censoring | FAIL | worst arm censored fraction 0.667 (max 0.05); primary |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **n/a (protocol v1: majority-of-seeds verdict)**.

