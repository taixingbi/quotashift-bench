# Protocol v4 — smoke + calibration report (2026-11-22) — FOR REVIEW; R1–R3 NOT started

## Code and server
- Commit 46e37f686c2591a2d12effe5b6fe21370396ccdb (branch protocol-v4, pushed), tree clean for every run (provenance gate).
- Frozen traces: experiments/v4/FROZEN_TRACES.json (live tokenizer, created 2026-11-22T04:23Z on 6116868; enforced pre-send).
- Server (read-only: /version, /server_info, /metrics; SSH refused, publickey): vLLM 0.17.1, Qwen/Qwen2.5-7B-Instruct, fp16, TP 1,
  max_model_len 4096, gpu_memory_utilization 0.8, prefix caching ON (sha256), chunked prefill ON, block_size 16, 4662 GPU KV blocks,
  CUDA graphs FULL_AND_PIECEWISE (max capture 512), seed 0. Server start 1795268683.89, unchanged before, during and after all runs.
- max_num_batched_tokens = 2048 and max_num_seqs = 256: INFERRED (compile_ranges_split_points=[2048]; max_cudagraph_capture_size 512
  = 2 x max_num_seqs under vLLM defaults); not exposed by the server, NOT verified.
- Model weight revision: UNVERIFIED (server reports revision=None, tokenizer_revision=None; no host shell access).
- GPU: RTX 3090 (exporter :9835), torch 2.10.0+cu128, driver 595.71.05. Snapshot: reports/v4/server_info_preflight.json.

## Smokes (4/4 passed, 08:09–08:19, 10.7 min)
All 11 validity gates passed in each; extra checks (telemetry present, cache isolation: verified pre-block reset 96->0 probe hits,
prefix hit 0.000, no unrelated traffic, no leak; request conservation offered = admitted = completed, 0 rejected/timeout/error) passed.
r2f_s96 and r2f_s96_direct classified FEASIBLE (417/417 competitor requests) — the protocol's expectation of overload at s=96 did not hold;
r2b_s2048 feasible (KV max 0.141).

