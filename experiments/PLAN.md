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

## Suite S — A7–A9 (protocol v3, `experiments/v3/`; design: docs/A7_A9_EXPERIMENT_DESIGN.md) — DONE 2026-11-21 (audited; corrected; long context re-run as v3.1)

Phase 3 smokes ran 2026-11-21 (`experiments/v3/smoke/`, reports in `reports/v3/smoke/`); harness validation only.

| Block | File(s) | Seeds × arms | Runs | Est. time | Status |
|---|---|---|---|---|---|
| S0 A7-V A/A null (run first; sets noise floor) | `a7v_cache_isolation_validation` | 5 × 2 | 10 | ~21 min (actual 25 min 10 s) | **done 09:37–10:02 local: passes precision gate** |
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

### Suite S outcome (2026-11-21, after audit and corrections)

- S1–S5 ran 15:18–20:15 EST. Forensic audit: `reports/v3/SUITE_S_FORENSIC_AUDIT.md`; corrected analysis:
  `reports/v3/SUITE_S_CORRECTED_ANALYSIS.md`; ADR-Q16/Q17: `docs/ADR_TTFT_METRIC_CORRECTION.md`.
- `a9_{tok,rate}_longctx` (v3) are **invalid** (competitor HTTP 400). Re-run as protocol v3.1
  (`docs/PROTOCOL_V3_1_LONGCTX_AMENDMENT.md`, `experiments/v3_1/`) 21:24–22:16 EST at 02448f8: rate-matched **valid,
  supported** (0.213 [0.185, 0.241]); token-matched **invalid** (pre-registered competitor-completion gate: the short
  control completed 74.6–76.0% of its requests in seeds 45–46).
- All other S blocks stand as pre-registered; see the corrected analysis for post-hoc TTFT/SLO/energy context.

### S0 result (2026-11-21 09:37:04–10:02:14 EST, server start 1795268683.89, code = commit dbd7f17)

- A/A victim TTFT P95 ratio over 5 paired seeds: mean 0.962, SD 0.055. Pre-registered percentile-bootstrap 95% CI
  [0.918, 1.006], **half-width 0.044 ≤ 0.25 → passes the precision gate**; classification negative (CI contains 1).
  Sensitivity check (not pre-registered): t-based CI [0.893, 1.031], half-width 0.069.
- All 10 arms: engine prefix hit ratio 0.000, per-request `cached_tokens` coverage 1.0, reconciliation residual 0,
  attribution exact, no restart, `prefill_est_minus_measured` 0, 1958/1958 requests completed, no leaks.
- One verified hygiene reset before the run (hits 96 → 0, `prerun_cache_reset.json`); no per-arm reset
  (`cache_reset: none` as pre-registered). No warm-cache contamination found.
- Remaining blocks S1–S5 run in plan order, each preceded by the same hygiene reset (not a per-arm reset).

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

## Protocol v4 (`experiments/v4/`; design: docs/PROTOCOL_V4.md) — ALL STAGES DONE (S, C, R1, R2-F, R2-B, R3)

R1 feasible token-matched comparison (calibrated common load), R2 request-granularity sweeps (R2-F fixed output,
R2-B balanced), R3 gateway vs direct-vLLM replay. 45 generated YAMLs (`scripts/build_v4.py`), frozen on the live
tokenizer (`experiments/v4/FROZEN_TRACES.json`, `scripts/freeze_v4.py`). Budget: 35 blocks / 178 arms ≈ 7.7 h GPU,
staged S (smokes) → C (calibration, selects L*) → R1 → R2-F → R2-B → R3; each stage needs owner approval.

**Stages S + C (2026-11-22, commit 46e37f6, clean tree, server start 1795268683.89 throughout; owner-approved).**
- Server, read-only (/version, /server_info, /metrics; no host shell): vLLM 0.17.1, fp16, max_model_len 4096,
  gpu_memory_utilization 0.8, prefix caching on, chunked prefill on, 4662 KV blocks. max_num_batched_tokens 2048 and
  max_num_seqs 256 are inferred from defaults-derived config fields, not verified. Model revision UNVERIFIED (revision=None).
- S (08:09–08:19 EST): 4/4 smokes passed all gates + telemetry/cache-isolation/conservation checks. R2-F s96 (gateway
  and direct) classified feasible, not the expected overload (expectation only, not a rule).
- C (08:20–09:08 EST): 9/9 probes passed integrity gates; 100% competitor completion, 0 victim censoring everywhere.
  Gateway saturation (limit 0.25): L200 P 0.011, D 0.092, S 0.035; L300 P 0.016, **D 0.367**, S 0.134; L400 P 0.006,
  **D 0.807**, **S 0.341**. Frozen rule ⇒ **L\* = 200**. No rerun, no threshold change. Engine waiting 0 and KV ≤ 4.8% in
  every probe: the 8-slot gateway is the binding constraint (D L300 victim user TTFT P95 ≈ 2.2 s, of which ≈ 2.1 s is gateway queue).
- Local reports (gitignored): reports/v4/{smoke,calibration}/, calibration/CALIBRATION_REPORT.md.
- Next, pending owner review: R1 at L200 (30 arms ≈ 80 min); remaining R1–R3 152 arms ≈ 6.7 h.

**Stage R1 at L\* = 200 (2026-11-22 09:40–10:56 EST, 76 min, commit 05ae0ed, clean tree, same server start; owner-approved).**
3 blocks x 5 seeds (42–46), 30 arms; all validity gates + telemetry/cache-isolation/conservation checks passed; competitor
completion 100%, victim censoring 0, prefix hit 0, engine waiting 0, KV <= 3.8%. Primary: victim user TTFT P95 ratio, two-sided 1.25x.
- A/A short: 0.956 [0.848, 1.038] — negative (noise floor; per seed 1.08, 1.02, 0.76, 0.98, 0.95).
- Prefill 1024/32 (23 req) vs token-matched short 64/64 (190 req): 1.047 [0.878, 1.216] — **negative**. Secondary: backend TTFT
  P95 1.14x, dynamic energy 0.88x (752 vs 853 J/1k realized tokens), engine service per authorized token 0.42x.
