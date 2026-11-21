# Experiment plan — protocol v2 replication + E-series (prepared 2026-11-21, nothing below has run)

Two separately versioned suites. Historical A1–A5 (protocol v1, `experiments/*.yaml`, results archived per
`docs/HISTORICAL_ARCHIVE.md`) are frozen: their definitions, schedule hashes (test-pinned), thresholds and
results are not modified, and `quotashift experiment` refuses to overwrite an existing report directory.

Pre-registration: every metric, threshold and tolerance below is fixed in the YAML files **before** any run.
Changes go into "Amendments" with a date, before the affected runs. Negative results and failed runs are
reported. A finding is claimed only from real GPU runs (`synthetic_backend: false`) with clean attribution
(`unrelated_traffic_suspected: false` on every arm used).

## Fixed setup

- Target `selfhost`: 192.168.86.173, vLLM 0.17.1, `Qwen/Qwen2.5-7B-Instruct`, `max_model_len` 4096, GPU
  stated by the owner as RTX 3090 (`gpu_type_source: owner_stated`). The 0.34.0 host (.176) is never pooled
  with .173; using it would be a separate, separately analysed series.
- Prefix caching is ON on .173 as deployed (`vllm:cache_config_info`). Scenarios declare
  `expect_prefix_caching`; runs fail closed if the server differs.
- Protocol v2 everywhere (ADR-Q13): per-arm salted nonce, counterbalanced arm order, per-arm counter snapshots.
  Use a new `isolation_salt` per replication of the same scenario (the server cache persists across runs).
- Fixed admission per attack/control pair (FCFS; gateway limits only in E2). The workload is the variable.
- Statistics: paired seeds; one ratio per seed; 95% percentile-bootstrap CI over seeds (independent runs,
  never requests). A result is "supported" only if the CI clears the pre-registered threshold.
- Prerequisite P1 (GPU telemetry): run `quotashift gpu-exporter --host <LAN IP>` on the GPU host and set
  `gpu_exporter_url` in `configs/targets/selfhost.yaml`. Until then manifests record GPU telemetry as absent.

## Target reference — self-hosted sample output (added 2026-11-21)

Operational guide (server launch, GPU exporter, preflight, metrics): **docs/SELFHOST.md**.

Source: <https://github.com/taixingbi/vllm-qwen-serving/blob/main/self-hosted-sample-output.md> (the owner's capture
from 192.168.86.173:8000, sent from a Mac on the same LAN). It is a reference for what the target exposes,
**not** a QuotaShift measurement; its numbers are never used as results.

What it shows about the target:
- OpenAI-compatible `POST /v1/chat/completions` with `Qwen/Qwen2.5-7B-Instruct`; `usage.prompt_tokens_details`
  is `null` (so per-request cached tokens stay unobservable, which matches KNOWN_LIMITATIONS). The chat template adds
  system/role tokens (a 7-word user message counted as 38 prompt tokens), which is why the harness compares realized
  `prompt_tokens` across arms and doesn't rely on planned word counts.
- `GET /metrics` exposes, in addition to the counters the harness already reads (`num_requests_running/waiting`,
  `kv_cache_usage_perc`, `prefix_cache_{queries,hits}_total`, `num_preemptions_total`, `prompt_tokens_total`):
  - `vllm:prompt_tokens_by_source_total{source=local_compute|local_cache_hit|external_kv_transfer}`: a direct
    engine counter for prefill-computed tokens;
  - `vllm:estimated_flops_per_gpu_total` and `vllm:estimated_{read,write}_bytes_per_gpu_total`: MFU counters,
    **0 in the capture** (they appear to be off unless MFU tracking is enabled on the server);
  - `vllm:engine_sleep_state{sleep_state=awake|weights_offloaded|discard_all}`;
  - `process_start_time_seconds`: the server process start time.
- At capture time the server had been up ~34 h, with ~7.13M prompt tokens, ~16.8% prefix-cache hit rate and 0
  preemptions. The cache is therefore long-lived and warm across runs, which is why each replication gets a new
  `isolation_salt`.

