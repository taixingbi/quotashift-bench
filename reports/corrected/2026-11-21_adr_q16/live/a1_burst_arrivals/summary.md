# QuotaShift attack-effect report — `a1_burst_arrivals`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/live/a1_burst_arrivals/.

- Control: `uniform_arrivals`  ·  seeds: 5  ·  pre-registered metric: **Victim backend TTFT P95 (historical `ttft_p95`)** (`ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_sent (backend dispatch); excludes gateway queue time (ADR-Q16)
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **n/a (protocol v1: majority-of-seeds verdict)** (seeds with metric: 5).

## Victim backend TTFT P95 (historical `ttft_p95`): victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim backend TTFT P95 (historical `ttft_p95`): **1.58×**  (median 1.51×, 95% bootstrap CI [1.45, 1.79])
- **Threshold-crossing rate: 60%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 13322 tokens, 102 requests per run.
- Victim slowdown per 1k competing tokens: 0.0437
- Victim slowdown per 100 competing requests: 0.5725

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 127.20 | 87.52 | 1.45 | no | 0/0 |
| 43 | 145.67 | 95.56 | 1.52 | yes | 0/0 |
| 44 | 143.87 | 100.88 | 1.43 | no | 0/0 |
| 45 | 168.01 | 84.28 | 1.99 | yes | 0/0 |
| 46 | 124.10 | 82.13 | 1.51 | yes | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 1.000 | 1418.6 | 127.2 | 1315.6 | 2677.4 |
| control | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 1.000 | 746.9 | 87.5 | 686.8 | 2008.7 |
| attack | 43 | 37 | 37 | 0 | 0 | 0 | 0 | 0.486 | 4326.0 | 145.7 | 4231.7 | 5662.7 |
| control | 43 | 37 | 37 | 0 | 0 | 0 | 0 | 1.000 | 587.7 | 95.6 | 512.1 | 1859.0 |
| attack | 44 | 42 | 42 | 0 | 0 | 0 | 0 | 0.905 | 2729.7 | 143.9 | 2606.9 | 4087.9 |
| control | 44 | 42 | 42 | 0 | 0 | 0 | 0 | 1.000 | 274.4 | 100.9 | 210.1 | 1563.4 |
| attack | 45 | 36 | 36 | 0 | 0 | 0 | 0 | 0.778 | 2620.2 | 168.0 | 2506.6 | 3933.0 |
| control | 45 | 36 | 36 | 0 | 0 | 0 | 0 | 1.000 | 686.8 | 84.3 | 607.5 | 1957.1 |
| attack | 46 | 26 | 26 | 0 | 0 | 0 | 0 | 0.538 | 5365.5 | 124.1 | 5272.2 | 6675.8 |
| control | 46 | 26 | 26 | 0 | 0 | 0 | 0 | 1.000 | 495.5 | 82.1 | 434.8 | 1764.7 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.582 | [1.451, 1.789] | inconclusive |
| Victim user-facing TTFT P95 | ms | 6.771 | [3.758, 9.783] | supported |
| Victim gateway queue time P95 | ms | 7.768 | [4.069, 11.467] | supported |
| Victim end-to-end latency P95 | ms | 2.557 | [1.823, 3.281] | supported |
| Victim offered-load SLO success | fraction of offered | 0.741 | [0.566, 0.917] | negative |

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

Under matched budgets, the victim degradation crosses the pre-registered threshold on a majority of seeds.
Pre-registered CI classification: **n/a (protocol v1: majority-of-seeds verdict)**.