- Decode 64/256 (75 req) vs short (188 req): **4.36 [2.24, 6.34] — supported**, bimodal per seed (1.04, 6.33, 6.39, 6.28, 1.77).
  Entirely gateway queueing: user TTFT P95 801 vs 180 ms, gateway queue P95 697 vs 20 ms, backend TTFT P95 168 vs 166 ms
  (1.01x, negative); gateway saturation 0.110 vs 0.028; SLO success 0.987 vs 1.000. Energy 1.04x/realized token.
- Interpretation (pre-registered R3 rule applies): an admission effect of the 8-slot FCFS gateway (long-held decode slots), not
  demonstrated GPU interference. Local reports: reports/v4/r1/ (gitignored).
- Next, pending owner approval: R2-F (48 arms), R2-B (36), R3 direct (38) — 122 arms ≈ 5.4 h.

**Stages R2 + R3 (2026-11-22 15:00–20:10 EST, 5 h 10 min, commit 6c5615b, clean tree, same server start; owner-approved).**
19 blocks / 122 arms, all rc=0; all validity gates + telemetry/cache-isolation/conservation checks passed; competitor realized
tokens = authorized at every point; victim censoring 0 everywhere. R2 is 3 seeds per point: DESCRIPTIVE, not inferential.
- R2-F (output 32, 1000 tok/s), victim user TTFT P95 (gateway queue P95) / SLO success / gateway saturation:
  s96 25.8 s (25.6 s) / 0.06 / 0.96; s128 3.2 s (3.1 s) / 0.66 / 0.88; s192 1.15 s (1.03 s) / 0.99 / 0.46; s256 831 ms (728) / 0.99 / 0.21;
  s512 544 (330) / 1.00 / 0.10; s1024 526 (173) / 1.00 / 0.02; s2048 599 (111) / 1.00 / 0.02; s3584 770 (28) / 1.00 / 0.02.
  U-shape: small requests are request-bound at the gateway (frozen rule: s <= 128), large requests delay victims in the backend.
- R2-B (in = out = s/2, 400 tok/s): s64 681 ms (575) / 1.00; s128 952 (830) / 0.99; s256 1.51 s (1.41) / 0.97; s512 2.29 s (2.20) / 0.92;
  s1024 3.50 s (3.40) / 0.88; s2048 2.76 s (2.65) / 0.92; saturation 0.17–0.33. Longer outputs hold gateway slots longer.
- LIMITATION (frozen classifications kept): the R2 regime rule uses only competitor completion and victim censoring, so every point
  is "feasible" (incl. s96 at 6% victim SLO); the limiting-resource rule (saturation >= 0.5) labels all R2-B points "unconstrained"
  despite up to 3.4 s gateway-queue P95.
- R3 direct vLLM (same frozen traces, same server start; compares two execution paths with different admission and batching, not
  isolated gateway software overhead): R1 decode vs short 4.36 [2.24, 6.34] supported via gateway -> **0.996 [0.958, 1.026] negative**
  direct; R1 prefill 1.047 negative -> 1.151 [1.057, 1.254] inconclusive. R2-F attack arm victim TTFT P95 gateway -> direct: s96 25.8 s
  -> 227 ms; s256 831 -> 235 ms; s1024 526 -> 418 ms. Backend TTFT P95 rises 8–80 ms on the direct path (engine runs up to 25
  concurrent, never queues): a real but small GPU contribution. Main v4 finding: at this serving config, shape-dependent victim
  harm is dominated by gateway admission queueing, not GPU interference. Local reports: reports/v4/{r2,r3}/ (gitignored).

**Post-v4 (2026-11-22, offline, no GPU).**
- Post-hoc exploratory slot-time analysis and R1 decode statistical audit: `reports/v4/posthoc_slot_time/SLOT_TIME_ANALYSIS.md`
  (`scripts/v4_posthoc_slot_time.py`).
- Raw-data audit and storage proposal: `docs/RAW_DATA_AUDIT.md`.
- Protocol v5 (cap 8/16/32 × shape): FROZEN 2026-11-24 as `docs/PROTOCOL_V5.md` (rev 3; ADR-Q19 accepted; P1 accepted); no stage run or approved. P2 done (FROZEN_TRACES.json, Freeze Commit 2). Stage S (2026-11-23 20:57–21:07, 10.7 min): 4/4 smokes passed every gate (cap_configured, occupancy reconstruction 1.000, timestamp alignment lag 0.000 s with a measured scraper offset of 0.143–0.150 s, provenance clean, censoring 0, completion 1.000); smokes are never analysed. Stage A (2026-11-23 21:10 – 2026-11-24 07:09, 598.9 min): 12/12 blocks passed every gate, no flags, no reruns, one server start throughout. Next: sanitized Stage A export + `v5_analysis.py --stage A`; Stage B pending separate approval. Offline prep: `experiments/v5/` (23 generated YAMLs, `FROZEN_SCHEDULE.json`, frozen `FCFS_PREDICTIONS.json`). Run-level loader (`scripts/v5_analysis.py --stage A|B`, §9 item 8) done and mock-tested; items 9–11 done (gates, `run_v5.sh` stage driver, sanitized export); DRAFT rev 3 after owner review. Remaining before any GPU run: P1 host verification, freeze commit 1, P2 live trace freeze.
