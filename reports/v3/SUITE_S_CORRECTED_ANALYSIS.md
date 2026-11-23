# Suite S corrected analysis (ADR-Q16/Q17, protocol v3.1)

2026-11-21, offline re-analysis plus the two amended long-context GPU blocks. Code: `53d0ed3` (corrections, gates,
amendment) and `02448f8` (re-analysis script, smoke salt r2), both on `main`. Original data is archived with
SHA-256 checksums in `archive/2026-11-21_suite_s_original/`, and no historical file was modified. Corrected
per-report outputs are in `reports/corrected/2026-11-21_adr_q16/<original path>/`, and v3.1 outputs in `reports/v3_1/`.

**How to read this document.** "Historical" means the pre-registered primary, recomputed from the original runs with the
original metric key. It is reproduced exactly and its classification is unchanged. "Post-hoc" marks every value that was
not pre-registered for its series: user-facing TTFT, gateway queue, offered-load SLO success, energy per realized token
and the validity gates. Post-hoc values never replace a historical classification. A normalized energy ratio is a cost per
unit of work. It is never a victim-performance effect.

## 0. Which original findings remain supported

| finding | historical / pre-registered | status after correction |
|---|---|---|
| A1 burst arrivals (v1) | backend TTFT 1.590 [1.532, 1.655] | Stands as a backend-TTFT result. Post-hoc user-facing TTFT is larger (5.786 [4.515, 7.141]), with no victim censoring in either arm. The degradation is robust to the TTFT definition. |
| A2 prefill concentration (v1; headline 3.19×, n=20) | backend TTFT 3.191 [2.663, 3.746] | **Not supported as a victim-degradation finding.** The historical value reproduces, but the matched_total_short control floods the 8-slot gateway: only 279/707 control victims completed (358 cancelled at run cutoff, 70 gateway timeouts). The control's backend TTFT therefore covers its fastest survivors only. Post-hoc user-facing TTFT ratio 0.018 [0.014, 0.024]; offered-load SLO success 0.986 (attack) vs 0.014 (control). It fails the censoring gate (54–60% of control victims censored). Same for the A2 sweep points. |
| A3 decode, A4 mixed, A5 stateful (v1) | backend TTFT 1.06× / 1.35× / 1.28× | Unchanged and uncensored. Post-hoc user-facing TTFT: A3 0.67×, A4 1.09×, A5 1.81× (below). |
| A7-V A/A noise floor (S0) | 0.962 [0.918, 1.006] negative | Stands. The user-facing ratio is 1.00 [0.99, 1.01]; the precision gate passes under both definitions. |
| A7 cache state (S1 exploratory / S1′ confirmatory) | backend TTFT 0.615 [0.574, 0.667] supported (victim faster) | **Stands** under both definitions (user-facing 0.583 [0.463, 0.703]), with no censoring and the manipulation check passed. |
| A8a cancel/timeout, A8b retry churn | negative / negative | Stand (one-sided `increase`). Post-hoc user-facing TTFT is far *lower* in the attack arm (0.11×, 0.22×), because client cancellations free inflight slots and control victims queue in the gateway. The victim is not degraded under either definition. |
| A9 token-matched prefill / decode / prefix reuse (energy) | negative / negative / negative | Stand as computed. The controls of prefill and prefix-reuse completed only 93–94% of their competitor requests (gateway timeouts), so they fail the ADR-Q17 completion gate post-hoc. Read those two as `negative, control incompletely executed`. |
| A9 rate-matched prefill / decode / prefix reuse (energy) | supported / supported / supported (ratio < 0.8) | Stand as computed. The cause is the **denominator**: arm energy changes by −2% to +8% while authorized tokens rise 1.7–3.6×. These are lower J per authorized token, not victim improvements; victim backend TTFT is *worse* in rate-matched prefill (§3). |
| A9 long context v3 (token- and rate-matched) | inconclusive / supported | **Invalid** (112/116 competitor requests HTTP 400). Superseded by v3.1. |
| A9 long context v3.1, rate-matched (new) | 0.213 [0.185, 0.241] supported | **Valid**: every ADR-Q17 gate passed. Denominator-driven: energy +13% for 5.5× authorized tokens (§3.3). |
| A9 long context v3.1, token-matched (new) | invalid (computed before gates: negative, 0.943 [0.917, 0.973]) | **Invalid** under the pre-registered competitor-completion gate. The short control could not execute its token budget (74.6–76.0% of competitor requests completed in seeds 45–46; gateway queue timeouts). Every other gate passed. |

## 1. Reproduction and both TTFT definitions (all 24 live reports)

All 24 historical primaries reproduce exactly (|Δ| ≤ 1e-9 in mean ratio and CI): **24/24**. All v3 classifications are unchanged. v1 reports had no CI classification (majority-of-seeds verdict), and none is added.

