# QuotaShift attack-effect report — `a3_decode_heavy`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/live/a3_decode_heavy/.

- Control: `matched_total_short`  ·  seeds: 5  ·  pre-registered metric: **Victim backend TTFT P95 (historical `ttft_p95`)** (`ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_sent (backend dispatch); excludes gateway queue time (ADR-Q16)
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **n/a (protocol v1: majority-of-seeds verdict)** (seeds with metric: 5).

## Victim backend TTFT P95 (historical `ttft_p95`): victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim backend TTFT P95 (historical `ttft_p95`): **1.06×**  (median 1.11×, 95% bootstrap CI [0.87, 1.26])
- **Threshold-crossing rate: 0%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 9998 tokens, 35 requests per run.
- Victim slowdown per 1k competing tokens: 0.0062
- Victim slowdown per 100 competing requests: 0.1739

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 134.14 | 154.01 | 0.87 | no | 0/0 |
| 43 | 123.45 | 108.98 | 1.13 | no | 0/0 |
| 44 | 124.05 | 86.39 | 1.44 | no | 0/0 |
| 45 | 124.49 | 164.59 | 0.76 | no | 0/0 |
| 46 | 162.74 | 146.40 | 1.11 | no | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 0.939 | 1783.4 | 134.1 | 1677.9 | 3069.9 |
| control | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 0.727 | 3420.1 | 154.0 | 3336.5 | 4767.4 |
| attack | 43 | 37 | 37 | 0 | 0 | 0 | 0 | 0.703 | 2842.2 | 123.5 | 2739.5 | 4120.5 |
| control | 43 | 37 | 37 | 0 | 0 | 0 | 0 | 0.405 | 9807.2 | 109.0 | 9741.6 | 11164.4 |
| attack | 44 | 42 | 42 | 0 | 0 | 0 | 0 | 0.429 | 5607.6 | 124.0 | 5514.0 | 6925.9 |
| control | 44 | 42 | 42 | 0 | 0 | 0 | 0 | 0.262 | 13725.9 | 86.4 | 13647.8 | 15061.9 |
| attack | 45 | 36 | 36 | 0 | 0 | 0 | 0 | 0.750 | 4848.6 | 124.5 | 4743.0 | 6140.4 |
| control | 45 | 36 | 36 | 0 | 0 | 0 | 0 | 0.750 | 3244.2 | 164.6 | 3158.4 | 4597.5 |
| attack | 46 | 26 | 26 | 0 | 0 | 0 | 0 | 0.654 | 3470.4 | 162.7 | 3365.3 | 4741.3 |
| control | 46 | 26 | 26 | 0 | 0 | 0 | 0 | 0.692 | 5674.9 | 146.4 | 5601.2 | 7042.5 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.062 | [0.873, 1.258] | negative |
| Victim user-facing TTFT P95 | ms | 0.665 | [0.378, 1.101] | negative |
| Victim gateway queue time P95 | ms | 0.658 | [0.370, 1.102] | negative |
| Victim end-to-end latency P95 | ms | 0.696 | [0.448, 1.028] | negative |
| Victim offered-load SLO success | fraction of offered | 1.321 | [1.036, 1.606] | inconclusive |

### Validity gates (fail closed; ADR-Q17)

Overall: **FAIL**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | pass | lowest arm 1.000 (min 0.95) |
| primary_metric_present | pass | 5/5 seeds have a finite Victim backend TTFT P95 (historical `ttft_p95`) |
| tokenized_context | FAIL | no pre-run tokenization check recorded |
| provenance | FAIL | server start ['None']; vllm version; model revision status not recorded |
| victim_latency_censoring | pass | worst arm censored fraction 0.000 (max 0.05); primary |

## Verdict

Under matched budgets, the victim degradation does NOT reach the pre-registered threshold on a majority of seeds (reported as a negative result, per the plan).
Pre-registered CI classification: **n/a (protocol v1: majority-of-seeds verdict)**.

