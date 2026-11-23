# QuotaShift attack-effect report — `a5_stateful_sequence`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/live/stateful_sequences/.

- Control: `shuffled_phase_order`  ·  seeds: 5  ·  pre-registered metric: **Victim backend TTFT P95 (historical `ttft_p95`)** (`ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_sent (backend dispatch); excludes gateway queue time (ADR-Q16)
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **n/a (protocol v1: majority-of-seeds verdict)** (seeds with metric: 5).

## Victim backend TTFT P95 (historical `ttft_p95`): victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim backend TTFT P95 (historical `ttft_p95`): **1.28×**  (median 1.39×, 95% bootstrap CI [1.08, 1.46])
- **Threshold-crossing rate: 20%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 27630 tokens, 56 requests per run.
- Victim slowdown per 1k competing tokens: 0.0101
- Victim slowdown per 100 competing requests: 0.4960

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 211.17 | 136.71 | 1.54 | yes | 0/0 |
| 43 | 193.94 | 168.98 | 1.15 | no | 0/0 |
| 44 | 186.49 | 134.40 | 1.39 | no | 0/0 |
| 45 | 193.85 | 137.41 | 1.41 | no | 0/0 |
| 46 | 187.03 | 205.99 | 0.91 | no | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 71 | 71 | 0 | 0 | 0 | 0 | 1.000 | 268.1 | 211.2 | 0.0 | 1775.3 |
| control | 42 | 71 | 71 | 0 | 0 | 0 | 0 | 1.000 | 158.7 | 136.7 | 0.0 | 1459.8 |
| attack | 43 | 75 | 75 | 0 | 0 | 0 | 0 | 1.000 | 274.0 | 193.9 | 89.4 | 2257.0 |
| control | 43 | 75 | 75 | 0 | 0 | 0 | 0 | 1.000 | 196.5 | 169.0 | 72.9 | 1457.3 |
| attack | 44 | 78 | 78 | 0 | 0 | 0 | 0 | 0.974 | 393.1 | 186.5 | 44.0 | 2212.1 |
| control | 44 | 78 | 78 | 0 | 0 | 0 | 0 | 1.000 | 249.8 | 134.4 | 144.2 | 1510.0 |
| attack | 45 | 76 | 76 | 0 | 0 | 0 | 0 | 0.987 | 1652.7 | 193.8 | 1547.3 | 3205.8 |
| control | 45 | 76 | 76 | 0 | 0 | 0 | 0 | 0.987 | 1070.9 | 137.4 | 1006.5 | 2334.1 |
| attack | 46 | 57 | 57 | 0 | 0 | 0 | 0 | 1.000 | 656.2 | 187.0 | 560.1 | 1957.1 |
| control | 46 | 57 | 57 | 0 | 0 | 0 | 0 | 1.000 | 230.8 | 206.0 | 0.0 | 1495.6 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.280 | [1.083, 1.460] | negative |
| Victim user-facing TTFT P95 | ms | 1.809 | [1.484, 2.329] | inconclusive |
| Victim gateway queue time P95 | ms | 1.023 | [0.305, 1.537] | insufficient_seeds |
| Victim end-to-end latency P95 | ms | 1.382 | [1.283, 1.482] | negative |
| Victim offered-load SLO success | fraction of offered | 0.995 | [0.985, 1.000] | negative |

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