| report | series | seeds | historical primary ratio [95% CI] | historical class | user-facing TTFT ratio [CI] (post-hoc) | gateway-queue P95 ratio (post-hoc) | SLO success / offered A / C (post-hoc) | ADR-Q17 gates failed (post-hoc) |  |
|---|---|---|---|---|---|---|---|---|---|
| a1_burst_arrivals | v1 | 5 | 1.582 [1.451, 1.789] | n/a (protocol v1: majority-of-seeds verdict) | 6.771 [3.758, 9.783] | 7.768 [4.069, 11.467] | 0.741 / 1.000 | none |  |
| a1_burst_arrivals_r20 | v1 | 20 | 1.590 [1.532, 1.655] | n/a (protocol v1: majority-of-seeds verdict) | 5.786 [4.515, 7.141] | 13.799 [5.102, 29.800] | 0.740 / 0.947 | none |  |
| a2_prefill_heavy | v1 | 5 | 3.158 [2.375, 3.939] | n/a (protocol v1: majority-of-seeds verdict) | 0.014 [0.010, 0.017] | 0.008 [0.004, 0.012] | 1.000 / 0.016 | competitor_completion, victim_latency_censoring |  |
| a2_prefill_heavy_r20 | v1 | 20 | 3.191 [2.663, 3.746] | n/a (protocol v1: majority-of-seeds verdict) | 0.018 [0.014, 0.024] | 0.013 [0.009, 0.019] | 0.986 / 0.014 | competitor_completion, victim_latency_censoring |  |
| a2_sweep_in128 | v1 | 5 | 1.731 [1.298, 2.052] | n/a (protocol v1: majority-of-seeds verdict) | 0.106 [0.051, 0.198] | 0.102 [0.048, 0.197] | 0.624 / 0.016 | competitor_completion, victim_latency_censoring |  |
| a2_sweep_in256 | v1 | 5 | 2.221 [1.538, 2.905] | n/a (protocol v1: majority-of-seeds verdict) | 0.027 [0.015, 0.039] | 0.024 [0.013, 0.037] | 0.967 / 0.016 | competitor_completion, victim_latency_censoring |  |
| a2_sweep_in512 | v1 | 5 | 2.139 [1.615, 2.691] | n/a (protocol v1: majority-of-seeds verdict) | 0.017 [0.013, 0.021] | 0.015 [0.011, 0.019] | 1.000 / 0.016 | competitor_completion, victim_latency_censoring |  |
| a2_sweep_in768 | v1 | 5 | 2.999 [2.526, 3.473] | n/a (protocol v1: majority-of-seeds verdict) | 0.012 [0.008, 0.015] | 0.007 [0.003, 0.011] | 0.994 / 0.016 | competitor_completion, victim_latency_censoring |  |
| a3_decode_heavy | v1 | 5 | 1.062 [0.873, 1.258] | n/a (protocol v1: majority-of-seeds verdict) | 0.665 [0.378, 1.101] | 0.658 [0.370, 1.102] | 0.695 / 0.567 | none |  |
| a4_mixed_shapes | v1 | 5 | 1.347 [1.234, 1.475] | n/a (protocol v1: majority-of-seeds verdict) | 1.088 [1.029, 1.164] | 1.054 [1.001, 1.123] | 0.960 / 0.970 | none |  |
| stateful_sequences | v1 | 5 | 1.280 [1.083, 1.460] | n/a (protocol v1: majority-of-seeds verdict) | 1.809 [1.484, 2.329] | 1.023 [0.305, 1.537] | 0.992 / 0.997 | none |  |
| a7v_cache_isolation_validation | v3 | 5 | 0.962 [0.918, 1.006] | negative | 0.999 [0.993, 1.009] | 1.014 [1.004, 1.024] | 0.866 / 0.867 | none |  |
| a7_prefix_cache | v3 | 5 | 0.607 [0.556, 0.659] | supported | 0.558 [0.449, 0.661] | 0.453 [0.264, 0.601] | 0.996 / 0.990 | none |  |
| a7_prefix_cache_reset | v3 | 5 | 0.615 [0.574, 0.667] | supported | 0.583 [0.463, 0.703] | 0.456 [0.288, 0.593] | 0.996 / 0.990 | none |  |
| a8_lifecycle_churn | v3 | 5 | 0.975 [0.873, 1.065] | negative | 0.108 [0.078, 0.140] | 0.020 [0.000, 0.059] | 1.000 / 0.936 | none |  |
| a8_retry_churn | v3 | 5 | 1.116 [0.980, 1.231] | negative | 0.220 [0.134, 0.291] | 0.211 [0.127, 0.282] | 0.932 / 0.386 | none |  |
| a9_tok_prefill | v3 | 5 | 0.904 [0.891, 0.916] | negative | 0.012 [0.011, 0.013] | 0.001 [0.000, 0.002] | 1.000 / 0.023 | competitor_completion |  |
| a9_tok_decode | v3 | 5 | 1.099 [1.072, 1.125] | negative | 0.375 [0.244, 0.506] | 0.365 [0.241, 0.489] | 0.795 / 0.535 | none |  |
| a9_tok_longctx | v3 | 5 | 0.784 [0.759, 0.809] | inconclusive | 0.004 [0.003, 0.005] | 0.000 [0.000, 0.000] | 1.000 / 0.060 | backend_error_rate, http_400_rate, competitor_completion | INVALID |
| a9_tok_prefix_reuse | v3 | 5 | 0.859 [0.838, 0.882] | negative | 0.004 [0.003, 0.004] | 0.000 [0.000, 0.000] | 1.000 / 0.025 | competitor_completion |  |
| a9_rate_prefill | v3 | 5 | 0.289 [0.277, 0.302] | supported | 3.612 [2.576, 4.657] | — (control queue 0) | 1.000 / 1.000 | none |  |
| a9_rate_decode | v3 | 5 | 0.624 [0.611, 0.637] | supported | 18.363 [14.847, 21.879] | 580.798 [580.798, 580.798] | 0.808 / 1.000 | none |  |
| a9_rate_longctx | v3 | 5 | 0.181 [0.153, 0.210] | supported | 1.120 [0.668, 1.527] | — (control queue 0) | 1.000 / 1.000 | backend_error_rate, http_400_rate, competitor_completion | INVALID |
| a9_rate_prefix_reuse | v3 | 5 | 0.272 [0.261, 0.285] | supported | 1.246 [1.184, 1.318] | — (control queue 0) | 1.000 / 1.000 | none |  |