Planned harness follow-ups (not implemented yet; each gets a test and a DECISIONS entry before use):
1. **Preflight checks** (all suites): record `process_start_time_seconds` before and after each arm, and flag
   a server restart (counter reset) if it changes. Require `engine_sleep_state{awake}=1` and
   `num_requests_running = waiting = 0` before an arm starts (fail closed otherwise).
2. **A7/A9 prefill accounting:** read `prompt_tokens_by_source_total` deltas and report `local_compute` as the
   measured prefill-computed tokens. Keep the current estimate (Δprompt − Δprefix hits) alongside it and report
   any disagreement. This doesn't change any pre-registered metric (the estimate is a secondary metric).
3. **A9 compute proxy (optional, owner action):** if the owner enables MFU tracking on vLLM, Δ`estimated_flops_per_gpu_total`
   per 1k authorized tokens becomes an additional *secondary* A9 metric. It doesn't replace the pre-registered
   primary metric (GPU dynamic energy), which still needs the GPU exporter (P1). Before enabling MFU, confirm the
   exact vLLM flag in the 0.17.1 docs; nothing is assumed here.
4. **Pre-suite snapshot:** save one `curl -s http://192.168.86.173:8000/metrics | grep '^vllm:'` and one
   `/v1/models` response per suite under `reports/<suite>/target_snapshot/`, so each report records the server
   state it ran against.

## Suite R — A2–A5 replication under protocol v2 (`experiments/v2/`)

Primary metric unchanged: victim TTFT P95 amplification (attack ÷ matched control), threshold 1.5×.

| Block | Files | Seeds × arms | Runs | Est. time |
|---|---|---|---|---|
| R1 cache ON | `a{2..5}_*_v2.yaml` | 5 × 2 | 40 | ~63 min |
| R2 cache OFF (owner restarts vLLM with `--no-enable-prefix-caching`) | `*_v2_nocache.yaml` | 5 × 2 | 40 | ~63 min |
| R3 A2 rate-matched sweep (ADR-Q12), cache ON | `a2_rate_in{128,256,512,768}_v2.yaml` | 5 × 2 per point | 40 | ~50 min |
| R3' same, cache OFF (optional) | `a2_rate_in*_v2_nocache.yaml` | 5 × 2 | 40 | ~50 min |
| **Total (R1–R3)** | | | **120** | **~3 h** |

Times are scaled from the historical runs (A2 12.5, A3 10.5, A4 10.3, A5 30 min per 5 paired seeds). The v1
files `experiments/a2_rate_in*.yaml` were written for ADR-Q12 but never run; they are superseded by the v2
copies and should not be run. ADR-Q12's secondary analysis (Spearman ρ of attack-arm TTFT vs L) still needs an
analysis script.

Command (per file): `uv run quotashift experiment experiments/v2/<f>.yaml --reps 5 --live --path gateway
--out reports/v2/<scenario_id>`. Each report lists per-arm hit ratios, arm order and attribution flags, and is
compared explicitly against the v1 result for the same scenario (agreements and inconsistencies both reported).

## Suite E — multi-tenant characterization (`experiments/eseries/`)

| ID | File(s) | What varies | Path(s) | Seeds | Runs | Est. time |
|---|---|---|---|---|---|---|
| E0 | `e0_single_tenant` | path | direct, gateway | 5 | 10 | ~22 min |
| E1 | `e1_steady_3t` | path | direct, gateway | 5 | 10 | ~22 min |
| E2 | `e2_token_saturation` | phase: competitor 0.5× → 2× its TPM | gateway | 3 | 3 | ~10 min |
| E3 | `e3_noisy_neighbor` | bursty prefill competitor vs rate-matched short | direct, gateway | 5 × 2 arms | 20 | ~43 min |
| E4 | `e4_shape_{prefill,decode,mixed}` | competitor shape vs token-matched short | direct | 5 × 2 arms × 3 | 30 | ~65 min |
| E5 | `e5_scaling_{3,10,30}t` | tenant count at fixed 3.0 rps total | direct, gateway | 5 × 3 | 30 | ~65 min |
| E6 | `e6_kv_pressure` | long-context competitor rate 0.2→0.5→1.0 rps vs rate-matched short | direct | 3 × 2 arms | 6 | ~19 min |
| **Total** | | | | | **109** | **~4.1 h** |

