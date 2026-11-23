# QuotaShift attack-effect report — `a2_sweep_in128`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/live/a2_sweep_in128/.

- Control: `matched_total_short`  ·  seeds: 5  ·  pre-registered metric: **Victim backend TTFT P95 (historical `ttft_p95`)** (`ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_sent (backend dispatch); excludes gateway queue time (ADR-Q16)
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **n/a (protocol v1: majority-of-seeds verdict)** (seeds with metric: 5).

## Victim backend TTFT P95 (historical `ttft_p95`): victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim backend TTFT P95 (historical `ttft_p95`): **1.73×**  (median 1.93×, 95% bootstrap CI [1.30, 2.05])
- **Threshold-crossing rate: 80%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 30222 tokens, 206 requests per run.
- Victim slowdown per 1k competing tokens: 0.0242
- Victim slowdown per 100 competing requests: 0.3554

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 271.80 | 297.34 | 0.91 | no | 0/5 |
| 43 | 230.56 | 111.50 | 2.07 | yes | 0/1 |
| 44 | 156.86 | 81.39 | 1.93 | yes | 0/0 |
| 45 | 181.04 | 109.80 | 1.65 | yes | 0/1 |
| 46 | 173.48 | 82.65 | 2.10 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 0.545 | 17340.9 | 271.8 | 17188.2 | 19113.5 |
| control | 42 | 33 | 15 | 0 | 5 | 0 | 13 | 0.000 | 60069.1 | 297.3 | 59852.3 | 61421.2 |
| attack | 43 | 37 | 37 | 0 | 0 | 0 | 0 | 0.459 | 4416.5 | 230.6 | 4303.6 | 5891.5 |
| control | 43 | 37 | 19 | 0 | 1 | 0 | 17 | 0.054 | 52419.7 | 111.5 | 59020.6 | 53730.0 |
| attack | 44 | 42 | 42 | 0 | 0 | 0 | 0 | 0.810 | 2930.9 | 156.9 | 2835.0 | 4429.2 |
| control | 44 | 42 | 23 | 0 | 0 | 0 | 19 | 0.024 | 53480.3 | 81.4 | 55195.8 | 54844.4 |
| attack | 45 | 36 | 36 | 0 | 0 | 0 | 0 | 0.500 | 3652.2 | 181.0 | 3551.5 | 5105.2 |
| control | 45 | 36 | 15 | 0 | 1 | 0 | 20 | 0.000 | 58048.4 | 109.8 | 57787.0 | 59345.3 |
| attack | 46 | 26 | 26 | 0 | 0 | 0 | 0 | 0.808 | 2343.7 | 173.5 | 2227.3 | 3796.6 |
| control | 46 | 26 | 11 | 0 | 0 | 0 | 15 | 0.000 | 58480.6 | 82.7 | 57963.8 | 59751.2 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.731 | [1.298, 2.052] | inconclusive |
| Victim user-facing TTFT P95 | ms | 0.106 | [0.051, 0.198] | negative |
| Victim gateway queue time P95 | ms | 0.102 | [0.048, 0.197] | negative |
| Victim end-to-end latency P95 | ms | 0.130 | [0.075, 0.221] | negative |
| Victim offered-load SLO success | fraction of offered | 21.250 | [8.500, 34.000] | insufficient_seeds |

### Validity gates (fail closed; ADR-Q17)

Overall: **FAIL**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | FAIL | lowest arm 0.875 (min 0.95) |
| primary_metric_present | pass | 5/5 seeds have a finite Victim backend TTFT P95 (historical `ttft_p95`) |
| tokenized_context | FAIL | no pre-run tokenization check recorded |
| provenance | FAIL | git sha ['3d4c40f6bf1c2a27133d850740f05992a1266827', '680a0ffd094497c7bfde352f48d58040ab930319']; dirty ['True']; server start ['None']; vllm version; model revision status not recorded |
| victim_latency_censoring | FAIL | worst arm censored fraction 0.583 (max 0.05); primary |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **n/a (protocol v1: majority-of-seeds verdict)**.