The historical primary is victim backend TTFT P95 (`ttft_p95`) for A1–A8, and GPU dynamic energy per 1,000 authorized tokens for A9. `tokenized_context` and `provenance` cannot be satisfied by runs made before ADR-Q17 (no pre-run tokenization; dirty trees, and no model-revision status recorded), so they are left out of the gate column above. They are listed in each corrected report.

## 2. Victim request outcomes per scenario (sums over seeds, post-warm-up)

| report | A offered | A completed | A rejected | A timed out | A cancelled | C offered | C completed | C rejected | C timed out | C cancelled | A censored | C censored |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a1_burst_arrivals | 174 | 174 | 0 | 0 | 0 | 174 | 174 | 0 | 0 | 0 | 0.000 | 0.000 |
| a1_burst_arrivals_r20 | 707 | 707 | 0 | 0 | 0 | 707 | 707 | 0 | 0 | 0 | 0.000 | 0.000 |
| a2_prefill_heavy | 174 | 174 | 0 | 0 | 0 | 174 | 80 | 0 | 10 | 84 | 0.000 | 0.548 |
| a2_prefill_heavy_r20 | 707 | 707 | 0 | 0 | 0 | 707 | 279 | 0 | 70 | 358 | 0.000 | 0.605 |
| a2_sweep_in128 | 174 | 174 | 0 | 0 | 0 | 174 | 83 | 0 | 7 | 84 | 0.000 | 0.529 |
| a2_sweep_in256 | 174 | 174 | 0 | 0 | 0 | 174 | 107 | 0 | 4 | 63 | 0.000 | 0.373 |
| a2_sweep_in512 | 174 | 174 | 0 | 0 | 0 | 174 | 135 | 0 | 2 | 37 | 0.000 | 0.226 |
| a2_sweep_in768 | 174 | 174 | 0 | 0 | 0 | 174 | 137 | 0 | 2 | 35 | 0.000 | 0.187 |
| a3_decode_heavy | 174 | 174 | 0 | 0 | 0 | 174 | 174 | 0 | 0 | 0 | 0.000 | 0.000 |
| a4_mixed_shapes | 174 | 174 | 0 | 0 | 0 | 174 | 174 | 0 | 0 | 0 | 0.000 | 0.000 |
| stateful_sequences | 357 | 357 | 0 | 0 | 0 | 357 | 357 | 0 | 0 | 0 | 0.000 | 0.000 |
| a7v_cache_isolation_validation | 706 | 706 | 0 | 0 | 0 | 706 | 706 | 0 | 0 | 0 | 0.000 | 0.000 |
| a7_prefix_cache | 706 | 706 | 0 | 0 | 0 | 706 | 706 | 0 | 0 | 0 | 0.000 | 0.000 |
| a7_prefix_cache_reset | 706 | 706 | 0 | 0 | 0 | 706 | 706 | 0 | 0 | 0 | 0.000 | 0.000 |
| a8_lifecycle_churn | 541 | 541 | 0 | 0 | 0 | 541 | 541 | 0 | 0 | 0 | 0.000 | 0.000 |
| a8_retry_churn | 541 | 541 | 0 | 0 | 0 | 541 | 541 | 0 | 0 | 0 | 0.000 | 0.000 |
| a9_tok_prefill | 541 | 541 | 0 | 0 | 0 | 541 | 529 | 0 | 12 | 0 | 0.000 | 0.021 |
| a9_tok_decode | 541 | 541 | 0 | 0 | 0 | 541 | 541 | 0 | 0 | 0 | 0.000 | 0.000 |
| a9_tok_longctx | 541 | 541 | 0 | 0 | 0 | 541 | 505 | 0 | 36 | 0 | 0.000 | 0.065 |
| a9_tok_prefix_reuse | 541 | 541 | 0 | 0 | 0 | 541 | 528 | 0 | 13 | 0 | 0.000 | 0.023 |
| a9_rate_prefill | 541 | 541 | 0 | 0 | 0 | 541 | 541 | 0 | 0 | 0 | 0.000 | 0.000 |
| a9_rate_decode | 541 | 541 | 0 | 0 | 0 | 541 | 541 | 0 | 0 | 0 | 0.000 | 0.000 |
| a9_rate_longctx | 541 | 541 | 0 | 0 | 0 | 541 | 541 | 0 | 0 | 0 | 0.000 | 0.000 |
| a9_rate_prefix_reuse | 541 | 541 | 0 | 0 | 0 | 541 | 541 | 0 | 0 | 0 | 0.000 | 0.000 |

