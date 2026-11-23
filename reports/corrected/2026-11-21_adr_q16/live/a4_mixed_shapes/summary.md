# QuotaShift attack-effect report — `a4_mixed_shapes`

> Live target measurements.

> CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary recomputed from the original runs (reproduced exactly) and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load SLO success are POST-HOC (not pre-registered). Validity gates are reported only. Original report: reports/live/a4_mixed_shapes/.

- Control: `homogeneous_mixture`  ·  seeds: 5  ·  pre-registered metric: **Victim backend TTFT P95 (historical `ttft_p95`)** (`ttft_p95`, unit: ms)
- Definition: P95 over completed victim requests of t_first_token - t_sent (backend dispatch); excludes gateway queue time (ADR-Q16)
- **Pre-registered threshold: 1.5×** (fixed before runs; ADR-Q08), direction `increase`; CI-based classification: **n/a (protocol v1: majority-of-seeds verdict)** (seeds with metric: 5).

## Victim backend TTFT P95 (historical `ttft_p95`): victim degradation (attack vs matched control)

- Mean attack/control ratio of Victim backend TTFT P95 (historical `ttft_p95`): **1.35×**  (median 1.26×, 95% bootstrap CI [1.23, 1.47])
- **Threshold-crossing rate: 20%** of 5 seeds crossed the threshold.

### Budget-normalized effect
- Mean measured competing load: 14074 tokens, 35 requests per run.
- Victim slowdown per 1k competing tokens: 0.0246
- Victim slowdown per 100 competing requests: 0.9800

### Per-seed detail (matched pairs; values in ms)

| seed | attack (ms) | control (ms) | ratio | crosses threshold | victim timeouts (a/c) |
|---|---|---|---|---|---|
| 42 | 154.73 | 128.98 | 1.20 | no | 0/0 |
| 43 | 189.01 | 150.70 | 1.25 | no | 0/0 |
| 44 | 181.83 | 117.36 | 1.55 | yes | 0/0 |
| 45 | 183.68 | 145.68 | 1.26 | no | 0/0 |
| 46 | 163.37 | 111.09 | 1.47 | no | 0/0 |

### Victim request outcomes (post-warm-up; SLO success over offered requests)

| arm | seed | offered | completed | rejected | timed out | backend error | cancelled | SLO success / offered | user TTFT P95 ms | backend TTFT P95 ms | gateway queue P95 ms | E2E P95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attack | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 1.000 | 779.6 | 154.7 | 595.8 | 2192.0 |
| control | 42 | 33 | 33 | 0 | 0 | 0 | 0 | 1.000 | 631.5 | 129.0 | 505.4 | 1992.6 |
| attack | 43 | 37 | 37 | 0 | 0 | 0 | 0 | 1.000 | 753.5 | 189.0 | 659.2 | 2129.6 |
| control | 43 | 37 | 37 | 0 | 0 | 0 | 0 | 1.000 | 690.8 | 150.7 | 628.9 | 2030.2 |
| attack | 44 | 42 | 42 | 0 | 0 | 0 | 0 | 0.857 | 2488.5 | 181.8 | 2364.1 | 3948.7 |
| control | 44 | 42 | 42 | 0 | 0 | 0 | 0 | 0.905 | 2357.5 | 117.4 | 2274.3 | 3836.7 |
| attack | 45 | 36 | 36 | 0 | 0 | 0 | 0 | 0.944 | 1836.1 | 183.7 | 1726.4 | 3184.4 |
| control | 45 | 36 | 36 | 0 | 0 | 0 | 0 | 0.944 | 1735.9 | 145.7 | 1675.3 | 3094.3 |
| attack | 46 | 26 | 26 | 0 | 0 | 0 | 0 | 1.000 | 1512.3 | 163.4 | 1411.9 | 2940.8 |
| control | 46 | 26 | 26 | 0 | 0 | 0 | 0 | 1.000 | 1514.0 | 111.1 | 1452.3 | 2929.3 |

### Secondary endpoints (reported beside the primary; no claim)

| endpoint | unit | mean ratio a/c | 95% CI | two-sided label (diagnostic) |
|---|---|---|---|---|
| Victim backend TTFT P95 | ms | 1.347 | [1.234, 1.475] | negative |
| Victim user-facing TTFT P95 | ms | 1.088 | [1.029, 1.164] | negative |
| Victim gateway queue time P95 | ms | 1.054 | [1.001, 1.123] | negative |
| Victim end-to-end latency P95 | ms | 1.042 | [1.018, 1.072] | negative |
| Victim offered-load SLO success | fraction of offered | 0.989 | [0.968, 1.000] | negative |

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

