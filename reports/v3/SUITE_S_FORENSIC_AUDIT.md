# Suite S forensic audit (A7–A9, protocol v3)

Read-only audit, 2026-11-21 20:39–20:48 EST. No GPU runs were made, no data was overwritten, and the pre-registered protocol,
thresholds and classifications were not changed. Every number in the tables below comes from `results/<block>__{attack,control}/*/`
(`requests.parquet`, `trace.jsonl`, `metrics_timeseries.parquet`, `metrics_summary.json`, `manifest.json`) and
`reports/v3/<block>/{manifest.json,summary.md}`. The audit scripts are in the session scratchpad (`audit.py`, `write_audit.py`), and their
CSV outputs (`per_arm.csv`, `endpoints_per_seed.csv`, `coverage.csv`, `trace_identity.csv`, `provenance.csv`,
`report_vs_recomputed.csv`) are copied to `reports/v3/suite_s_audit/`.

## 0. Conclusions

1. **A9 "low victim TTFT ratios" (0.18–0.62): the cause is a report labelling defect, not a measurement.** For A9 the
   pre-registered `degradation_metric` is `gpu_energy_per_1k_authorized_tokens`, and the reported ratios are exactly that
   primary endpoint. `write_report` prints it under the fixed label "Mean victim slowdown ratio", with per-seed columns
   headed "attack ms / control ms". Those columns are actually J per 1k authorized tokens. Recomputed from raw files, all 60 per-seed ratios
   (A7–A9) match the reports to within rounding (max |Δratio| = 0.005). No arm is reversed and no denominator is wrong. My earlier progress messages that called these
   "victim speed-ups" were wrong. The actual secondary victim TTFT results are in §2.4. For example, `a9_rate_prefill` victim backend
   TTFT P95 is **3.44× the control** (a slowdown), not 0.29×.
2. **Why the A9 rate-matched energy ratios are low: real and mechanical.** Dynamic GPU energy per arm is nearly constant
   (27.0–37.3 kJ, mean board power 261–317 W) because the GPU runs near full power whenever any request is in flight.
   Rate-matched attack arms authorize 1.7–6.7× more tokens than their short control (decode 1.7×, prefill and prefix-reuse 3.3–3.8×,
   long context 4.4–6.7×), so J per 1k authorized tokens falls by about the same factor. This is a measured property of this GPU at this load, with no sign of an accounting error. It is still mostly a
   denominator effect, and it should be reported that way.