Victim `cancelled` here means the run cutoff: requests were still queued in the gateway when the arm ended (`terminal_detail = run_cutoff`). Victim timeouts are `gateway_queue_timeout` (60 s). Every censored victim belongs to a control arm that sends many short competitor requests through the 8-slot gateway (`matched_total_short`, A2/A9-tok). Attack arms censor no victims.

## 3. A9 energy analysis

Primary (pre-registered): GPU dynamic energy over the arm window, divided by authorized tokens (planned input + requested output of every request, victims included). In v1–v3 authorized tokens are planned whitespace words; in v3.1 they are real Qwen2.5 tokens, so planned = realized there. The token-matched (`a9_tok_*`) and rate-matched (`a9_rate_*`) series are never pooled.

### 3.1 Token-matched series (valid v3 blocks)

**Absolute and normalized energy, and work (mean of 5 seeds)**

| block | arm | dyn. energy kJ (arm window) | dyn. energy kJ (incl. tail) | authorized tok | realized tok | J/1k auth | J/1k auth (incl. tail) | J/1k realized | comp. authorized tok | comp. admitted tok | comp. completed tok | GPU W mean | GPU util % | engine busy s | engine service s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a9_tok_prefill | attack | 32.37 | 34.54 | 85658 | 165372 | 380.4 | 405.9 | 197.1 | 71408 | 71408 | 71408 | 303 | 87.6 | 99.6 | 303 |
| a9_tok_prefill | control | 35.84 | 38.03 | 85649 | 125611 | 420.9 | 446.6 | 285.4 | 71398 | 71398 | 66355 | 316 | 99.2 | 125.5 | 964 |
| a9_tok_decode | attack | 34.59 | 36.77 | 51894 | 66438 | 669.5 | 711.7 | 522.7 | 37643 | 37643 | 37643 | 310 | 98.9 | 123.4 | 805 |
| a9_tok_decode | control | 31.49 | 33.63 | 51882 | 81283 | 609.9 | 651.4 | 389.3 | 37632 | 37632 | 37632 | 298 | 88.0 | 104.6 | 616 |
| a9_tok_prefix_reuse | attack | 30.52 | 32.69 | 85658 | 108512 | 359.0 | 384.5 | 283.2 | 71408 | 71408 | 71408 | 288 | 80.8 | 93.8 | 216 |
| a9_tok_prefix_reuse | control | 35.56 | 37.77 | 85649 | 125955 | 417.5 | 443.4 | 282.4 | 71398 | 71398 | 66611 | 316 | 99.5 | 125.7 | 970 |

**Per-seed attack/control ratios (mean [95% bootstrap CI]); the J/1k-authorized column is the pre-registered primary**

| block | absolute dyn. energy | authorized tokens | J/1k authorized (primary) | J/1k auth incl. tail | J/1k realized (post-hoc) | engine service s |
|---|---|---|---|---|---|---|
| a9_tok_prefill | 0.904 [0.891, 0.916] | 1.000 [1.000, 1.001] | 0.904 [0.891, 0.916] negative | 0.909 [0.896, 0.920] | 0.691 [0.647, 0.734] | 0.314 [0.295, 0.334] |
| a9_tok_decode | 1.099 [1.072, 1.126] | 1.000 [1.000, 1.001] | 1.099 [1.072, 1.125] negative | 1.093 [1.069, 1.119] | 1.344 [1.310, 1.379] | 1.306 [1.288, 1.329] |
| a9_tok_prefix_reuse | 0.859 [0.838, 0.882] | 1.000 [1.000, 1.001] | 0.859 [0.838, 0.882] negative | 0.866 [0.845, 0.889] | 1.003 [0.937, 1.069] | 0.222 [0.213, 0.230] |

**Victim latency and completion (secondary; mean of 5 seeds)**

| block | arm | victim user TTFT P95 ms | victim backend TTFT P95 ms | victim E2E P95 ms | victim completion rate | victim timeout rate | victim SLO success / offered | competitor completion rate |
|---|---|---|---|---|---|---|---|---|
| a9_tok_prefill | attack | 642 | 601 | 3134 | 1.000 | 0.000 | 1.000 | 1.000 |
| a9_tok_prefill | control | 52535 | 339 | 53886 | 0.978 | 0.022 | 0.023 | 0.929 |
| a9_tok_decode | attack | 3036 | 198 | 4360 | 1.000 | 0.000 | 0.795 | 1.000 |
| a9_tok_decode | control | 10372 | 227 | 11800 | 1.000 | 0.000 | 0.535 | 1.000 |
| a9_tok_prefix_reuse | attack | 182 | 180 | 1694 | 1.000 | 0.000 | 1.000 | 1.000 |
| a9_tok_prefix_reuse | control | 52288 | 215 | 53713 | 0.976 | 0.024 | 0.025 | 0.933 |