Wall-clock per run ≈ runtime + drain (≈5–10 s) + startup. Planned requests per seed (dry-run): E0 115,
E1 175, E2 379, E3 204, E4 179, E5 337–344, E6 219.

Commands: single-arm series (E0, E1, E2, E5) —
`uv run quotashift run-local experiments/eseries/<f>.yaml --live --path <direct|gateway> --seed <N>`;
paired series (E3, E4, E6) — `uv run quotashift experiment experiments/eseries/<f>.yaml --live --reps <n>
--path <direct|gateway> --out reports/eseries/<scenario_id>_<path>`.

Pre-registered expectations (descriptive unless stated):
- **E0:** gateway − direct TTFT P50 overhead < 5 ms per seed; otherwise reported as measurable overhead.
- **E1:** per-tenant attribution conserved (engine token deltas == sum of client usage); Jain index over SLO
  attainment ≥ 0.95.
- **E2 (correctness):** zero `rate_limited` rejections in `under_quota`; in `over_quota` admitted reserved tokens
  per rolling 60 s ≤ TPM; victims' completion rate ≥ 99%. Quota exhaustion (429 `rate_limited:*`) is reported
  separately from GPU saturation (vLLM waiting > 0, TTFT growth).
- **E3/E4/E6 (primary):** victim TTFT P95 ratio per seed, threshold 1.5×. E4 secondary: victim TPOT P95 ratio.
  E4 caveat stated in advance: token-matched controls change request count/rate, so shape and rate are mixed.
- **E5:** victim TTFT P95 and SLO goodput vs tenant count at fixed total load; fairness (Jain) per run.
- **E6:** KV usage max, preemption delta, waiting-queue max per phase; the level at which preemptions appear,
  or that they did not appear in range.

## Disk

Measured per run: 108–112 KB (v2 live smoke, ~35–60 requests) and ~292 KB (historical prefill-heavy A2 run).
229 runs (R1–R3 + E) at ≤ 400 KB each → **< 100 MB**, plus reports (< 5 MB). Archive results to an external
disk after each suite (only one disk was available on 2026-11-21).

## Order

0. ~~Implement target-reference follow-ups 1, 2 and 4~~ **done 2026-11-21** (preflight checks, `prompt_tokens_by_source`, target snapshot), plus a warm-cache re-run guard. Validated live on .173.
1. P1 GPU exporter on the GPU host; commit the code + configs (manifests record git SHA and a dirty flag).
2. R1 (cache ON) → owner restarts vLLM with caching OFF → R2 → restart with caching ON → R3.
3. E0 → E1 → E2 (validates baseline, overhead and quota correctness) → E3–E6.
No long GPU sweep starts automatically; each block is started explicitly.

## Amendments

(none)

## Suite S — A7–A9 (protocol v3, `experiments/v3/`; design: docs/A7_A9_EXPERIMENT_DESIGN.md) — NOT STARTED

Phase 3 smokes ran 2026-11-21 (`experiments/v3/smoke/`, reports in `reports/v3/smoke/`); harness validation only.