## Calibration decision
Rule (frozen, scripts/v4_analysis.py): every probe at L and all lower grid loads must have integrity gates passing, competitor completion
>= 0.98, victim censoring 0, gateway saturation <= 0.25. L200: P/D/S feasible (max saturation 0.097). L300: D fails saturation (0.369,
0.364). L400: D (0.828) and S (0.356) fail saturation. => L* = 200 (decision: run experiments/v4/r1/*_L200.yaml — NOT started).
No probe was rerun; no threshold changed. The A/A replicates of a probe replay the same frozen trace (identical token accounting) with
distinct isolation salts.

## Tables — all candidate loads (generated, read-only from reports/v4/calibration)

## Selection (frozen rule, scripts/v4_analysis.py select-load)

```json
{
 "rule": {
  "min_competitor_completion": 0.98,
  "max_victim_censored": 0.0,
  "max_gw_saturation": 0.25,
  "integrity_gates": [
   "backend_error_rate",
   "http_400_rate",
   "admission_rate",
   "primary_metric_present",
   "tokenized_context",
   "planned_vs_reported_tokens",
   "provenance",
   "arrival_coverage",
   "realized_output_equals_authorized"
  ]
 },
 "feasible_at": {
  "200": true,
  "300": false,
  "400": false
 },
 "selected_load": 200,
 "decision": "run experiments/v4/r1/*_L200.yaml"
}
```

| probe | feasible | min completion | max censored | max gw saturation | failed integrity | missing |
|---|---|---|---|---|---|---|
| v4_cal_D_L200 | True | 1.000 | 0.000 | 0.097 | - | - |
| v4_cal_D_L300 | False | 1.000 | 0.000 | 0.369 | - | - |
| v4_cal_D_L400 | False | 1.000 | 0.000 | 0.828 | - | - |
| v4_cal_P_L200 | True | 1.000 | 0.000 | 0.011 | - | - |
| v4_cal_P_L300 | True | 1.000 | 0.000 | 0.016 | - | - |
| v4_cal_P_L400 | True | 1.000 | 0.000 | 0.006 | - | - |
| v4_cal_S_L200 | True | 1.000 | 0.000 | 0.037 | - | - |
| v4_cal_S_L300 | True | 1.000 | 0.000 | 0.144 | - | - |
| v4_cal_S_L400 | False | 1.000 | 0.000 | 0.356 | - | - |

Missing probes: none


## Validity and completion

| probe | rep | rc | gates_passed | failed | c_off | c_adm | c_done | c_compl | c_adm_rate | c_timeout | c_err | c_cancel | v_off | v_adm_rate | v_rej | v_timeout | v_cens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P_L200 | A | 0 | True | - | 23 | 23 | 23 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| P_L200 | B | 0 | True | - | 23 | 23 | 23 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| P_L300 | A | 0 | True | - | 34 | 34 | 34 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| P_L300 | B | 0 | True | - | 34 | 34 | 34 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| P_L400 | A | 0 | True | - | 45 | 45 | 45 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| P_L400 | B | 0 | True | - | 45 | 45 | 45 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| D_L200 | A | 0 | True | - | 75 | 75 | 75 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| D_L200 | B | 0 | True | - | 75 | 75 | 75 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| D_L300 | A | 0 | True | - | 112 | 112 | 112 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| D_L300 | B | 0 | True | - | 112 | 112 | 112 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| D_L400 | A | 0 | True | - | 150 | 150 | 150 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| D_L400 | B | 0 | True | - | 150 | 150 | 150 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| S_L200 | A | 0 | True | - | 188 | 188 | 188 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| S_L200 | B | 0 | True | - | 188 | 188 | 188 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| S_L300 | A | 0 | True | - | 281 | 281 | 281 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| S_L300 | B | 0 | True | - | 281 | 281 | 281 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| S_L400 | A | 0 | True | - | 375 | 375 | 375 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |
| S_L400 | B | 0 | True | - | 375 | 375 | 375 | 1.000 | 1.000 | 0 | 0 | 0 | 121 | 1.000 | 0 | 0 | 0.000 |


## Victim latency (absolute, ms) and SLO

| probe | rep | user_ttft_p50 | user_ttft_p95 | backend_ttft_p95 | gwq_p50 | gwq_p95 | e2e_p95 | tpot_p95 | slo |
|---|---|---|---|---|---|---|---|---|---|
| P_L200 | A | 81 | 208 | 208 | 0 | 0 | 1665 | 25 | 1.000 |
| P_L200 | B | 82 | 199 | 199 | 0 | 0 | 1665 | 25 | 1.000 |
| P_L300 | A | 83 | 249 | 249 | 0 | 0 | 1770 | 27 | 1.000 |
| P_L300 | B | 82 | 236 | 236 | 0 | 0 | 1768 | 27 | 1.000 |
| P_L400 | A | 82 | 304 | 304 | 0 | 0 | 1797 | 27 | 1.000 |
| P_L400 | B | 81 | 271 | 271 | 0 | 0 | 1799 | 27 | 1.000 |
| D_L200 | A | 82 | 187 | 109 | 0 | 103 | 1487 | 21 | 1.000 |
| D_L200 | B | 81 | 182 | 110 | 0 | 103 | 1495 | 21 | 1.000 |
| D_L300 | A | 93 | 2193 | 105 | 0 | 2130 | 3516 | 21 | 0.917 |
| D_L300 | B | 89 | 2208 | 103 | 0 | 2148 | 3529 | 21 | 0.917 |
| D_L400 | A | 2315 | 9735 | 166 | 2241 | 9592 | 11007 | 22 | 0.479 |
| D_L400 | B | 1939 | 9694 | 173 | 1780 | 9589 | 11020 | 22 | 0.504 |
| S_L200 | A | 81 | 150 | 119 | 0 | 54 | 1457 | 22 | 1.000 |
| S_L200 | B | 80 | 160 | 120 | 0 | 46 | 1467 | 22 | 1.000 |
| S_L300 | A | 88 | 305 | 149 | 0 | 210 | 1668 | 22 | 1.000 |
| S_L300 | B | 86 | 307 | 112 | 0 | 213 | 1671 | 22 | 1.000 |
| S_L400 | A | 134 | 684 | 159 | 0 | 587 | 2067 | 23 | 1.000 |
| S_L400 | B | 131 | 655 | 166 | 0 | 569 | 2003 | 22 | 1.000 |


## Gateway / engine pressure

| probe | rep | sat | inflight_mean | gw_q_mean | gw_q_max | req_bound | eng_run_mean | eng_run_max | eng_wait_mean | eng_wait_max | eng_bound |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P_L200 | A | 0.011 | 1.68 | 0.00 | 0 | 0.000 | 1.55 | 8 | 0.00 | 0 | 0.000 |
| P_L200 | B | 0.011 | 1.67 | 0.00 | 0 | 0.000 | 1.55 | 8 | 0.00 | 0 | 0.000 |
| P_L300 | A | 0.016 | 1.75 | 0.00 | 0 | 0.000 | 1.64 | 8 | 0.00 | 0 | 0.000 |
| P_L300 | B | 0.016 | 1.75 | 0.00 | 0 | 0.000 | 1.63 | 8 | 0.00 | 0 | 0.000 |
| P_L400 | A | 0.006 | 1.86 | 0.00 | 0 | 0.000 | 1.75 | 8 | 0.00 | 0 | 0.000 |
| P_L400 | B | 0.005 | 1.91 | 0.00 | 0 | 0.000 | 1.79 | 8 | 0.00 | 0 | 0.000 |
| D_L200 | A | 0.097 | 4.59 | 0.03 | 2 | 0.021 | 4.51 | 8 | 0.00 | 0 | 0.000 |
| D_L200 | B | 0.087 | 4.49 | 0.03 | 2 | 0.026 | 4.45 | 8 | 0.00 | 0 | 0.000 |
| D_L300 | A | 0.369 | 6.04 | 0.66 | 8 | 0.217 | 5.99 | 8 | 0.00 | 0 | 0.000 |
| D_L300 | B | 0.364 | 6.06 | 0.69 | 9 | 0.232 | 5.98 | 8 | 0.00 | 0 | 0.000 |
| D_L400 | A | 0.828 | 7.47 | 5.81 | 22 | 0.781 | 7.28 | 8 | 0.00 | 0 | 0.000 |
| D_L400 | B | 0.786 | 7.24 | 5.46 | 22 | 0.716 | 7.17 | 8 | 0.00 | 0 | 0.000 |
| S_L200 | A | 0.032 | 3.62 | 0.01 | 2 | 0.005 | 3.44 | 8 | 0.00 | 0 | 0.000 |
| S_L200 | B | 0.037 | 3.59 | 0.03 | 2 | 0.021 | 3.44 | 8 | 0.00 | 0 | 0.000 |
| S_L300 | A | 0.123 | 4.73 | 0.10 | 4 | 0.048 | 4.49 | 8 | 0.00 | 0 | 0.000 |
| S_L300 | B | 0.144 | 4.75 | 0.12 | 5 | 0.053 | 4.44 | 8 | 0.00 | 0 | 0.000 |
| S_L400 | A | 0.356 | 5.87 | 0.52 | 5 | 0.239 | 5.57 | 8 | 0.00 | 0 | 0.000 |
| S_L400 | B | 0.326 | 5.88 | 0.49 | 5 | 0.204 | 5.59 | 8 | 0.00 | 0 | 0.000 |


## GPU / KV / energy

| probe | rep | gpu_util | kv_max | power_w | E_kJ | Edyn_kJ | Edyn_per_1k_real_J |
|---|---|---|---|---|---|---|---|
| P_L200 | A | 73.2 | 0.037 | 274 | 32.80 | 28.90 | 719.7 |
| P_L200 | B | 74.0 | 0.037 | 274 | 32.90 | 28.76 | 716.4 |
| P_L300 | A | 76.6 | 0.037 | 281 | 33.74 | 28.69 | 554.3 |
| P_L300 | B | 75.3 | 0.036 | 279 | 33.57 | 29.57 | 571.1 |
| P_L400 | A | 78.6 | 0.047 | 283 | 33.88 | 29.48 | 465.1 |
| P_L400 | B | 78.7 | 0.048 | 282 | 33.75 | 29.79 | 470.0 |
| D_L200 | A | 98.3 | 0.023 | 308 | 38.33 | 34.11 | 855.6 |
| D_L200 | B | 98.5 | 0.023 | 309 | 38.42 | 34.18 | 857.5 |
| D_L300 | A | 99.0 | 0.025 | 310 | 39.10 | 34.56 | 668.5 |
| D_L300 | B | 99.0 | 0.025 | 311 | 39.15 | 34.95 | 676.0 |
| D_L400 | A | 99.5 | 0.029 | 312 | 41.33 | 36.89 | 577.7 |
| D_L400 | B | 99.5 | 0.029 | 311 | 41.85 | 37.13 | 581.4 |
| S_L200 | A | 94.4 | 0.013 | 303 | 36.44 | 31.72 | 794.4 |
| S_L200 | B | 92.5 | 0.013 | 303 | 36.37 | 32.35 | 810.3 |
| S_L300 | A | 96.9 | 0.013 | 308 | 37.27 | 32.54 | 627.8 |
| S_L300 | B | 97.3 | 0.013 | 308 | 37.32 | 33.28 | 642.1 |
| S_L400 | A | 97.5 | 0.013 | 307 | 37.54 | 33.33 | 521.9 |
| S_L400 | B | 97.3 | 0.013 | 309 | 37.65 | 33.39 | 522.8 |


## Token accounting and cache

| probe | rep | auth_tok | c_auth_tok | c_real_tok | real_tok | c_real_tok_s | tok_reported | tok_mismatch | out_mismatch | prefix_hit | victim_cached | comp_cached | arr_first | arr_last | unrelated | leak |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| P_L200 | A | 40150 | 24288 | 24288 | 40150 | 202.4 | 144 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.039 | 0.982 | False | False |
| P_L200 | B | 40150 | 24288 | 24288 | 40150 | 202.4 | 144 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.039 | 0.982 | False | False |
| P_L300 | A | 51766 | 35904 | 35904 | 51766 | 299.2 | 155 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.005 | 0.982 | False | False |
| P_L300 | B | 51766 | 35904 | 35904 | 51766 | 299.2 | 155 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.005 | 0.982 | False | False |
| P_L400 | A | 63382 | 47520 | 47520 | 63382 | 396.0 | 166 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.005 | 0.982 | False | False |
| P_L400 | B | 63382 | 47520 | 47520 | 63382 | 396.0 | 166 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.005 | 0.982 | False | False |
| D_L200 | A | 39862 | 24000 | 24000 | 39862 | 200.0 | 196 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.005 | 0.993 | False | False |
| D_L200 | B | 39862 | 24000 | 24000 | 39862 | 200.0 | 196 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.005 | 0.993 | False | False |
| D_L300 | A | 51702 | 35840 | 35840 | 51702 | 298.7 | 233 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.005 | 0.993 | False | False |
| D_L300 | B | 51702 | 35840 | 35840 | 51702 | 298.7 | 233 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.005 | 0.993 | False | False |
| D_L400 | A | 63862 | 48000 | 48000 | 63862 | 400.0 | 271 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.005 | 0.993 | False | False |
| D_L400 | B | 63862 | 48000 | 48000 | 63862 | 400.0 | 271 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.005 | 0.993 | False | False |
| S_L200 | A | 39926 | 24064 | 24064 | 39926 | 200.5 | 309 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.005 | 0.993 | False | False |
| S_L200 | B | 39926 | 24064 | 24064 | 39926 | 200.5 | 309 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.005 | 0.993 | False | False |
| S_L300 | A | 51830 | 35968 | 35968 | 51830 | 299.7 | 402 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.004 | 0.998 | False | False |
| S_L300 | B | 51830 | 35968 | 35968 | 51830 | 299.7 | 402 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.004 | 0.998 | False | False |
| S_L400 | A | 63862 | 48000 | 48000 | 63862 | 400.0 | 496 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.004 | 0.998 | False | False |
| S_L400 | B | 63862 | 48000 | 48000 | 63862 | 400.0 | 496 | 0 | 0 | 0.000 | 0.0 | 0.0 | 0.004 | 0.998 | False | False |