### 3.2 Rate-matched series (valid v3 blocks)

**Absolute and normalized energy, and work (mean of 5 seeds)**

| block | arm | dyn. energy kJ (arm window) | dyn. energy kJ (incl. tail) | authorized tok | realized tok | J/1k auth | J/1k auth (incl. tail) | J/1k realized | comp. authorized tok | comp. admitted tok | comp. completed tok | GPU W mean | GPU util % | engine busy s | engine service s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a9_rate_prefill | attack | 32.44 | 34.58 | 85658 | 165372 | 381.4 | 406.6 | 197.6 | 71408 | 71408 | 71408 | 302 | 87.0 | 99.4 | 302 |
| a9_rate_prefill | control | 31.31 | 33.52 | 23799 | 37510 | 1320.1 | 1413.0 | 837.7 | 9549 | 9549 | 9549 | 293 | 85.8 | 103.1 | 254 |
| a9_rate_decode | attack | 34.77 | 36.96 | 51894 | 66268 | 673.0 | 715.5 | 526.5 | 37643 | 37643 | 37643 | 311 | 99.0 | 123.5 | 800 |
| a9_rate_decode | control | 32.21 | 34.42 | 29969 | 47134 | 1077.9 | 1151.9 | 685.4 | 15718 | 15718 | 15718 | 302 | 91.5 | 109.7 | 326 |
| a9_rate_prefix_reuse | attack | 30.54 | 32.72 | 85658 | 108512 | 359.3 | 384.9 | 283.4 | 71408 | 71408 | 71408 | 288 | 81.4 | 93.5 | 216 |
| a9_rate_prefix_reuse | control | 31.27 | 33.50 | 23799 | 37510 | 1318.6 | 1412.5 | 836.8 | 9549 | 9549 | 9549 | 294 | 86.1 | 100.9 | 254 |

**Per-seed attack/control ratios (mean [95% bootstrap CI]); the J/1k-authorized column is the pre-registered primary**

| block | absolute dyn. energy | authorized tokens | J/1k authorized (primary) | J/1k auth incl. tail | J/1k realized (post-hoc) | engine service s |
|---|---|---|---|---|---|---|
| a9_rate_prefill | 1.036 [1.026, 1.045] | 3.594 [3.446, 3.743] | 0.289 [0.277, 0.302] supported | 0.288 [0.275, 0.301] | 0.236 [0.225, 0.248] | 1.187 [1.154, 1.222] |
| a9_rate_decode | 1.080 [1.063, 1.097] | 1.731 [1.707, 1.758] | 0.624 [0.611, 0.637] supported | 0.621 [0.608, 0.633] | 0.768 [0.755, 0.782] | 2.451 [2.409, 2.497] |
| a9_rate_prefix_reuse | 0.977 [0.971, 0.981] | 3.594 [3.446, 3.743] | 0.272 [0.261, 0.285] supported | 0.272 [0.261, 0.285] | 0.339 [0.326, 0.354] | 0.850 [0.844, 0.857] |

**Victim latency and completion (secondary; mean of 5 seeds)**

| block | arm | victim user TTFT P95 ms | victim backend TTFT P95 ms | victim E2E P95 ms | victim completion rate | victim timeout rate | victim SLO success / offered | competitor completion rate |
|---|---|---|---|---|---|---|---|---|
| a9_rate_prefill | attack | 616 | 569 | 3032 | 1.000 | 0.000 | 1.000 | 1.000 |
| a9_rate_prefill | control | 189 | 185 | 1552 | 1.000 | 0.000 | 1.000 | 1.000 |
| a9_rate_decode | attack | 3237 | 141 | 4596 | 1.000 | 0.000 | 0.808 | 1.000 |
| a9_rate_decode | control | 185 | 157 | 1583 | 1.000 | 0.000 | 1.000 | 1.000 |
| a9_rate_prefix_reuse | attack | 203 | 201 | 1723 | 1.000 | 0.000 | 1.000 | 1.000 |
| a9_rate_prefix_reuse | control | 162 | 158 | 1535 | 1.000 | 0.000 | 1.000 | 1.000 |

### 3.3 Long context: v3.1 (new) and v3 (invalid, for comparison only)

**Absolute and normalized energy, and work (mean of 5 seeds)**

