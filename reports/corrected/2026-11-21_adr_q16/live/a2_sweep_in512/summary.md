# QuotaShift attack-effect report — `a2_sweep_in512`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/live/a2_sweep_in512/.

- Control: `matched_total_short`  ·  seeds: 5  ·  pre-registered metric: **Victim backend TTFT P95 (historical `ttft_p95`)** (`ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_sent (backend dispatch); excludes gateway queue time (ADR-Q16)
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **n/a (protocol v1: majority-of-seeds verdict)** (seeds with metric: 5).

## Victim backend TTFT P95 (historical `ttft_p95`): victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim backend TTFT P95 (historical `ttft_p95`): **2.14×**  (median 2.03×, 95% bootstrap CI [1.62, 2.69])
- **Threshold-crossing rate: 80%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 27879 tokens, 57 requests per run.
- Victim slowdown per 1k competing tokens: 0.0408
- Victim slowdown per 100 competing requests: 2.0116

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 196.59 | 128.52 | 1.53 | yes | 0/0 |
| 43 | 290.03 | 142.53 | 2.03 | yes | 0/2 |
| 44 | 266.90 | 106.98 | 2.49 | yes | 0/0 |
| 45 | 230.12 | 154.38 | 1.49 | no | 0/0 |
| 46 | 316.19 | 100.61 | 3.14 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 1.000 | 851.0 | 196.6 | 764.4 | 2398.5 |
| control | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 0.000 | 43801.6 | 128.5 | 43730.3 | 45126.1 |
| attack | 43 | 37 | 37 | 0 | 0 | 0 | 0 | 1.000 | 605.8 | 290.0 | 506.4 | 2343.4 |
| control | 43 | 37 | 20 | 0 | 2 | 0 | 15 | 0.054 | 58793.9 | 142.5 | 58714.3 | 60060.1 |
| attack | 44 | 42 | 42 | 0 | 0 | 0 | 0 | 1.000 | 790.8 | 266.9 | 671.1 | 2274.4 |
| control | 44 | 42 | 30 | 0 | 0 | 0 | 12 | 0.024 | 54758.1 | 107.0 | 54674.1 | 56025.4 |
| attack | 45 | 36 | 36 | 0 | 0 | 0 | 0 | 1.000 | 1125.3 | 230.1 | 976.3 | 2915.6 |
| control | 45 | 36 | 36 | 0 | 0 | 0 | 0 | 0.000 | 49173.1 | 154.4 | 49089.3 | 50486.5 |
| attack | 46 | 26 | 26 | 0 | 0 | 0 | 0 | 1.000 | 1105.5 | 316.2 | 997.2 | 2511.6 |
| control | 46 | 26 | 16 | 0 | 0 | 0 | 10 | 0.000 | 56301.9 | 100.6 | 55774.4 | 57572.0 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 2.139 | [1.615, 2.691] | supported |
| Victim user-facing TTFT P95 | ms | 0.017 | [0.013, 0.021] | negative |
| Victim gateway queue time P95 | ms | 0.015 | [0.011, 0.019] | negative |
| Victim end-to-end latency P95 | ms | 0.047 | [0.041, 0.053] | negative |
| Victim offered-load SLO success | fraction of offered | 30.250 | [18.500, 42.000] | insufficient_seeds |

### Validity gates (fail closed; ADR-Q17)

Overall: **FAIL**

| gate | result | detail |
|---|---|---|
| backend_error_rate | pass | worst arm 0.0000 (max 0.01) |
| http_400_rate | pass | worst arm 0.0000 (max 0.01) |
| admission_rate | pass | lowest class admission 1.000 (min 0.95) |
| competitor_completion | FAIL | lowest arm 0.919 (min 0.95) |
| primary_metric_present | pass | 5/5 seeds have a finite Victim backend TTFT P95 (historical `ttft_p95`) |
| tokenized_context | FAIL | no pre-run tokenization check recorded |
| provenance | FAIL | dirty ['True']; server start ['None']; vllm version; model revision status not recorded |
| victim_latency_censoring | FAIL | worst arm censored fraction 0.459 (max 0.05); primary |

## Verdict

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **n/a (protocol v1: majority-of-seeds verdict)**.

