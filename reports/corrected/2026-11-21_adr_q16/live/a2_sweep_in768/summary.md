# QuotaShift attack-effect report — `a2_sweep_in768`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/live/a2_sweep_in768/.

- Control: `matched_total_short`  ·  seeds: 5  ·  pre-registered metric: **Victim backend TTFT P95 (historical `ttft_p95`)** (`ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_sent (backend dispatch); excludes gateway queue time (ADR-Q16)
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **n/a (protocol v1: majority-of-seeds verdict)** (seeds with metric: 5).

## Victim backend TTFT P95 (historical `ttft_p95`): victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim backend TTFT P95 (historical `ttft_p95`): **3.00×**  (median 2.78×, 95% bootstrap CI [2.53, 3.47])
- **Threshold-crossing rate: 100%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 27794 tokens, 38 requests per run.
- Victim slowdown per 1k competing tokens: 0.0719
- Victim slowdown per 100 competing requests: 5.2065

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 521.31 | 148.99 | 3.50 | yes | 0/0 |
| 43 | 413.95 | 148.93 | 2.78 | yes | 0/1 |
| 44 | 368.46 | 143.78 | 2.56 | yes | 0/1 |
| 45 | 340.53 | 89.76 | 3.79 | yes | 0/0 |
| 46 | 189.46 | 80.22 | 2.36 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 0.970 | 661.7 | 521.3 | 462.2 | 2699.4 |
| control | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 0.000 | 46895.4 | 149.0 | 46775.6 | 48177.6 |
| attack | 43 | 37 | 37 | 0 | 0 | 0 | 0 | 1.000 | 835.3 | 413.9 | 505.2 | 2673.3 |
| control | 43 | 37 | 20 | 0 | 1 | 0 | 16 | 0.054 | 57385.2 | 148.9 | 59053.2 | 58680.2 |
| attack | 44 | 42 | 42 | 0 | 0 | 0 | 0 | 1.000 | 918.0 | 368.5 | 788.1 | 2766.2 |
| control | 44 | 42 | 22 | 0 | 1 | 0 | 19 | 0.024 | 59830.3 | 143.8 | 59772.0 | 61196.5 |
| attack | 45 | 36 | 36 | 0 | 0 | 0 | 0 | 1.000 | 398.8 | 340.5 | 242.7 | 2369.8 |
| control | 45 | 36 | 36 | 0 | 0 | 0 | 0 | 0.000 | 45042.7 | 89.8 | 44983.2 | 46334.2 |
| attack | 46 | 26 | 26 | 0 | 0 | 0 | 0 | 1.000 | 274.2 | 189.5 | 0.0 | 2285.6 |
| control | 46 | 26 | 26 | 0 | 0 | 0 | 0 | 0.000 | 46324.4 | 80.2 | 46249.8 | 47594.7 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 2.999 | [2.526, 3.473] | supported |
| Victim user-facing TTFT P95 | ms | 0.012 | [0.008, 0.015] | negative |
| Victim gateway queue time P95 | ms | 0.007 | [0.003, 0.011] | negative |
| Victim end-to-end latency P95 | ms | 0.049 | [0.046, 0.053] | negative |
| Victim offered-load SLO success | fraction of offered | 30.250 | [18.500, 42.000] | insufficient_seeds |

### Validity gates (fail closed; ADR-Q17)

Overall: **FAIL**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | FAIL | lowest arm 0.864 (min 0.95) |
| primary_metric_present | pass | 5/5 seeds have a finite Victim backend TTFT P95 (historical `ttft_p95`) |
| tokenized_context | FAIL | no pre-run tokenization check recorded |
| provenance | FAIL | dirty ['True']; server start ['None']; vllm version; model revision status not recorded |
| victim_latency_censoring | FAIL | worst arm censored fraction 0.476 (max 0.05); primary |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **n/a (protocol v1: majority-of-seeds verdict)**.