| block | arm | dyn. energy kJ (arm window) | dyn. energy kJ (incl. tail) | authorized tok | realized tok | J/1k auth | J/1k auth (incl. tail) | J/1k realized | comp. authorized tok | comp. admitted tok | comp. completed tok | GPU W mean | GPU util % | engine busy s | engine service s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a9_rate_longctx_v31 | attack | 32.71 | 34.80 | 94710 | 94659 | 361.9 | 385.3 | 362.2 | 80458 | 80458 | 80458 | 299 | 88.9 | 108.6 | 336 |
| a9_rate_longctx_v31 | control | 28.92 | 31.12 | 17221 | 17219 | 1686.9 | 1815.9 | 1687.1 | 2970 | 2970 | 2970 | 276 | 76.2 | 87.4 | 173 |
| a9_tok_longctx_v31 | attack | 32.85 | 34.99 | 94710 | 94672 | 362.8 | 386.8 | 362.9 | 80458 | 80458 | 80458 | 299 | 89.6 | 109.5 | 335 |
| a9_tok_longctx_v31 | control | 34.89 | 37.06 | 94712 | 83748 | 384.2 | 408.3 | 420.9 | 80461 | 80461 | 70118 | 310 | 97.0 | 122.3 | 918 |
| a9_rate_longctx | attack | 27.88 | 30.03 | 94708 | 25241 | 310.3 | 334.4 | 1121.6 | 80458 | 80458 | 1394 | 268 | 70.2 | 79.9 | 152 |
| a9_rate_longctx | control | 29.10 | 31.27 | 17220 | 27254 | 1698.0 | 1825.1 | 1073.1 | 2970 | 2970 | 2970 | 277 | 76.6 | 86.7 | 179 |
| a9_tok_longctx | attack | 27.91 | 30.07 | 94708 | 25241 | 310.4 | 334.5 | 1122.8 | 80458 | 80458 | 1394 | 267 | 71.0 | 81.3 | 152 |
| a9_tok_longctx | control | 35.69 | 37.89 | 94711 | 124204 | 393.9 | 418.4 | 289.0 | 80461 | 80461 | 66099 | 315 | 98.7 | 125.3 | 950 |

**Per-seed attack/control ratios (mean [95% bootstrap CI]); the J/1k-authorized column is the pre-registered primary**

| block | absolute dyn. energy | authorized tokens | J/1k authorized (primary) | J/1k auth incl. tail | J/1k realized (post-hoc) | engine service s |
|---|---|---|---|---|---|---|
| a9_rate_longctx_v31 | 1.131 [1.102, 1.157] | 5.446 [4.626, 6.266] | 0.213 [0.185, 0.241] supported | 0.211 [0.183, 0.238] | 0.213 [0.185, 0.241] | 1.929 [1.720, 2.138] |
| a9_tok_longctx_v31 | 0.943 [0.917, 0.972] | 1.000 [0.999, 1.000] | 0.943 [0.917, 0.973] negative | 0.945 [0.922, 0.974] | 0.856 [0.765, 0.947] | 0.363 [0.336, 0.391] |
| a9_rate_longctx | 0.959 [0.940, 0.977] | 5.447 [4.627, 6.266] | 0.181 [0.153, 0.210] supported | 0.182 [0.153, 0.211] | 1.044 [0.962, 1.126] | 0.850 [0.807, 0.890] |
| a9_tok_longctx | 0.783 [0.759, 0.808] | 1.000 [0.999, 1.000] | 0.784 [0.759, 0.809] inconclusive | 0.795 [0.770, 0.820] | 3.876 [3.598, 4.136] | 0.161 [0.153, 0.170] |

**Victim latency and completion (secondary; mean of 5 seeds)**

| block | arm | victim user TTFT P95 ms | victim backend TTFT P95 ms | victim E2E P95 ms | victim completion rate | victim timeout rate | victim SLO success / offered | competitor completion rate |
|---|---|---|---|---|---|---|---|---|
| a9_rate_longctx_v31 | attack | 739 | 486 | 2920 | 1.000 | 0.000 | 0.992 | 1.000 |
| a9_rate_longctx_v31 | control | 137 | 137 | 1418 | 1.000 | 0.000 | 1.000 | 1.000 |
| a9_tok_longctx_v31 | attack | 726 | 505 | 2922 | 1.000 | 0.000 | 0.992 | 1.000 |
| a9_tok_longctx_v31 | control | 45422 | 131 | 46771 | 0.956 | 0.044 | 0.091 | 0.871 |
| a9_rate_longctx | attack | 201 | 201 | 1544 | 1.000 | 0.000 | 1.000 | 0.034 |
| a9_rate_longctx | control | 251 | 250 | 1576 | 1.000 | 0.000 | 1.000 | 1.000 |
| a9_tok_longctx | attack | 195 | 195 | 1540 | 1.000 | 0.000 | 1.000 | 0.034 |
| a9_tok_longctx | control | 49590 | 272 | 50994 | 0.933 | 0.067 | 0.060 | 0.822 |

### 3.4 Where the apparent energy improvement comes from

Decomposition: primary ratio = (absolute energy ratio) ÷ (authorized-token ratio), using the per-seed ratios above.
Every v3.1 request and every valid v3 attack arm completed its competitor requests, so incomplete execution is ruled out
except where stated.

- **Rate-matched prefill, decode, prefix reuse, and long context v3.1 (ratios 0.21–0.62, `supported`): denominator.** The attack arm
  authorizes 1.7–5.5× more tokens, while arm energy changes by only −2% to +13%. Engine service time rises (decode 2.45×, long
  context 1.95×, prefill 1.19×) or falls slightly (prefix reuse 0.85×, from 55% prefix-cache hits). The GPU runs at 276–311 W
  mean in *both* arms, near its active power, for the whole 120 s window. Energy per arm is therefore set mainly by
  being active for the window, not by token volume, and more tokens per window lowers J per token. This is **not** lower
  real compute work (except the modest prefix-reuse saving), and **not** a victim effect: in rate-matched prefill the victim's
  backend TTFT P95 is about 3× *higher* in the attack arm, and its E2E P95 is 2.0× higher.