| Block | File(s) | Seeds × arms | Runs | Est. time | Status |
|---|---|---|---|---|---|
| S0 A7-V A/A null (run first; sets noise floor) | `a7v_cache_isolation_validation` | 5 × 2 | 10 | ~21 min | ready |
| S1 A7 cache state (exploratory: no verified reset) | `a7_prefix_cache` | 5 × 2 | 10 | ~21 min | ready |
| S1' A7 with verified reset (confirmatory) | `a7_prefix_cache_reset` | 5 × 2 | 10 | ~21 min | ready: dev mode on since 2026-11-21 11:05 UTC; `reset_and_verify` passed (hits 96 → 0) |
| S2 A8a cancel/timeout churn | `a8_lifecycle_churn` | 5 × 2 | 10 | ~16 min | ready |
| S3 A8b bounded retry churn | `a8_retry_churn` | 5 × 2 | 10 | ~16 min | ready |
| S4 A9 token-matched families (4) | `a9_tok_{prefill,decode,longctx,prefix_reuse}` | 5 × 2 × 4 | 40 | ~83 min (+~17 min idle/tail waits) | ready: GPU power via exporter :9835 verified 2026-11-21 |
| S5 A9 rate-matched families (4) | `a9_rate_{prefill,decode,longctx,prefix_reuse}` | 5 × 2 × 4 | 40 | ~83 min (+~17 min) | ready |
| **Total (S0–S5, incl. S1')** | | | **130** | **~5.0 h** (with ~25 s idle-settle + tail wait per run) | |

Re-verified 2026-11-21 06:19 local (see design doc amendments): verified reset **works**, per-request
`cached_tokens` is **reported** (cold request = `null` = missing, not 0; the harness doesn't record it yet),
GPU power is still **unavailable** (no exporter on the host, and no SSH from the runner). The vLLM restart changed
`gpu_memory_utilization` to 0.80, so runs before and after 11:05:29 UTC are never pooled. To unblock S4/S5, run on
the GPU host `quotashift gpu-exporter --host 192.168.86.173` (or `nvidia-smi dmon -s pucvmet -d 1` logged to a file,
which is a weaker, non-time-aligned fallback) and set `gpu_exporter_url` in `configs/targets/selfhost.yaml`.

Time per run ≈ runtime + ~4 s overhead (measured: 20 s smoke arms took ~24 s). Disk: 96–152 KB per smoke run;
full runs (90–120 s) ≲ 0.6 MB each → < 75 MB for Suite S.

Command per file: `uv run quotashift experiment experiments/v3/<f>.yaml --reps 5 --live --path gateway
--out reports/v3/<scenario_id>`. The run stops (`exit 4`) on a cleanup/accounting leak (A8) or an unverifiable
pre-registered cache reset (S1'). Order: S0 → (check A7-V noise floor: CI half-width ≤ 0.25, else Suite S is
exploratory) → S1 → S2 → S3 → S4/S5 after the GPU exporter is running.

GPU power verified 2026-11-21 06:36–06:51 local: `gpu_exporter_url: http://192.168.86.173:9835/metrics`
(nvidia_gpu_exporter). Each run now waits for GPU idle clocks before the arm (about 3.5 s) and records the
post-arm power tail (about 22 s), which adds about 25 s per run. The idle-baseline defect and its fix are in the
design doc amendments.

### Step 0 implemented (2026-11-21 09:00–09:08 local)

- **Preflight, fail closed:** before each live arm, a bounded 30 s wait for `num_requests_running = waiting = 0`
  and `engine_sleep_state{awake} = 1`. If that fails, `EngineNotReady` stops the run (exit 4). The per-arm
  `process_start_time_seconds` must not change during an experiment; if it does, `ServerRestarted` (exit 4).
- **Prefill accounting:** `prefill_computed_tokens_measured` = Δ`prompt_tokens_by_source_total{local_compute}`,
  reported beside the pre-registered estimate (Δprompt − Δhits) with their difference. Live A7 smoke: 250 = 250.
- **Target snapshot:** every live `quotashift experiment` writes `<report>/target_snapshot/` (target check, `/version`,
  `/v1/models`, the `vllm:` and `process_start_time_seconds` lines, GPU `nvidia_smi_gpu_info`) and refuses to start
  if the target check fails.
- **Warm-cache re-run guard:** without a verified reset (`cache_reset: none`), the run is refused (exit 3) before
  anything is sent if a run with a byte-identical trace (same `trace_sha256`) already ran on the current server
  start. Fix: a new `isolation_salt` per replication. `--allow-warm-rerun` exists only for deliberate harness
  checks. **Found by:** the A7 smoke `reports/v3/smoke_step0/a7_prefix_cache_smoke` (14:02 UTC) repeated the
  13:45 UTC smoke on the same server start. Both arms hit 98.6% (warm cache), so it's **invalid** as an A7
  measurement and kept only as evidence. The guard only recognizes runs that recorded `process_start_time_seconds`
  (from 2026-11-21 09:00 local onward).
- **Suite S consequence:** each `experiments/v3/*.yaml` block runs once per server start with its current salt. A
  repeat (for example after a failure) needs a new `isolation_salt`, or a server restart, which starts a new series.
