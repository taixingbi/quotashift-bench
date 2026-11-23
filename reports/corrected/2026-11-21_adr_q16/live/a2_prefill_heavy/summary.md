# QuotaShift attack-effect report — `a2_prefill_heavy`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/live/a2_prefill_heavy/.

- Control: `matched_total_short`  ·  seeds: 5  ·  pre-registered metric: **Victim backend TTFT P95 (historical `ttft_p95`)** (`ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_sent (backend dispatch); excludes gateway queue time (ADR-Q16)
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **n/a (protocol v1: majority-of-seeds verdict)** (seeds with metric: 5).

## Victim backend TTFT P95 (historical `ttft_p95`): victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim backend TTFT P95 (historical `ttft_p95`): **3.16×**  (median 3.14×, 95% bootstrap CI [2.37, 3.94])
- **Threshold-crossing rate: 100%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 33882 tokens, 35 requests per run.
- Victim slowdown per 1k competing tokens: 0.0637
- Victim slowdown per 100 competing requests: 6.0950

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 518.97 | 119.03 | 4.36 | yes | 0/3 |
| 43 | 424.55 | 149.54 | 2.84 | yes | 0/2 |
| 44 | 555.33 | 177.09 | 3.14 | yes | 0/3 |
| 45 | 195.74 | 116.62 | 1.68 | yes | 0/0 |
| 46 | 458.75 | 121.53 | 3.77 | yes | 0/2 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 1.000 | 749.5 | 519.0 | 249.2 | 2568.6 |
| control | 42 | 33 | 17 | 0 | 3 | 0 | 13 | 0.000 | 60022.5 | 119.0 | 59925.4 | 61353.9 |
| attack | 43 | 37 | 37 | 0 | 0 | 0 | 0 | 1.000 | 424.5 | 424.5 | 72.3 | 2625.4 |
| control | 43 | 37 | 18 | 0 | 2 | 0 | 17 | 0.054 | 59519.7 | 149.5 | 59885.6 | 60811.6 |
| attack | 44 | 42 | 42 | 0 | 0 | 0 | 0 | 1.000 | 1094.8 | 555.3 | 964.4 | 3062.8 |
| control | 44 | 42 | 20 | 0 | 3 | 0 | 19 | 0.024 | 59909.4 | 177.1 | 59831.7 | 61274.3 |
| attack | 45 | 36 | 36 | 0 | 0 | 0 | 0 | 1.000 | 765.4 | 195.7 | 555.2 | 2426.9 |
| control | 45 | 36 | 17 | 0 | 0 | 0 | 19 | 0.000 | 59360.3 | 116.6 | 59127.3 | 60718.3 |
| attack | 46 | 26 | 26 | 0 | 0 | 0 | 0 | 1.000 | 999.5 | 458.8 | 459.0 | 2781.2 |
| control | 46 | 26 | 8 | 0 | 2 | 0 | 16 | 0.000 | 59205.4 | 121.5 | 58638.6 | 60585.6 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 3.158 | [2.375, 3.939] | supported |
| Victim user-facing TTFT P95 | ms | 0.014 | [0.010, 0.017] | negative |
| Victim gateway queue time P95 | ms | 0.008 | [0.004, 0.012] | negative |
| Victim end-to-end latency P95 | ms | 0.044 | [0.041, 0.047] | negative |
| Victim offered-load SLO success | fraction of offered | 30.250 | [18.500, 42.000] | insufficient_seeds |

### Validity gates (fail closed; ADR-Q17)

Overall: **FAIL**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | FAIL | lowest arm 0.762 (min 0.95) |
| primary_metric_present | pass | 5/5 seeds have a finite Victim backend TTFT P95 (historical `ttft_p95`) |
| tokenized_context | FAIL | no pre-run tokenization check recorded |
| provenance | FAIL | server start ['None']; vllm version; model revision status not recorded |
| victim_latency_censoring | FAIL | worst arm censored fraction 0.692 (max 0.05); primary |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **n/a (protocol v1: majority-of-seeds verdict)**.