- **Token-matched prefill / prefix reuse (0.90 / 0.86, `negative`):** matched authorized tokens, so the primary equals the absolute
  energy ratio. The control does *more* engine work (3.2× / 4.5× engine service seconds: about 560 short requests against 75 long
  ones), yet completes only about 94% of its competitor tokens (gateway timeouts). Its slightly higher energy is therefore a lower bound on
  the work it was authorized for. Incomplete execution in the control biases the ratio toward 1, not away from it.
- **Token-matched decode (1.10, `negative`):** the attack's long decodes use 10% more energy than the short control at matched
  authorized tokens. Both arms completed their competitor requests.
- **Token-matched long context v3.1 (`invalid`):** the computed 0.94 is not interpretable. The control executed only 87% of its
  authorized competitor tokens (74.6–76.0% of requests in seeds 45–46), which is incomplete execution, and it is refused by the gate.
- **Long context v3 (`invalid`):** the attack arms executed 2% of their competitor tokens (HTTP 400). Their 0.18 / 0.78 ratios are
  an incomplete-execution artifact.

## 4. Corrected long-context results (protocol v3.1)

### `a9_tok_longctx_v31`: invalid (computed before gates: negative)

- Commit `02448f8cb6adc31d924d9e8b3f86a0cc0e7f7585`, dirty ['False'], vLLM ['{"version": "0.17.1"}'], server start ['1795268683.89'], model `Qwen/Qwen2.5-7B-Instruct`; model revision: server reports revision=None (resolved from the hub default at load time); documented revision none is not server-verified.
- Pre-run tokenization: tokenizer `vllm /tokenize`, unit `tokenizer`; every request of both arms × 5 seeds verified (`ok` in all 10 arm traces). GPU telemetry: nvidia_gpu_exporter (RTX 3090); backend config in `target_snapshot/`.
- Primary: GPU Dynamic Energy per 1,000 Authorized Tokens ratio 0.943 [0.917, 0.973], threshold 1.25 two-sided.
- Gates: backend_error_rate pass (worst arm 0.0000 (max 0.01)); http_400_rate pass (worst arm 0.0000 (max 0.01)); admission_rate pass (lowest class admission 1.000 (min 0.95)); competitor_completion FAIL (lowest arm 0.746 (min 0.95)); primary_metric_present pass (5/5 seeds have a finite GPU Dynamic Energy per 1,000 Authorized Tokens); tokenized_context pass (max completed prompt+max_output 3840.0 <= 4096; pre-run check ok); planned_vs_reported_tokens pass (0 mismatch(es) among 3913/3913 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it)); provenance pass (sha 02448f8cb6ad, clean, server start 1795268683.89); victim_latency_censoring FAIL (worst arm censored fraction 0.130 (max 0.05); secondary latency endpoints only)

| seed | energy A kJ | energy C kJ | auth tok A | auth tok C | J/1k auth A | J/1k auth C | ratio | comp. done A | comp. done C | victims done A | victims done C | victim user TTFT P95 A ms | victim user TTFT P95 C ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 42 | 31.28 | 31.43 | 64691 | 64747 | 483.6 | 485.4 | 0.996 | 15/15 | 406/406 | 99/99 | 99/99 | 185 | 16879 |
| 43 | 30.46 | 33.10 | 77811 | 77831 | 391.4 | 425.3 | 0.920 | 19/19 | 494/494 | 110/110 | 110/110 | 811 | 34799 |
| 44 | 33.23 | 36.89 | 93036 | 93054 | 357.1 | 396.4 | 0.901 | 22/22 | 609/609 | 111/111 | 111/111 | 841 | 55822 |
| 45 | 34.69 | 36.79 | 118240 | 118221 | 293.4 | 311.2 | 0.943 | 30/30 | 620/816 | 106/106 | 97/106 | 1139 | 59613 |
| 46 | 34.58 | 36.21 | 119770 | 119708 | 288.7 | 302.5 | 0.954 | 30/30 | 610/818 | 115/115 | 100/115 | 654 | 59997 |

### `a9_rate_longctx_v31`: supported

- Commit `02448f8cb6adc31d924d9e8b3f86a0cc0e7f7585`, dirty ['False'], vLLM ['{"version": "0.17.1"}'], server start ['1795268683.89'], model `Qwen/Qwen2.5-7B-Instruct`; model revision: server reports revision=None (resolved from the hub default at load time); documented revision none is not server-verified.
- Pre-run tokenization: tokenizer `vllm /tokenize`, unit `tokenizer`; every request of both arms × 5 seeds verified (`ok` in all 10 arm traces). GPU telemetry: nvidia_gpu_exporter (RTX 3090); backend config in `target_snapshot/`.
- Primary: GPU Dynamic Energy per 1,000 Authorized Tokens ratio 0.213 [0.185, 0.241], threshold 1.25 two-sided.
- Gates: backend_error_rate pass (worst arm 0.0000 (max 0.01)); http_400_rate pass (worst arm 0.0000 (max 0.01)); admission_rate pass (lowest class admission 1.000 (min 0.95)); competitor_completion pass (lowest arm 1.000 (min 0.95)); primary_metric_present pass (5/5 seeds have a finite GPU Dynamic Energy per 1,000 Authorized Tokens); tokenized_context pass (max completed prompt+max_output 3840.0 <= 4096; pre-run check ok); planned_vs_reported_tokens pass (0 mismatch(es) among 1314/1314 completed requests reporting usage.prompt_tokens (planned input_token_count must equal it)); provenance pass (sha 02448f8cb6ad, clean, server start 1795268683.89); victim_latency_censoring pass (worst arm censored fraction 0.000 (max 0.05); secondary latency endpoints only)