3. **Long-context coverage = 0.0: the 0.0 came from my own check script, but it exposed a real defect.** In `a9_{tok,rate}_longctx`, the
   attack-arm competitor completed **4 of 116** requests. The other **112 failed with HTTP 400** ("You passed 3841 input tokens
   ... maximum input length of 3840 tokens"). In seeds 42 and 46 the competitor tenant completed 0 requests, so the harness
   correctly records its coverage as `null` (empty denominator). My `suite_check.py` turned that `null` into 0 with `or 0`. All
   29,975 completed requests in Suite S report a numeric `cached_tokens`, with 0 nulls. All 1,648 non-completed requests have `null`, kept as missing.
4. **Root cause of the long-context failure: the planned token unit is whitespace words, not tokenizer tokens.** Realized prompt tokens per
   planned word are 2.03–2.14 for the pseudo-word filler and 1.21–1.36 for the single-token prefix vocabulary. The long-context family
   plans 1,136–3,584 words (3,584 is the cap), which is about 2,300–7,300 real tokens, against a 3,840-token input limit. The schema safety
   check (`scenario.py:284`) compares planned words with `model_max_len`, so it passed. No long-context smoke was run.
   **Both long-context blocks are invalid: the manipulation failed** (the competitor workload was never served).
5. **TTFT definition discrepancy (affects all A1–A9 TTFT endpoints).** `attack_effect.run_metrics` computes `ttft_ms =
   t_first_token − t_sent` (backend TTFT, excluding gateway queueing; `attack_effect.py:98-100`, since commit 4a829d7, Phase 5).
   `docs/METRIC_DEFINITIONS.md:11` and `evaluation/metrics.py:37` define `ttft_ms = t_first_token − t_offered`
   (user-facing, including the gateway queue). The pre-registered "victim TTFT P95" has always been computed as backend TTFT.
   This matters a lot where the gateway queue dominates. Examples: A8 control-arm victims wait 1.7–9.5 s at P95 in the gateway, and A9 token-matched controls 50–52 s.
   The pre-registered labels for A7 and A8 do not change under the other definition (§2.5), but A9's secondary TTFT does.
6. **Token-matched A9 victims are censored.** In `a9_tok_{prefill,longctx,prefix_reuse}` controls, victims hit the
   gateway's 60 s queue timeout (12, 36 and 13 requests over 5 seeds; seeds 44–46 only). Timed-out requests are excluded from TTFT,
   so the control-arm TTFT is survivor-biased toward faster requests.
7. **Other integrity checks are clean.** One server start (1795268683.89) and no restarts. Engine reconciliation residual is 0 in all 120 runs, with no
   unrelated traffic, no leaks and request accounting conserved. Victim workloads are identical across arms up to the designed per-arm salt.
   Competitor arrival schedules are identical in every rate-matched block. The GPU idle baseline and tail settled in every arm, with
   166–206 power samples per arm and a maximum gap of 2.0 s.
8. **GPU reruns:** needed only for the two long-context blocks, after a scenario fix that changes the protocol and needs approval and
   a fresh pre-registration (§7). Every other correction is analysis-side and can be recomputed from the existing data.

## 1. Evidence: A9 metric mapping

- `experiments/v3/a9_*.yaml`: `comparison.degradation_metric: gpu_energy_per_1k_authorized_tokens` (all 8 files).
  A7/A8: `ttft_p95`.
- `src/quotashift/evaluation/attack_effect.py:163-173` `_metric_value`: for this metric, returns
  `gpu_dynamic_energy_j / (authorized_tokens / 1000)`. `analyze_pair` (`:198-251`) takes ratio = attack / control per seed.
- `attack_effect.py:284` prints `"Mean victim slowdown ratio"`, and `:296` prints the per-seed table header
  `"| seed | attack ms | control ms | ratio |"` whatever the metric. The figure's y-label (`:415`) is
  "victim slowdown ratio" too. **Labelling defect only; values are correct.**
- `authorized_tokens` (`runtime/runner.py:283`) = Σ over **all** requests in the arm, victims included, of
  `input_token_count + max_output_tokens`, in planned (whitespace-word) units, per ADR-Q10 ("budgets compared are
  planned/requested quantities"). `gpu_dynamic_energy_j` (`instrumentation/engine_counters.py:148-156`) is a trapezoid
  integral of board power over the arm's scrape window, minus pre-arm idle power × span.
- Report vs recomputed: `suite_s_audit/report_vs_recomputed.csv`, 60 seed pairs, max |Δratio| 0.0049 (2-decimal rounding
  in `summary.md`).
- Trace checks (`trace_identity.csv`): victim requests in every block have identical `request_id`, tenant, arrival time,
  `input_token_count`, `max_output_tokens`, deadlines and SLO class across arms. Their prompt text differs only in the designed
  per-arm salt (4 nonce words, `workload/isolation.py`; A7: the 192-word arm-salted tenant prefix, `workload/prefix_cache.py:37-58`).
  `rate_matched_short` keeps the competitor request count and the arrival times exactly the same in all 20 rate-matched seed pairs
  (`comp_arrivals_identical = True`) and changes the shape to (64 in / 64 out), as designed
  (`scenario.py:61`). Admission policy (FCFS), rate limits (none), queue caps (`max_queue_wait_s = 60`), backend URL,
  vLLM 0.17.1, and cache config (`gpu_memory_utilization` 0.8, 4662 blocks, prefix caching on) are identical in every
  run manifest.

## 2. Per-seed metrics

### 2.1 A9 primary endpoint: GPU dynamic energy per 1k authorized tokens (arm window)

| block | seed | dyn. energy A (kJ) | dyn. energy C (kJ) | authorized tok A | authorized tok C | realized tok A | realized tok C | J/1k auth A | J/1k auth C | ratio A/C |
|---|---|---|---|---|---|---|---|---|---|---|
| a9_tok_prefill | 42 | 31.19 | 33.93 | 75302 | 75241 | 145115 | 117517 | 414.2 | 451.0 | 0.918 |
| a9_tok_prefill | 43 | 31.30 | 34.15 | 76924 | 76935 | 147762 | 120373 | 407.0 | 443.9 | 0.917 |
| a9_tok_prefill | 44 | 32.84 | 37.27 | 86889 | 86906 | 167772 | 131205 | 377.9 | 428.9 | 0.881 |
| a9_tok_prefill | 45 | 33.21 | 37.17 | 94770 | 94797 | 183685 | 131273 | 350.5 | 392.1 | 0.894 |
| a9_tok_prefill | 46 | 33.29 | 36.67 | 94407 | 94364 | 182527 | 127688 | 352.6 | 388.6 | 0.907 |
| a9_tok_decode | 42 | 33.74 | 30.85 | 45978 | 45929 | 58989 | 71841 | 733.9 | 671.7 | 1.093 |
| a9_tok_decode | 43 | 35.53 | 31.73 | 51993 | 51975 | 66486 | 81413 | 683.3 | 610.5 | 1.119 |
| a9_tok_decode | 44 | 34.38 | 32.28 | 50391 | 50426 | 65274 | 79282 | 682.3 | 640.2 | 1.066 |
| a9_tok_decode | 45 | 35.22 | 30.69 | 54987 | 54989 | 70068 | 86073 | 640.5 | 558.1 | 1.147 |
| a9_tok_decode | 46 | 34.10 | 31.91 | 56119 | 56092 | 71374 | 87804 | 607.6 | 568.9 | 1.068 |
| a9_tok_longctx | 42 | 26.96 | 32.94 | 64689 | 64745 | 20156 | 101172 | 416.8 | 508.7 | 0.819 |
| a9_tok_longctx | 43 | 27.70 | 33.92 | 77811 | 77831 | 29177 | 121769 | 356.0 | 435.9 | 0.817 |
| a9_tok_longctx | 44 | 28.02 | 37.25 | 93032 | 93050 | 27540 | 133982 | 301.2 | 400.3 | 0.753 |
| a9_tok_longctx | 45 | 28.22 | 37.21 | 118240 | 118221 | 25602 | 133073 | 238.7 | 314.8 | 0.758 |
| a9_tok_longctx | 46 | 28.64 | 37.12 | 119770 | 119708 | 23728 | 131024 | 239.2 | 310.1 | 0.771 |
| a9_tok_prefix_reuse | 42 | 29.68 | 33.83 | 75302 | 75241 | 95576 | 117517 | 394.2 | 449.6 | 0.877 |
| a9_tok_prefix_reuse | 43 | 29.96 | 33.41 | 76924 | 76935 | 98146 | 120373 | 389.5 | 434.2 | 0.897 |
| a9_tok_prefix_reuse | 44 | 30.49 | 37.07 | 86889 | 86906 | 110336 | 132434 | 351.0 | 426.5 | 0.823 |
| a9_tok_prefix_reuse | 45 | 31.26 | 37.07 | 94770 | 94797 | 119228 | 131184 | 329.8 | 391.0 | 0.843 |
| a9_tok_prefix_reuse | 46 | 31.22 | 36.43 | 94407 | 94364 | 119273 | 128267 | 330.7 | 386.1 | 0.856 |
| a9_rate_prefill | 42 | 31.33 | 30.72 | 75302 | 21097 | 145115 | 33124 | 416.1 | 1456.2 | 0.286 |
| a9_rate_prefill | 43 | 31.44 | 30.16 | 76924 | 23047 | 147762 | 36364 | 408.7 | 1308.8 | 0.312 |
| a9_rate_prefill | 44 | 33.03 | 31.54 | 86889 | 24698 | 167772 | 39163 | 380.1 | 1276.9 | 0.298 |
| a9_rate_prefill | 45 | 33.54 | 32.12 | 94770 | 24653 | 183685 | 38776 | 353.9 | 1302.8 | 0.272 |
| a9_rate_prefill | 46 | 32.85 | 32.02 | 94407 | 25500 | 182527 | 40121 | 348.0 | 1255.7 | 0.277 |
| a9_rate_decode | 42 | 34.18 | 30.99 | 45978 | 26601 | 59232 | 41709 | 743.5 | 1164.8 | 0.638 |
| a9_rate_decode | 43 | 35.55 | 32.29 | 51993 | 30215 | 66215 | 47535 | 683.7 | 1068.7 | 0.640 |
| a9_rate_decode | 44 | 34.44 | 32.39 | 50391 | 29818 | 65095 | 47161 | 683.4 | 1086.1 | 0.629 |
| a9_rate_decode | 45 | 35.14 | 32.66 | 54987 | 30925 | 69936 | 48557 | 639.0 | 1056.0 | 0.605 |
| a9_rate_decode | 46 | 34.53 | 32.73 | 56119 | 32284 | 70863 | 50706 | 615.3 | 1013.8 | 0.607 |
| a9_rate_longctx | 42 | 26.96 | 28.01 | 64689 | 14697 | 20156 | 23154 | 416.7 | 1906.0 | 0.219 |
| a9_rate_longctx | 43 | 27.83 | 28.10 | 77811 | 17031 | 29177 | 27021 | 357.7 | 1649.7 | 0.217 |
| a9_rate_longctx | 44 | 28.05 | 30.17 | 93032 | 17914 | 27540 | 28579 | 301.5 | 1684.2 | 0.179 |
| a9_rate_longctx | 45 | 28.06 | 29.09 | 118240 | 17613 | 25602 | 27790 | 237.3 | 1651.4 | 0.144 |
| a9_rate_longctx | 46 | 28.52 | 30.13 | 119770 | 18844 | 23728 | 29728 | 238.1 | 1599.0 | 0.149 |
| a9_rate_prefix_reuse | 42 | 29.71 | 30.70 | 75302 | 21097 | 95576 | 33124 | 394.5 | 1455.2 | 0.271 |
| a9_rate_prefix_reuse | 43 | 29.82 | 30.30 | 76924 | 23047 | 98146 | 36364 | 387.7 | 1314.6 | 0.295 |
| a9_rate_prefix_reuse | 44 | 30.91 | 31.63 | 86889 | 24698 | 110336 | 39163 | 355.7 | 1280.8 | 0.278 |
| a9_rate_prefix_reuse | 45 | 31.15 | 31.95 | 94770 | 24653 | 119228 | 38776 | 328.7 | 1295.8 | 0.254 |
| a9_rate_prefix_reuse | 46 | 31.14 | 31.79 | 94407 | 25500 | 119273 | 40121 | 329.8 | 1246.6 | 0.265 |

Authorized = planned `input_token_count + max_output_tokens` over all requests (victims included). Realized = Σ `prompt_tokens_reported + output_tokens` over completed requests (engine tokenizer).

### 2.2 Victim request outcomes per arm (all blocks, mean of 5 seeds)

| block | arm | offered | admitted | sent to vLLM | completed | timed out | rejected | cancelled | other | pending |
|---|---|---|---|---|---|---|---|---|---|---|
| a7_prefix_cache | attack | 141.2 | 141.2 | 141.2 | 141.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a7_prefix_cache | control | 141.2 | 141.2 | 141.2 | 141.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a7_prefix_cache_reset | attack | 141.2 | 141.2 | 141.2 | 141.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a7_prefix_cache_reset | control | 141.2 | 141.2 | 141.2 | 141.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a8_lifecycle_churn | attack | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a8_lifecycle_churn | control | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a8_retry_churn | attack | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a8_retry_churn | control | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a9_tok_prefill | attack | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a9_tok_prefill | control | 108.2 | 108.2 | 105.8 | 105.8 | 2.4 | 0.0 | 0.0 | 0.0 | 0.0 |
| a9_tok_decode | attack | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a9_tok_decode | control | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a9_tok_longctx | attack | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a9_tok_longctx | control | 108.2 | 108.2 | 101.0 | 101.0 | 7.2 | 0.0 | 0.0 | 0.0 | 0.0 |
| a9_tok_prefix_reuse | attack | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a9_tok_prefix_reuse | control | 108.2 | 108.2 | 105.6 | 105.6 | 2.6 | 0.0 | 0.0 | 0.0 | 0.0 |
| a9_rate_prefill | attack | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a9_rate_prefill | control | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a9_rate_decode | attack | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a9_rate_decode | control | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a9_rate_longctx | attack | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a9_rate_longctx | control | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a9_rate_prefix_reuse | attack | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| a9_rate_prefix_reuse | control | 108.2 | 108.2 | 108.2 | 108.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

All victim timeouts are `terminal_detail = gateway_queue_timeout` with `t_sent = null`: they never reached vLLM. There were no rejections and no pending (non-terminal) requests. No non-completed victim has a first token, so excluding them from TTFT drops no partial TTFT observations, but it does drop the slowest requests (censoring).

Victim gateway-queue timeouts by seed (42..46), token-matched controls: `a9_tok_prefill` 0, 0, 2, 3, 7; `a9_tok_decode` 0, 0, 0, 0, 0; `a9_tok_longctx` 0, 0, 8, 12, 16; `a9_tok_prefix_reuse` 0, 0, 2, 5, 6. Attack arms: 0 in every block.

### 2.3 Victim latency per seed (ms; backend TTFT = `t_first_token − t_sent`, completed victims, as analysed)

| block | seed | P50 A | P50 C | P95 A | P95 C | P99 A | P99 C | P95 ratio A/C | victim timeouts A | victim timeouts C |
|---|---|---|---|---|---|---|---|---|---|---|
| a7_prefix_cache | 42 | 110.9 | 126.3 | 218.9 | 379.5 | 292.9 | 468.2 | 0.577 | 0 | 0 |
| a7_prefix_cache | 43 | 114.7 | 123.5 | 233.9 | 374.6 | 295.5 | 561.9 | 0.624 | 0 | 0 |
| a7_prefix_cache | 44 | 114.0 | 122.1 | 228.0 | 326.7 | 285.5 | 432.1 | 0.698 | 0 | 0 |
| a7_prefix_cache | 45 | 106.4 | 115.2 | 227.3 | 369.4 | 312.8 | 491.0 | 0.615 | 0 | 0 |
| a7_prefix_cache | 46 | 114.5 | 121.2 | 201.0 | 386.4 | 264.1 | 432.9 | 0.520 | 0 | 0 |
| a7_prefix_cache_reset | 42 | 110.4 | 112.5 | 238.1 | 382.6 | 291.9 | 444.5 | 0.622 | 0 | 0 |
| a7_prefix_cache_reset | 43 | 110.6 | 127.9 | 225.7 | 402.9 | 301.0 | 632.0 | 0.560 | 0 | 0 |
| a7_prefix_cache_reset | 44 | 114.7 | 126.9 | 235.6 | 329.8 | 296.8 | 444.1 | 0.714 | 0 | 0 |
| a7_prefix_cache_reset | 45 | 109.4 | 130.2 | 241.6 | 396.1 | 343.5 | 479.7 | 0.610 | 0 | 0 |
| a7_prefix_cache_reset | 46 | 113.0 | 118.4 | 203.7 | 357.4 | 265.4 | 461.2 | 0.570 | 0 | 0 |
| a8_lifecycle_churn | 42 | 101.2 | 103.1 | 129.6 | 133.1 | 182.5 | 197.3 | 0.974 | 0 | 0 |
| a8_lifecycle_churn | 43 | 104.2 | 105.5 | 136.0 | 170.6 | 148.5 | 278.7 | 0.797 | 0 | 0 |
| a8_lifecycle_churn | 44 | 105.5 | 105.2 | 151.4 | 153.8 | 181.8 | 177.6 | 0.985 | 0 | 0 |
| a8_lifecycle_churn | 45 | 100.1 | 98.3 | 136.5 | 136.6 | 153.2 | 162.5 | 1.000 | 0 | 0 |
| a8_lifecycle_churn | 46 | 104.0 | 101.1 | 144.6 | 128.8 | 165.7 | 144.9 | 1.122 | 0 | 0 |
| a8_retry_churn | 42 | 101.7 | 102.7 | 131.5 | 145.5 | 181.2 | 210.7 | 0.904 | 0 | 0 |
| a8_retry_churn | 43 | 104.9 | 103.3 | 179.0 | 137.0 | 329.6 | 152.2 | 1.307 | 0 | 0 |
| a8_retry_churn | 44 | 106.8 | 105.8 | 174.1 | 147.7 | 296.0 | 157.1 | 1.178 | 0 | 0 |
| a8_retry_churn | 45 | 116.6 | 106.3 | 224.1 | 189.7 | 268.5 | 509.5 | 1.181 | 0 | 0 |
| a8_retry_churn | 46 | 115.9 | 115.1 | 196.1 | 194.5 | 273.5 | 320.5 | 1.009 | 0 | 0 |
| a9_tok_prefill | 42 | 136.9 | 208.2 | 522.8 | 386.0 | 887.5 | 388.2 | 1.354 | 0 | 0 |
| a9_tok_prefill | 43 | 142.7 | 224.7 | 530.5 | 329.7 | 804.8 | 458.7 | 1.609 | 0 | 0 |
| a9_tok_prefill | 44 | 149.9 | 157.7 | 510.5 | 247.0 | 843.4 | 387.8 | 2.067 | 0 | 2 |
| a9_tok_prefill | 45 | 142.5 | 252.7 | 738.2 | 355.9 | 1196.1 | 385.1 | 2.074 | 0 | 3 |
| a9_tok_prefill | 46 | 142.7 | 272.5 | 700.9 | 377.0 | 957.1 | 473.3 | 1.859 | 0 | 7 |
| a9_tok_decode | 42 | 115.9 | 122.5 | 233.1 | 226.5 | 812.0 | 301.7 | 1.029 | 0 | 0 |
| a9_tok_decode | 43 | 121.9 | 119.0 | 190.6 | 195.6 | 233.8 | 238.4 | 0.974 | 0 | 0 |
| a9_tok_decode | 44 | 119.7 | 131.0 | 259.2 | 232.4 | 317.8 | 259.3 | 1.115 | 0 | 0 |
| a9_tok_decode | 45 | 103.7 | 189.1 | 166.8 | 314.0 | 229.7 | 371.3 | 0.531 | 0 | 0 |
| a9_tok_decode | 46 | 104.6 | 112.8 | 138.6 | 164.0 | 158.8 | 223.4 | 0.845 | 0 | 0 |
| a9_tok_longctx | 42 | 100.0 | 113.0 | 159.5 | 178.7 | 184.8 | 204.6 | 0.892 | 0 | 0 |
| a9_tok_longctx | 43 | 109.7 | 133.1 | 239.5 | 246.2 | 305.3 | 261.1 | 0.973 | 0 | 0 |
| a9_tok_longctx | 44 | 124.1 | 261.5 | 236.6 | 302.0 | 306.7 | 426.1 | 0.783 | 0 | 8 |
| a9_tok_longctx | 45 | 101.6 | 221.6 | 150.9 | 335.5 | 229.9 | 350.5 | 0.450 | 0 | 12 |
| a9_tok_longctx | 46 | 103.5 | 254.5 | 186.9 | 299.8 | 261.3 | 301.9 | 0.624 | 0 | 16 |
| a9_tok_prefix_reuse | 42 | 103.2 | 111.4 | 206.4 | 158.5 | 238.7 | 164.0 | 1.302 | 0 | 0 |
| a9_tok_prefix_reuse | 43 | 106.4 | 149.1 | 166.9 | 229.2 | 197.4 | 259.5 | 0.728 | 0 | 0 |
| a9_tok_prefix_reuse | 44 | 109.8 | 125.5 | 180.0 | 184.2 | 199.5 | 243.9 | 0.977 | 0 | 2 |
| a9_tok_prefix_reuse | 45 | 103.1 | 215.5 | 153.5 | 269.5 | 242.1 | 299.9 | 0.570 | 0 | 5 |
| a9_tok_prefix_reuse | 46 | 108.2 | 146.6 | 195.6 | 231.9 | 247.5 | 236.6 | 0.844 | 0 | 6 |
| a9_rate_prefill | 42 | 121.0 | 105.6 | 486.5 | 151.8 | 543.9 | 185.3 | 3.205 | 0 | 0 |
| a9_rate_prefill | 43 | 117.3 | 111.0 | 494.4 | 314.7 | 590.2 | 491.6 | 1.571 | 0 | 0 |
| a9_rate_prefill | 44 | 111.2 | 103.8 | 481.9 | 165.4 | 855.8 | 212.6 | 2.913 | 0 | 0 |
| a9_rate_prefill | 45 | 111.4 | 99.7 | 651.7 | 146.5 | 1034.3 | 171.4 | 4.449 | 0 | 0 |
| a9_rate_prefill | 46 | 116.3 | 105.6 | 728.4 | 144.2 | 873.3 | 176.6 | 5.050 | 0 | 0 |
| a9_rate_decode | 42 | 105.1 | 99.6 | 143.2 | 141.7 | 203.7 | 210.0 | 1.011 | 0 | 0 |
| a9_rate_decode | 43 | 107.6 | 106.0 | 132.8 | 147.5 | 146.9 | 174.2 | 0.901 | 0 | 0 |
| a9_rate_decode | 44 | 107.1 | 107.6 | 145.5 | 184.6 | 157.0 | 210.1 | 0.788 | 0 | 0 |
| a9_rate_decode | 45 | 104.2 | 107.1 | 146.4 | 173.4 | 165.4 | 328.6 | 0.844 | 0 | 0 |
| a9_rate_decode | 46 | 104.0 | 106.9 | 135.1 | 140.2 | 157.9 | 154.5 | 0.964 | 0 | 0 |
| a9_rate_longctx | 42 | 103.8 | 102.6 | 203.4 | 158.5 | 268.7 | 265.8 | 1.283 | 0 | 0 |
| a9_rate_longctx | 43 | 105.5 | 104.8 | 155.0 | 168.7 | 177.2 | 283.9 | 0.919 | 0 | 0 |
| a9_rate_longctx | 44 | 112.0 | 111.6 | 214.5 | 156.1 | 318.1 | 172.0 | 1.374 | 0 | 0 |
| a9_rate_longctx | 45 | 129.0 | 107.4 | 271.0 | 151.4 | 360.8 | 211.1 | 1.791 | 0 | 0 |
| a9_rate_longctx | 46 | 107.2 | 110.9 | 159.7 | 617.6 | 273.3 | 931.5 | 0.259 | 0 | 0 |
| a9_rate_prefix_reuse | 42 | 106.9 | 105.0 | 188.1 | 155.1 | 234.8 | 241.0 | 1.213 | 0 | 0 |
| a9_rate_prefix_reuse | 43 | 108.6 | 103.0 | 177.9 | 151.2 | 220.3 | 176.3 | 1.177 | 0 | 0 |
| a9_rate_prefix_reuse | 44 | 119.9 | 108.2 | 252.7 | 181.3 | 320.9 | 257.3 | 1.394 | 0 | 0 |
| a9_rate_prefix_reuse | 45 | 100.3 | 99.4 | 180.2 | 152.0 | 263.7 | 182.7 | 1.185 | 0 | 0 |
| a9_rate_prefix_reuse | 46 | 108.8 | 104.1 | 204.3 | 148.6 | 252.9 | 170.5 | 1.375 | 0 | 0 |

### 2.4 Mechanism and pressure per arm (mean of 5 seeds)

| block | arm | comp offered | comp completed | victim gw-queue P95 ms | victim user TTFT P95 ms | running mean | running max | waiting max | KV max | gw inflight max | GPU W mean | dyn. energy J | engine prefill+decode s | engine busy s | engine prompt tok | engine gen tok | prefix hit ratio |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a7_prefix_cache | attack | 74.6 | 74.6 | 380 | 523 | 3.86 | 8.0 | 0.0 | 0.056 | 8.0 | 308 | 33521 | 477 | 117 | 134902 | 20461 | 0.596 |
| a7_prefix_cache | control | 74.6 | 74.6 | 766 | 946 | 4.37 | 8.0 | 0.0 | 0.091 | 8.0 | 313 | 34130 | 543 | 118 | 134902 | 20460 | 0.191 |
| a7_prefix_cache_reset | attack | 74.6 | 74.6 | 380 | 537 | 3.86 | 8.0 | 0.0 | 0.057 | 8.0 | 308 | 33461 | 478 | 117 | 134902 | 20461 | 0.596 |
| a7_prefix_cache_reset | control | 74.6 | 74.6 | 768 | 943 | 4.36 | 8.0 | 0.2 | 0.086 | 8.0 | 313 | 33838 | 543 | 118 | 134902 | 20461 | 0.191 |
| a8_lifecycle_churn | attack | 74.6 | 28.6 | 40 | 179 | 3.49 | 7.6 | 0.0 | 0.025 | 7.8 | 308 | 25274 | 302 | 90 | 23752 | 15125 | 0.000 |
| a8_lifecycle_churn | control | 74.6 | 74.6 | 1725 | 1826 | 5.76 | 8.0 | 0.0 | 0.030 | 8.0 | 310 | 26082 | 550 | 93 | 23752 | 25455 | 0.000 |
| a8_retry_churn | attack | 112.2 | 74.6 | 1872 | 1968 | 6.08 | 8.0 | 0.0 | 0.030 | 8.0 | 310 | 26289 | 547 | 94 | 27812 | 27040 | 0.133 |
| a8_retry_churn | control | 112.2 | 112.2 | 9471 | 9582 | 7.12 | 8.0 | 0.0 | 0.031 | 8.0 | 310 | 28624 | 746 | 102 | 27812 | 34704 | 0.133 |
| a9_tok_prefill | attack | 74.6 | 74.6 | 44 | 642 | 2.40 | 7.8 | 0.8 | 0.152 | 8.0 | 303 | 32367 | 303 | 100 | 156060 | 9312 | 0.000 |
| a9_tok_prefill | control | 557.8 | 518.4 | 52294 | 52535 | 7.46 | 8.0 | 0.0 | 0.023 | 8.0 | 316 | 35838 | 964 | 125 | 85668 | 39943 | 0.000 |
| a9_tok_decode | attack | 122.8 | 122.8 | 2897 | 3036 | 6.38 | 8.0 | 0.0 | 0.032 | 8.0 | 310 | 34592 | 805 | 123 | 28995 | 37443 | 0.000 |
| a9_tok_decode | control | 294.0 | 294.0 | 10175 | 10372 | 5.10 | 8.0 | 0.0 | 0.022 | 8.0 | 298 | 31494 | 616 | 105 | 55548 | 25735 | 0.000 |
| a9_tok_longctx | attack | 23.2 | 0.8 | 0 | 195 | 1.26 | 5.0 | 0.0 | 0.036 | 5.2 | 267 | 27910 | 152 | 81 | 18111 | 7130 | 0.000 |
| a9_tok_longctx | control | 628.6 | 516.4 | 49393 | 49590 | 7.22 | 8.0 | 0.0 | 0.022 | 8.0 | 315 | 35688 | 950 | 125 | 84690 | 39514 | 0.000 |
| a9_tok_prefix_reuse | attack | 74.6 | 74.6 | 0 | 182 | 1.74 | 6.4 | 0.0 | 0.035 | 7.0 | 288 | 30522 | 216 | 94 | 99200 | 9312 | 0.551 |
| a9_tok_prefix_reuse | control | 557.8 | 520.4 | 52114 | 52288 | 7.61 | 8.0 | 0.0 | 0.022 | 8.0 | 316 | 35562 | 970 | 126 | 85891 | 40064 | 0.000 |
| a9_rate_prefill | attack | 74.6 | 74.6 | 36 | 616 | 2.41 | 8.0 | 1.4 | 0.153 | 8.0 | 302 | 32438 | 302 | 99 | 156060 | 9312 | 0.000 |
| a9_rate_prefill | control | 74.6 | 74.6 | 0 | 189 | 2.06 | 6.8 | 0.0 | 0.017 | 7.4 | 293 | 31312 | 254 | 103 | 25810 | 11699 | 0.000 |
| a9_rate_decode | attack | 122.8 | 122.8 | 3129 | 3237 | 6.33 | 8.0 | 0.0 | 0.032 | 8.0 | 311 | 34767 | 800 | 124 | 28995 | 37273 | 0.000 |
| a9_rate_decode | control | 122.8 | 122.8 | 1 | 185 | 2.63 | 7.8 | 0.0 | 0.020 | 8.0 | 302 | 32209 | 326 | 110 | 32350 | 14784 | 0.000 |
| a9_rate_longctx | attack | 23.2 | 0.8 | 0 | 201 | 1.25 | 4.8 | 0.0 | 0.035 | 5.4 | 268 | 27884 | 152 | 80 | 18111 | 7130 | 0.000 |
| a9_rate_longctx | control | 23.2 | 23.2 | 0 | 251 | 1.47 | 6.4 | 0.0 | 0.017 | 6.4 | 277 | 29099 | 179 | 87 | 18845 | 8410 | 0.000 |
| a9_rate_prefix_reuse | attack | 74.6 | 74.6 | 0 | 203 | 1.74 | 6.2 | 0.0 | 0.037 | 7.2 | 288 | 30545 | 216 | 94 | 99200 | 9312 | 0.551 |
| a9_rate_prefix_reuse | control | 74.6 | 74.6 | 0 | 162 | 2.07 | 7.0 | 0.0 | 0.018 | 7.4 | 294 | 31273 | 254 | 101 | 25810 | 11699 | 0.000 |

Gateway inflight is capped at `max_global_inflight: 8`. When the competitor floods it (the token-matched short controls send about 560–630 competitor requests, against 23–123 in the attack arm), victims wait in the FCFS gateway queue, not in vLLM. vLLM `waiting` stays at about 0 throughout.

### 2.5 Block-level endpoints: pre-registered (unchanged) and sensitivity (not pre-registered)

| block | pre-registered primary (as reported) | victim backend-TTFT P95 ratio | victim user-facing TTFT P95 ratio | energy-with-tail /1k auth | energy /1k realized tok | engine service s /1k auth |
|---|---|---|---|---|---|---|
| a7_prefix_cache | backend TTFT P95: 0.61 [0.56, 0.66] supported | 0.61 [0.56, 0.66] supported | 0.56 [0.45, 0.66] supported | 0.98 [0.97, 0.99] negative | 0.98 [0.97, 0.99] negative | 0.88 [0.87, 0.89] negative |
| a7_prefix_cache_reset | backend TTFT P95: 0.62 [0.57, 0.67] supported | 0.62 [0.57, 0.67] supported | 0.58 [0.46, 0.70] supported | 0.99 [0.97, 1.01] negative | 0.99 [0.97, 1.00] negative | 0.88 [0.87, 0.89] negative |
| a8_lifecycle_churn | backend TTFT P95: 0.98 [0.87, 1.06] negative | 0.98 [0.87, 1.06] negative | 0.11 [0.08, 0.14] supported | 0.97 [0.96, 0.98] negative | 1.45 [1.42, 1.48] supported | 0.55 [0.54, 0.56] supported |
| a8_retry_churn | backend TTFT P95: 1.12 [0.98, 1.23] negative | 1.12 [0.98, 1.23] negative | 0.22 [0.13, 0.29] supported | 0.93 [0.89, 0.97] negative | 1.17 [1.13, 1.21] negative | 0.73 [0.71, 0.76] supported |
| a9_tok_prefill | energy/1k auth: 0.90 [0.89, 0.92] negative | 1.79 [1.55, 2.03] supported | 0.01 [0.01, 0.01] supported | 0.91 [0.90, 0.92] negative | 0.69 [0.65, 0.73] supported | 0.31 [0.29, 0.33] supported |
| a9_tok_decode | energy/1k auth: 1.10 [1.07, 1.13] negative | 0.90 [0.71, 1.05] inconclusive | 0.37 [0.24, 0.51] supported | 1.09 [1.07, 1.12] negative | 1.34 [1.31, 1.38] supported | 1.31 [1.29, 1.33] supported |
| a9_tok_longctx | energy/1k auth: 0.78 [0.76, 0.81] inconclusive | 0.74 [0.57, 0.90] inconclusive | 0.00 [0.00, 0.01] supported | 0.80 [0.77, 0.82] inconclusive | 3.88 [3.60, 4.14] supported | 0.16 [0.15, 0.17] supported |
| a9_tok_prefix_reuse | energy/1k auth: 0.86 [0.84, 0.88] negative | 0.88 [0.68, 1.12] inconclusive | 0.00 [0.00, 0.00] supported | 0.87 [0.84, 0.89] negative | 1.00 [0.94, 1.07] negative | 0.22 [0.21, 0.23] supported |
| a9_rate_prefill | energy/1k auth: 0.29 [0.28, 0.30] supported | 3.44 [2.38, 4.50] supported | 3.61 [2.58, 4.66] supported | 0.29 [0.28, 0.30] supported | 0.24 [0.22, 0.25] supported | 0.33 [0.32, 0.34] supported |
| a9_rate_decode | energy/1k auth: 0.62 [0.61, 0.64] supported | 0.90 [0.83, 0.97] negative | 18.36 [14.85, 21.88] supported | 0.62 [0.61, 0.63] supported | 0.77 [0.75, 0.78] supported | 1.42 [1.41, 1.43] supported |
| a9_rate_longctx | energy/1k auth: 0.18 [0.15, 0.21] supported | 1.13 [0.67, 1.53] inconclusive | 1.12 [0.67, 1.53] inconclusive | 0.18 [0.15, 0.21] supported | 1.04 [0.96, 1.13] negative | 0.16 [0.13, 0.19] supported |
| a9_rate_prefix_reuse | energy/1k auth: 0.27 [0.26, 0.29] supported | 1.27 [1.19, 1.35] inconclusive | 1.25 [1.18, 1.32] inconclusive | 0.27 [0.26, 0.29] supported | 0.34 [0.33, 0.35] supported | 0.24 [0.23, 0.25] supported |

Mean ratio [95% percentile bootstrap CI, 10,000 resamples, seed 0, same function as the pipeline] and the two-sided 1.25 classification applied mechanically. A8 is pre-registered one-sided (`increase`), so its primary label is `negative`, as reported. Only the "pre-registered primary" column carries a claim. The other columns are diagnostics for this audit and are not re-classifications.

## 3. Long-context coverage = 0.0

- **What 0.0 was:** a `null` turned into 0 in my own post-run script
  (`scratchpad/suite_check.py`, `min((v.get("coverage") or 0) ...)`). The harness's own `cached_token_summary`
  (`evaluation/cache_hits.py:24-41`) returns `coverage: None` for a tenant with 0 completed requests (an empty denominator) and does not
  impute anything. Nothing in `results/` or `reports/` contains 0.0 coverage.
- **Why the denominator was empty:** the competitor's long-context requests failed with HTTP 400 (context length). See the table
  below and §0.4.
- **0 vs null vs unavailable** (raw `requests.parquet`, all 120 runs; `coverage.csv` has tenant × status × arm × seed):

| terminal status | requests | cached_tokens = 0 | cached_tokens > 0 | cached_tokens = null |
|---|---|---|---|---|
| backend_error | 224 | 0 | 0 | 224 |
| cancelled | 156 | 0 | 0 | 156 |
| completed | 29975 | 25363 | 4612 | 0 |
| timed_out | 1268 | 0 | 0 | 1268 |

  Completed requests: numeric `cached_tokens` in every row (0 is an observed zero-hit, which the owner's §7a server patch reports on both endpoints). Non-completed requests: always `null` (no usage block), kept as missing and excluded from the ratio, as documented.


Coverage by tenant, arm and seed, as stored in `metrics_summary.json` (long-context blocks):

| block | arm | seed | comp coverage | comp completed | comp non-completed | v00 | v01 | v02 |
|---|---|---|---|---|---|---|---|---|
| a9_rate_longctx | attack | 42 | null | 0 | 15 | 1.0 | 1.0 | 1.0 |
| a9_rate_longctx | attack | 43 | 1.0 | 2 | 17 | 1.0 | 1.0 | 1.0 |
| a9_rate_longctx | attack | 44 | 1.0 | 1 | 21 | 1.0 | 1.0 | 1.0 |
| a9_rate_longctx | attack | 45 | 1.0 | 1 | 29 | 1.0 | 1.0 | 1.0 |
| a9_rate_longctx | attack | 46 | null | 0 | 30 | 1.0 | 1.0 | 1.0 |
| a9_rate_longctx | control | 42 | 1.0 | 15 | 0 | 1.0 | 1.0 | 1.0 |
| a9_rate_longctx | control | 43 | 1.0 | 19 | 0 | 1.0 | 1.0 | 1.0 |
| a9_rate_longctx | control | 44 | 1.0 | 22 | 0 | 1.0 | 1.0 | 1.0 |
| a9_rate_longctx | control | 45 | 1.0 | 30 | 0 | 1.0 | 1.0 | 1.0 |
| a9_rate_longctx | control | 46 | 1.0 | 30 | 0 | 1.0 | 1.0 | 1.0 |
| a9_tok_longctx | attack | 42 | null | 0 | 15 | 1.0 | 1.0 | 1.0 |
| a9_tok_longctx | attack | 43 | 1.0 | 2 | 17 | 1.0 | 1.0 | 1.0 |
| a9_tok_longctx | attack | 44 | 1.0 | 1 | 21 | 1.0 | 1.0 | 1.0 |
| a9_tok_longctx | attack | 45 | 1.0 | 1 | 29 | 1.0 | 1.0 | 1.0 |
| a9_tok_longctx | attack | 46 | null | 0 | 30 | 1.0 | 1.0 | 1.0 |
| a9_tok_longctx | control | 42 | 1.0 | 406 | 0 | 1.0 | 1.0 | 1.0 |
| a9_tok_longctx | control | 43 | 1.0 | 494 | 0 | 1.0 | 1.0 | 1.0 |
| a9_tok_longctx | control | 44 | 1.0 | 558 | 51 | 1.0 | 1.0 | 1.0 |
| a9_tok_longctx | control | 45 | 1.0 | 570 | 246 | 1.0 | 1.0 | 1.0 |
| a9_tok_longctx | control | 46 | 1.0 | 554 | 264 | 1.0 | 1.0 | 1.0 |

- **Engine reconciliation:** residual = Δ`prefix_cache_hits_total` − Σ per-request `cached_tokens` = **0 in every run**.
  Attribution is `exact` where every request completed and `bounded` where some did not (A8, long-context attack arms).
  Engine hit ratio is 0.000 in every long-context arm.
- **Censoring and timeouts:** the competitor's HTTP 400 errors are fast failures, so the attack arm effectively ran victims alone (engine running
  mean 1.25 vs 7.2 in the token-matched control). Victims never timed out in long-context attack arms. They did time out in the token-matched long-context control
  (36 over 5 seeds, gateway queue, §2.2).

## 4. Energy metric audit (A9)

- **Power coverage:** 166–206 board-power samples per arm (exporter :9835, about 0.65 s
  scrape), max gap 2.00 s, window span 118.0–132.7 s. Pre-arm idle settled in
  120/120 runs (32.7–40.1 W in A9). The post-arm tail settled in 120/120.
- **Idle subtraction:** dynamic = ∫P dt − P_idle × span (`engine_counters.py:148-156`). P_idle is the median of the settled
  pre-arm samples (SM ≤ 500 MHz, util 0, spread ≤ 15 W).
- **Arm-window vs with-tail:** the with-tail ratio agrees with the arm-window ratio within 0.02 in every A9 block, with no change in
  direction or classification (§2.5).
- **Denominator:** pre-registered "authorized tokens" = planned `input_token_count + max_output_tokens`, victims included.
  Planned input is in whitespace words: realized/planned prompt tokens are 2.03–2.14 (pseudo-word filler) and 1.21
  (single-token prefix vocabulary, A7 / `prefix_reuse` competitor). So token-matched (`a9_tok_*`) arms are matched in planned
  units only. In realized tokens they differ: for seed 42, prefill 145,115 vs 117,517; decode 58,989 vs 71,841; prefix reuse 95,576
  vs 117,517; long context 20,156 vs 101,172.
- **Absolute energy is nearly flat:** 27.0–37.3 kJ per arm, mean board power
  261–317 W, against about 34 W idle. With identical victims (about 0.9 rps) the GPU is near peak power
  for the whole window in every arm, so dynamic energy hardly tracks the competitor's token volume. Per 1k tokens, the result is set
  by the denominator. Board power also includes the victims' work (a documented confounder).

### 4.1 A9 primary (H9) classification, as pre-registered (unchanged), and validity

| block | mean ratio | 95% CI | pre-registered classification | audit status |
|---|---|---|---|---|
| a9_tok_prefill | 0.904 | [0.891, 0.916] | negative | valid as computed; matched in planned (word) units only, realized tokens differ |
| a9_tok_decode | 1.099 | [1.072, 1.125] | negative | valid as computed; matched in planned (word) units only, realized tokens differ |
| a9_tok_longctx | 0.784 | [0.759, 0.809] | inconclusive | INVALID: manipulation failed (112/116 competitor requests HTTP 400) |
| a9_tok_prefix_reuse | 0.859 | [0.838, 0.882] | negative | valid as computed; matched in planned (word) units only, realized tokens differ |
| a9_rate_prefill | 0.289 | [0.277, 0.302] | supported | valid as computed; denominator-dominated by design (authorized tokens differ 1.7–3.8×) |
| a9_rate_decode | 0.624 | [0.611, 0.637] | supported | valid as computed; denominator-dominated by design (authorized tokens differ 1.7–3.8×) |
| a9_rate_longctx | 0.181 | [0.153, 0.210] | supported | INVALID: manipulation failed (112/116 competitor requests HTTP 400) |
| a9_rate_prefix_reuse | 0.272 | [0.261, 0.285] | supported | valid as computed; denominator-dominated by design (authorized tokens differ 1.7–3.8×) |

Valid series: token-matched prefill, decode and prefix-reuse are **negative** for H9 (CI inside (0.8, 1.25)). Rate-matched prefill,
decode and prefix-reuse are **supported** (CI ≤ 0.8). In the rate-matched series that means energy per authorized token is lower for the heavy
family, mainly because arm energy stays nearly constant while authorized tokens rise 1.7–3.8×. Both long-context results (token-matched `inconclusive`,
rate-matched `supported`) are **invalid** and should be reported as such, not interpreted.

## 5. Provenance (from the 120 run manifests and 12 report manifests)

- **Commit:** `dbd7f178c6ec3da2842e712c9ef1258767425f7e` in all 120 runs. **Dirty:** `[True]`, meaning dirty in all runs. The only
  uncommitted change was `experiments/PLAN.md`, the S0 result note, later committed as 856fc07. The run manifests do not list
  dirty files, so this comes from the session record, not from the manifest.
- **Arm identity:** run `experiment_id` = `<block>__attack|__control` in 120/120 runs. Report `run_dirs` map every
  seed to one attack and one control run.
- **Arm order:** counterbalanced: even seeds attack→control, odd seeds control→attack (`arm_order` in the report manifests).
  It matches the run start timestamps in 60/60 pairs.
- **Hashes:** `config_sha256` is constant within each block×arm. `trace_sha256` is distinct per seed (5 per block×arm), and no trace hash is shared
  across blocks.
- **Backend:** `base_url` http://192.168.86.173:8000, vLLM `{'version': '0.17.1'}`. Server start from
  `engine_state_at_start.process_start_time_seconds` = `1795268683.89` in all 120 runs.
- **Missing fields:** `run_context.backend_identity.model_revision = null` (not reported by the server). Per-run manifests
  contain no `server_start` key (it lives in `metrics_summary.json → engine_counters.engine_state_at_start`), no arm-order field
  (that is only in the report manifest), and no list of dirty files. Report manifests have no `git` block (the summary I gave earlier said "dirty: None" because
  the field is missing, not because the tree was clean). The pre-block hygiene reset is recorded in
  `reports/v3/<block>/prerun_cache_reset.json`, not in any manifest.

## 6. Validity status per block

| block | metric | pre-registered result | status |
|---|---|---|---|
| a7_prefix_cache (S1) | ttft_p95, two-sided | 0.61 [0.56, 0.66] supported | valid; **exploratory** by design (no per-arm reset). Manipulation check passed (hit ratio 0.596 vs 0.191, Δ 0.41 ≥ 0.1). Direction: victim faster when the competitor reuses its prefix. User-facing TTFT agrees (0.56). |
| a7_prefix_cache_reset (S1′) | ttft_p95, two-sided | 0.62 [0.57, 0.67] supported | valid, **confirmatory** (per-arm verified reset). Same manipulation check and direction. |
| a8_lifecycle_churn | ttft_p95, increase | 0.98 [0.87, 1.06] negative | valid as computed. Note: backend TTFT excludes the gateway queue. Victims in the control wait much longer in the gateway (P95 1.7 s vs 0.04 s), because attack-arm cancellations free inflight slots. One-sided label is unchanged under either definition. |
| a8_retry_churn | ttft_p95, increase | 1.12 [0.98, 1.23] negative | valid as computed. Same gateway-queue note (control P95 9.5 s vs 1.9 s), and the label is unchanged under either definition. |
| a9_tok_prefill / decode / prefix_reuse | energy/1k auth, two-sided | negative (all three) | primary valid as computed, with the denominator caveat (§4). Secondary TTFT is **pending validation**: control victims censored by 60 s gateway timeouts, backend vs user TTFT definition. |
| a9_tok_longctx | energy/1k auth, two-sided | 0.78 inconclusive | **INVALID**: 112/116 competitor requests rejected (context length). |
| a9_rate_prefill / decode / prefix_reuse | energy/1k auth, two-sided | supported (all three, ratio < 0.8) | primary valid as computed, denominator-dominated (§4). Secondary victim backend TTFT: prefill 3.44×, decode 0.90×, prefix reuse 1.27× (not pre-registered claims). |
| a9_rate_longctx | energy/1k auth, two-sided | 0.18 supported | **INVALID**: same rejection as tok_longctx. |

S0 (A7-V) noise floor: unaffected. It used the same backend-TTFT definition as the A7 blocks, so the comparison inside the suite is consistent.

## 7. Corrections required

Analysis code. Recompute offline from existing data; no rerun:
1. `attack_effect.write_report` / `_figures`: label the headline, per-seed columns and y-axis from `analysis["metric"]`
   (for example "J per 1k authorized tokens"), not with a fixed "victim slowdown" / "ms". For A9, also print the secondary victim TTFT ratio
   separately and clearly labelled.
2. `attack_effect.run_metrics`: name the TTFT it uses. Either rename the current column `backend_ttft_ms` and add the
   user-facing `ttft_ms = t_first_token − t_offered` (as in `METRIC_DEFINITIONS.md` and `metrics.py`), or amend
   `METRIC_DEFINITIONS.md`. **Which definition is the pre-registered one is the owner's decision.** The code has used backend TTFT
   since Phase 5, including the A1–A5 headlines. Changing it would change those results, so this needs an ADR. It is not a silent fix.
3. Report victim timeouts and gateway-queue time beside every TTFT ratio, and flag a block as censored when either arm has
   victim timeouts. Today they appear only as a count column.
4. Add a manipulation check that fails a block (or marks it invalid) when the competitor's completed fraction falls below a
   pre-set floor. Today a block whose competitor was 97% rejected gets a classification.
5. My `suite_check.py`: use `None`, not `or 0`, for missing coverage. This is not part of the harness.

Scenario and harness. Needs owner approval, a protocol amendment, and new pre-registration before any rerun:
6. The `scenario.py:284` safety check compares planned words with `model_max_len`. With about 2.1 real tokens per filler word it should
   use the live tokenizer, or a measured tokens-per-word bound. `a9_*_longctx` must be re-sized so the real input stays ≤ 3,840
   tokens. This changes the family's definition, so it is a protocol change.
7. A design-doc statement is wrong for the filler: "Tokenized lengths are verified equal across arms on the live tokenizer (single-token vocab)"
   (`A7_A9_EXPERIMENT_DESIGN.md:50`) holds for the nonce and prefix vocabularies only. Pseudo-word filler is about 2.1 tokens per word. Victim
   prompts are still identical across arms, so victim matching holds, but token-budget matching in A9 is in planned units.
   This should go into `KNOWN_LIMITATIONS.md`.
8. Run a smoke test for each family before a suite. No long-context smoke was run.

## 8. Are GPU reruns needed?

- **No** for A7 (S1, S1′), A8a, A8b, and the six valid A9 blocks. Their data is intact, and items 1–5 are analysis-only.
- **Yes, but only after approval and re-pre-registration**, for `a9_tok_longctx` and `a9_rate_longctx` (about 50 min for both at the
  observed pace, plus a long-context smoke). A new `isolation_salt` is required (warm-cache guard), or a server restart, which
  would start a new non-pooled series.
- If the owner picks user-facing TTFT as the pre-registered definition (item 2), the TTFT results can still be recomputed
  from the existing timestamps, with no rerun needed.