| seed | energy A kJ | energy C kJ | auth tok A | auth tok C | J/1k auth A | J/1k auth C | ratio | comp. done A | comp. done C | victims done A | victims done C | victim user TTFT P95 A ms | victim user TTFT P95 C ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 42 | 31.23 | 27.50 | 64691 | 14699 | 482.8 | 1870.9 | 0.258 | 15/15 | 15/15 | 99/99 | 99/99 | 198 | 144 |
| 43 | 30.81 | 28.52 | 77811 | 17031 | 396.0 | 1674.7 | 0.236 | 19/19 | 19/19 | 110/110 | 110/110 | 817 | 112 |
| 44 | 33.09 | 29.64 | 93036 | 17918 | 355.7 | 1654.5 | 0.215 | 22/22 | 22/22 | 111/111 | 111/111 | 905 | 165 |
| 45 | 34.01 | 29.00 | 118240 | 17613 | 287.7 | 1646.5 | 0.175 | 30/30 | 30/30 | 106/106 | 106/106 | 1150 | 130 |
| 46 | 34.41 | 29.92 | 119770 | 18844 | 287.3 | 1587.8 | 0.181 | 30/30 | 30/30 | 115/115 | 115/115 | 623 | 134 |

## 5. Validity status of each A7–A9 block (final)

| block | pre-registered result | status |
|---|---|---|
| A7-V (S0) | negative (A/A) | valid; precision gate passed under both TTFT definitions |
| A7 S1 / S1′ | supported (victim faster) | valid; S1 exploratory, S1′ confirmatory; holds under both TTFT definitions |
| A8a / A8b | negative / negative | valid as computed (backend TTFT); post-hoc user-facing TTFT is lower in the attack arms |
| A9 tok prefill / prefix reuse | negative / negative | valid as computed; post-hoc: the control completed ≈94% of competitor requests (fails the ADR-Q17 completion gate) |
| A9 tok decode | negative | valid |
| A9 rate prefill / decode / prefix reuse | supported (< 0.8) | valid; driven by the denominator (cost per token), not a victim effect |
| A9 tok / rate long context v3 | inconclusive / supported | **invalid** (HTTP 400); kept as data, excluded |
| A9 rate long context v3.1 | supported (< 0.8) | **valid**, every gate passed; denominator-driven |
| A9 tok long context v3.1 | invalid (computed: negative) | **invalid**: pre-registered competitor-completion gate (control could not execute its budget) |

## 6. Code corrections (committed in 53d0ed3 / 02448f8)

- `evaluation/attack_effect.py`: `MetricInfo` registry. Every heading, table header, figure axis and verdict comes from the metric, and
  `check_report_labels` fails closed on a mismatch. Both TTFT definitions plus gateway queue time; victim offered, admitted, completed,
  rejected, timed-out, error and cancelled counts; offered-load SLO success; censoring; competitor admission, completion, HTTP 400 and
  authorized/admitted/completed/realized tokens; energy incl. tail; GPU power; and secondary endpoints in every report.
- `evaluation/validity.py`: ADR-Q17 gates; the CLI sets `invalid` and exits 5. `workload/tokenize.py`: live `/tokenize` counter,
  per-request calibration, and a pre-run context check (exit 3 before anything is sent). `scenario.prompt_token_unit`,
  single-token filler, a 32-token floor. `targets.model_revision_provenance` reads the revision the server itself reports.
- `scripts/reanalyze_suite.py` (this re-analysis), `scripts/write_corrected_analysis.py` (this document).

## 7. Open points for the owner (not changed here)

1. **The `matched_total_short` control congests the gateway.** At these budgets, re-expressing the competitor's tokens as hundreds of
   short requests saturates `max_global_inflight: 8`, so the control's own victims queue for up to 60 s and are censored (A2, A9-tok).
   That is a property of the control design under a fixed FCFS gateway, not of the attack. Any change (a different control,
   a longer window, or a different queue cap) is a protocol change that needs pre-registration. No threshold was changed.
2. **A2's historical headline** stays recorded as computed. Under ADR-Q17 it would be invalid (censoring), and its post-hoc
   user-facing and SLO-success results point the other way. Any paper claim should use the corrected framing.
3. **Model revision:** the server reports `revision=None`. Confirming the loaded snapshot needs the owner to check on the host
   (for example the HF cache snapshot directory).

