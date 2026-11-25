# Known limitations — QuotaShift

## Measurement validity
- **Mock backend is not a GPU measurement.** `run-local --mock` uses an uncalibrated engine simulator; timings are
  plumbing evidence only (`synthetic_backend: true`). Cross-tenant interference claims require the real vLLM path
  (Phase 4), which needs owner approval.
- **Synthetic prompts are a token-trace, not semantic inference.** Prompts are seeded benign templates; the mock
  counts whitespace words as tokens. Realized output length on a real engine is decided by the model, not the trace.

## Scope this pass
- **Gateway TTFT.** The Phase 1 gateway forwards non-streaming and records usage from the response body, so it does
  not expose first-token latency; streaming passthrough with per-token accounting is deferred to the integration path.
  (Matched-budget enforcement — ADR-Q10 — and the Phase 5 analysis — ADR-Q11 — are now implemented.)

## Infrastructure
- **Not deployed.** Terraform is validated offline only (mock provider). AWS-side facts (AMI availability, quotas,
  instance offering in the AZ, IAM validity) are unverified until a real `plan`.
- **Deploy blockers (2026-11-18 preflight).** G/VT on-demand vCPU quota is 0 (g5.2xlarge needs 8); the account was
  observed using root access keys. Both must be resolved before any apply (see `docs/TERRAFORM_PROPOSAL.md`).
- **NAT standing cost.** The private-by-default `nat` mode bills a NAT gateway hourly for as long as the stack is
  applied, even with the GPU stopped. Destroy or switch to `endpoints` (with S3-staged weights) to avoid it.
- **vLLM service discovery.** The gateway's `vllm_backend_url` defaults to an internal name; wiring the host-network
  vLLM task into Cloud Map / resolving the GPU host's private address is finalized at deploy time.

## Self-hosted target
- **Cross-arm prefix-cache carry-over biases every self-hosted live ratio (found 2026-11-21, results unchanged).**
  Per-arm deltas of `vllm:prefix_cache_{hits,queries}_total` from the saved `metrics_timeseries.parquet` show the
  control arm — which runs immediately after the attack arm on the same server and replays identical victim (and,
  for A1/A5, identical competitor) prompts — hits the prefix cache far more than the attack arm:
  A1 attack 0.275 / control 0.944 (n=25 runs each); A2 0.000 / 0.070 (n=25); A3 0.000 / 0.314; A4 0.000 / 0.235;
  A5 0.021 / 0.981 (n=5). A warm control lowers control victim TTFT and so **inflates attack/control ratios**.
  A1 and A5 are most exposed; A2 least, but not clean. The pre-registered results are retained as measured; any
  claim from them must carry this caveat until a replication with prefix caching off (or cache reset + arm-order
  counterbalancing) is run. Scrape-window deltas slightly undercount traffic at arm edges.
- **Prefix caching is ON on the self-hosted target, contrary to the documented default.** Observed 2026-11-20 via
  `/metrics` (`vllm:cache_config_info enable_prefix_caching="True"`, block_size 16, gpu_memory_utilization 0.85);
  lifetime prefix-cache hits ≈ 17% of queried tokens (1.156M / 6.657M). `ARCHITECTURE.md`/`REPRODUCIBILITY.md`
  describe prefix caching off (that is the docker-compose/AWS config). It was identical across every attack and
  control arm, so per-seed ratios remain within-config comparisons, but templated prompts can share cached
  prefixes and reduce effective prefill — plausibly *understating* prefill-heavy effects. All self-hosted live
  results (A1–A5, both A2 sweeps) were measured with it on; a caching-off replication is not yet run.
- **Revision unpinned.** The self-hosted vLLM (`configs/targets/selfhost.yaml`) does not report its HF revision via
  `/v1/models`, so `model_revision` is `null` until the host's `--revision` is recorded. Its GPU type, vLLM version and
  flags are owner-managed and not captured by this repo; self-host and AWS results are not directly comparable.

## Reused code
- The scheduler `REGISTRY` (fcfs/static_quota) is retained as a fixed config; it is not a QuotaShift contribution and
  is not exercised as an experimental variable.

## Attack-effect analysis (Phase 5)
- **Mock results are plumbing only.** A `--mock` experiment exercises the gateway, matched-budget pairing and the
  analysis/reporting path; its latencies are simulator outputs (`synthetic_backend: true`) and must never be read as
  evidence of real cross-tenant interference. Only a live target (self-hosted or AWS) yields a measurement.
- **Small-sample statistics.** The default 5 repetitions give a bootstrap CI for exploration, not a significance
  claim. Increase repetitions based on observed variance before drawing conclusions; a wide CI around 1.0× is a
  negative result, reported as such.
- **Attack-success rate depends on the pre-registered threshold.** It is fixed per scenario before runs (ADR-Q08/Q11);
  the rate is only meaningful relative to that threshold and the chosen degradation metric.

## Consolidated gateway, protocol v2, telemetry (2026-11-21)
- **Historical results live only on local disk** (`results/`, `reports/` are git-ignored). One verified archive
  exists outside the repo (docs/HISTORICAL_ARCHIVE.md); no second-disk copy yet.
- **Nonces reduce, not eliminate, cache sharing.** Chat templates, shared system prompts, hash collisions or reusing
  an `isolation_salt` while the server cache is warm can still produce hits. Per-arm ratios are recorded; the
  live v2 smoke measured 0.000 in all 4 arms, which is one observation, not a guarantee.
- **v2 prompts differ from v1 bytes:** 4 nonce words replace 4 filler words; real prompt tokens are 3–5 fewer than
  v1 (Qwen2.5), identical across arms. v1 and v2 results are compared, never pooled.
- **Engine counters are engine-global.** Attribution holds only if nothing else uses the server; runs flag
  `unrelated_traffic_suspected` (busy at start, counter reset, or engine prompt/generation tokens exceeding the
  run's own by > max(64, 2%)). Scrape-window snapshots bracket each arm; in-flight work from a previous arm that
  is still draining would be flagged, not silently attributed.
- **GPU telemetry not yet live:** the runner host cannot SSH to the GPU hosts; `quotashift gpu-exporter` (or DCGM)
  must run on the GPU host. GPU type is owner-stated, not measured.
- **HTTP adapter:** RPM/TPM reject at arrival (no waiting for window space). Requests cancelled after reaching the
  backend keep their conservative TPM reservation (usage unknown) and are not charged to the hard-cap ledger. The
  `/metrics` page has per-tenant counters, queue depth and rejections by reason, but no latency histograms
  (per-request latencies are in recorder rows). Recorder rows grow with every request (sized for experiments,
  not long-lived service).
- **vLLM `/tokenize` estimator** adds one backend round trip per request (opt-in, `QUOTASHIFT_TOKEN_ESTIMATOR=vllm`);
  the default whitespace estimate is kept for historical comparability.
- **Direct path is in-process.** `--path direct` removes gateway ledger/limits/queue caps but requests still pass
  through the runner's in-process dispatch (no HTTP hop). HTTP-gateway overhead is measured with the FastAPI
  adapter separately.
- **Config hashes:** new optional config fields change `config_sha256` for *new* runs of old configs; historical
  manifests and schedule hashes are unaffected.
- **Mock prefix-cache counters** are emulated for testing; cache hits do not change mock latency.

## A7–A9 (protocol v3, 2026-11-21)
- **No verified cache reset on .173** (`/reset_prefix_cache` → 404): A7 start states are matched only by per-arm
  salting + counterbalanced order; residual cache residency from the previous arm is not equal → A7 is exploratory.
- **Per-tenant cache hits are not observable** (`prompt_tokens_details` is null on this server); hit ratios are
  engine-global per arm.
- **GPU energy unavailable** until power is sampled on the host; A9 primary endpoint reported `unavailable`.
  Board power includes idle/other processes and the (identical) victim work; 1 s sampling; idle baseline taken
  right before each arm.
- **Engine time sums overlap** across batched requests (request-seconds, not exclusive GPU time); engine-busy time
  has scrape resolution (0.25–0.5 s).
- **A8 attribution is bounded, not exact,** for arms with cancelled/timed-out requests (see design amendment).
  Engine-side abort timing is observable only at scrape resolution; client cancel latency is decision → stream
  closed (measured ~2 ms p95 in smokes).
- **A8b retry matching is planned, not realized:** planned retries whose original completes before its timeout do
  not fire (counted as `retries_not_needed`).
- **A9 token-matched controls change request count; rate-matched controls change tokens** — the two series are
  analysed separately and normalized per 1k authorized tokens; neither isolates a single factor.

### GPU power / energy (verified 2026-11-21)
- Board power comes from `nvidia-smi` via nvidia_gpu_exporter, sampled about every 0.6 s; it's engine-global (whole board,
  victims included). Energy is a trapezoid integral, so spikes shorter than the sampling interval are missed.
- The idle baseline depends on a clock-based idle criterion (SM ≤ 500 MHz) calibrated on the RTX 3090; a different
  GPU needs re-calibration. If the GPU doesn't settle within 90 s, dynamic energy is reported as unavailable.
- About 16–22 s of post-arm high-clock power (the "tail") falls outside the arm window. It's reported as a secondary
  metric (`gpu_dynamic_energy_with_tail_j`); the pre-registered primary metric excludes it. The tail series
  starts after the engine drain, so a gap of ≤ 0.1 s between the arm window and the tail isn't integrated.

### Per-request cached tokens (implemented 2026-11-21)
- Full coverage depends on the owner's local vLLM patch (both endpoints since 13:44:43 UTC 2026-11-21;
  docs/SELFHOST.md §7a). On stock 0.17.1, or on the earlier chat-only build, zero-hit requests report `null`,
  coverage drops below 1 and `hit_ratio_reported` is biased upward; always read it with `coverage`. Reinstalling
  or upgrading vLLM can silently drop the patch, so check coverage in every run summary. The engine-reconciled
  ratio is available only for arms with exact attribution (not A8 arms with cancellations).
- `nulls_implied_zero` is also true when there are no nulls at all (vacuously); read it with coverage.
- The target runs a **locally patched** vLLM 0.17.1, and `/version` can't tell it apart from stock. Provenance
  depends on the owner's patch note plus `process_start_time_seconds`, and the runner can't read the source on
  the host.
- Tenant identity is the gateway's own trace label, not anything vLLM reports. It's exact for harness runs, but the
  field can't attribute traffic from clients outside the harness.
- Only completed requests carry usage; cancelled or timed-out requests (A8) have no per-request cached-token value.

### Preflight / warm-cache guard (2026-11-21)
- The warm-cache re-run guard matches on the exact `trace_sha256` plus the server start. It doesn't detect
  *partial* prompt overlap with earlier runs (for example a different scenario that shares victim prefixes), and it
  ignores runs recorded before 2026-11-21 09:00 local, which didn't store `process_start_time_seconds`.
- The engine-idle preflight only sees vLLM's own counters. A non-vLLM GPU process is caught only indirectly, by
  the GPU idle-baseline check.
- `prompt_tokens_by_source_total` sources summed to 4 tokens more than `prompt_tokens_total` in one 18,250-token
  arm. This is reported, not reconciled away.

### Suite S audit findings (2026-11-21; reports/v3/SUITE_S_FORENSIC_AUDIT.md)
- **Planned token unit.** Every scenario before v3.1 plans `input_token_count` in whitespace words. Pseudo-syllable
  filler is ~2.03–2.14 Qwen2.5 tokens per word; the single-token prefix/nonce vocabulary is 1.0 (A7 competitor
  prompts 1.21 overall). "Authorized tokens" and token-matched budgets of v1–v3 are therefore in planned (word)
  units, not tokenizer tokens; realized tokens differ by family. The design-doc sentence "Tokenized lengths are
  verified equal across arms on the live tokenizer (single-token vocab)" holds for the nonce/prefix words only.
  Victim prompts are still identical across arms. v3.1 (`prompt_token_unit: tokenizer`) fixes this for new series.
- **A9 long context v3 is invalid** (112/116 competitor requests HTTP 400); kept as data, excluded from conclusions.
- **TTFT definition.** Pre-registered `ttft_p95` results (A1–A9) are backend TTFT and exclude gateway queueing
  (ADR-Q16). User-facing values are post-hoc.
- **Censoring.** Latency percentiles are over completed requests; gateway-queue timeouts (60 s) drop the slowest
  victims. Read every latency ratio with offered-load SLO success and the timeout counts.
- **A9 energy is nearly flat per arm** (≈27–37 kJ; ~300 W mean board power) at this load, so per-token ratios are
  dominated by their denominators; board power includes the (identical) victims' work.
- **Model revision.** The server reports `revision=None` (`/server_info`); the SHA in SELFHOST/REPRODUCIBILITY is
  the hub `main` SHA looked up on 2026-11-19, not verified against the loaded weights.
- **Run manifests** do not list dirty files; report manifests before 2026-11-21 21:00 have no `git` block.

### matched_total_short front-loads its budget (found 2026-11-21 during the v4 design review)
- `_matched_total_short_control` generates its short-request pool at 2x the rate needed for the matched token total
  and keeps the earliest requests until the total is reached, so the control's whole competitor budget arrives in the
  first ~50% of the window (last arrival ~28–30 s of 60 s in A2; ~56–65 s of 120 s in A9-tok and v3.1 long context).
  Historical token-matched comparisons (A2, A3, A9-tok) therefore change request granularity AND temporal concentration
  (2x offered rate) together; the control's gateway congestion and victim censoring (corrected analysis §2) are partly
  caused by this. Results stay as recorded; v4 uses `token_matched_fixed` (full-window arrivals) and an
  `arrival_coverage` gate. `rate_matched_short` (A9-rate) keeps the attack's own arrival times and is not affected.

### v4 R2 regime and limiting-resource classifiers under-report victim harm (found 2026-11-22, after the R2 runs)
- **Regime rule.** The pre-registered rule (`feasibility_gates: classify`) uses only competitor completion (≥ 0.95) and victim
  censoring (≤ 0.05).
  - Victims eventually complete inside the 60 s gateway queue timeout, so every R2 point was classed "feasible".
  - That includes R2-F s96, where the victim user-facing TTFT P95 was 25.8 s and offered-load SLO success was 0.06.
- **Limiting-resource rule.** `scripts/v4_analysis.py` labels a point "request-bound" only when gateway saturation is ≥ 0.50.
  - All R2-B points (saturation 0.17–0.33) were therefore labelled "unconstrained", despite gateway-queue P95 up to 3.4 s.
- **Status.** Both rules were frozen before the runs and are kept as registered. Report victim SLO success and gateway-queue
  time beside each classification. Any revised rule would be a new, separately pre-registered amendment.
- **Inference.** R2 uses 3 seeds per point and is descriptive only.

### Post-hoc findings from the v4 slot-time analysis (2026-11-22, exploratory)
- **Telemetry scrape lag.**
  - `metrics_timeseries` stamps each scrape about 0.15 s before the gateway in-flight count is read (vLLM and GPU
    metrics are fetched first).
  - Sampled `gw_inflight` matches the in-flight count rebuilt from request timestamps 66% of the time at lag 0, and
    91–99.5% with a +0.15 s shift.
  - **Correction (2026-11-23; the original 2026-11-22 statement above is kept as written):**
    - The "91–99.5%" range does not reproduce. Across the 114 v4 gateway runs, agreement at +0.15 s is 0.77–0.995,
      with per-stage medians of 0.89–0.96.
    - See the erratum in `reports/v4/posthoc_slot_time/SLOT_TIME_ANALYSIS.md`.
    - From v5 on, scrapes record `t_gw_rel_s`, the time of the gateway read itself, and the alignment is validated per
      arm (`gateway_timestamp_alignment`).
  - Use the rebuilt occupancy for slot analyses.
- **P95 threshold fragility.**
  - With about 100–115 victims per run, P95 sits at about the 6th-largest value.
  - The v4 R1 decode per-seed P95 ratios split into about 1.0–1.8 vs about 6.3, depending on whether ≥ about 7 victims
    happen to arrive during transient gateway-saturation episodes. Within-seed bootstrap ranges reach 439–3,080 ms.
  - The pre-registered result stands; magnitude statements should cite the mean ratio (1.80) and tail mass (6.2% vs
    0.5% of victims over 500 ms) alongside it.
- **A/A shares the trace.** v4 A/A arms (`identical_workload`) replay the same trace, so the A/A noise floor excludes
  variation between traces. For example, seed 44 is bursty in both arms.
- **Engine queue time not recorded in v4.** It is unavailable per request. vLLM exposes a
  `request_queue_time_seconds` histogram that v4 did not capture.
  *(Original 2026-11-22 entry, kept as written. Corrected by the next entry.)*
- **Engine queue time: engine-global only, never per request** (correction, 2026-11-23).
  - **What v4 captured:** per-arm sum/count deltas of vLLM `request_queue_time_seconds`. That gives the exact
    engine-global mean over finished requests: ≤ 0.012 ms in every R1/R3 arm (measured). It did not capture bucket
    deltas.
  - **What vLLM 0.17.1 measures:** time from QUEUED to the *first* SCHEDULED event in the engine core. It is observed
    only at request finish. Aborted requests are never observed. There are no tenant labels, and buckets start at
    0.3 s.
  - **What that rules out:** per-request or per-victim engine queueing, and any millisecond-scale P95.
  - Details: `docs/PROTOCOL_V5_DRAFT.md` §5.2.
- **FCFS counterfactuals assume cap-invariant hold times** (v4 post-hoc `fcfs_cap16/32_*`, v5 H3). They are biased low,
  and independent resampling of holds under-predicts tails: LOSO at C = 8 gives bias −2.2 ms and 90% PI coverage 0.57.
  v4 R3 direct runs are excluded from all predictions, because their non-binding cap makes them de-facto C ≥ 16 data.
  See `docs/PROTOCOL_V5_DRAFT.md` §3.4–§3.5.
- **Committed raw data in a public repo.** Commit `c11decc` published local usernames, a private LAN IP and GPU device
  identifiers in run metadata. No credentials were found. See `docs/RAW_DATA_AUDIT.md`.
- **In-process simulator ignored the concurrency cap (fixed 2026-11-23).**
  - Before this date, `runtime/sim.py` dispatched without `max_concurrency_cap`, so mock (`--mock`) gateway runs
    were effectively uncapped. The live runner (`runtime/live.py`), and so every GPU measurement, always applied it.
  - Historical mock outputs are plumbing evidence only and are not regenerated.
  - Found by the v5 `cap_configured` gate.
- **Simulator sampled before same-instant dispatches (fixed 2026-11-23).**
  - Virtual time makes samples coincide with arrivals. A sample taken before an instant's dispatch missed requests
    sent at that instant, so rebuilt-vs-sampled agreement was 0.49–0.61 on full-length mock runs.
  - Samples are now taken after dispatch, which gives exact agreement 1.0 on the mock. The live runner never had the
    tie.
  - Mock-only.
- **v5 raw output is not committed.** `results/v5_*/` and `reports/v5/{smoke,stage_a,stage_b,export}/` are
  git-ignored. Raw data is published only as sanitized, SHA-256-verified release tarballs
  (`scripts/export_v5_raw.py`). Rule 3 pseudonymizes GPU ids with a private salt, so third parties cannot link them
  to a physical device.
- **v5 host verification evidence levels (P1, 2026-11-24).**
  - **Model snapshot:** `a09a354…` is identified **by exclusion**, not observed directly. It is the only cached
    snapshot, it predates the server start, and its weight blobs are hash-intact. vLLM had closed the weight files,
    and the startup log names no path. A snapshot deleted after loading cannot be ruled out, but no deleted mapped
    file was seen.
  - **`max_num_seqs` = 256 is inferred** from the installed, hash-pinned vLLM 0.17.1 source defaults and the absence
    of overrides. It is not logged. An override outside the pinned files cannot be excluded.
  - **Unaffected:** `max_num_batched_tokens` = 2048, vLLM 0.17.1 and the server identity are directly evidenced.


### v5 final results (2026-11-24, after Stages A and B; `docs/RESULTS_V4_V5.md` §5, §7)
- **The FCFS prediction error direction is wrong in the saturated regime.**
  - Protocol v5 §3.5 and the C = 8 leave-one-seed-out validation expected under-prediction.
  - At L = 400, C = 8 the attack arm was over-predicted in 10/10 seeds, by 87–481 ms (5–11%; cell −7.1%).
  - The L = 400 controls and A/A arms were over-predicted by 0.5–3.2%.
  - All of these still passed the frozen tolerance, but they were extrapolated and are excluded from H3.
- **The threshold is not above noise at L = 400, C = 8.** The 18.1× D vs S classification there carries the
  preregistered flag: the A/A-ind per-seed ratios range 0.72–1.36 at that point.
- **No noise check is possible for the L = 400 direct cell.** The frozen design has no L = 400 direct A/A-ind cell.
- **Prefill has a small backend effect.** P vs S attack arms show 3–6 ms higher backend TTFT at every cap and on the
  direct path. It stays inside the H6 equivalence band, but it is not zero.
- **Output filename mismatch.** The frozen `v5_analysis.py` writes `analysis_<stage>.json`, while its docstring says
  `ANALYSIS_<stage>.json`. Left unchanged because the code is frozen.
- **Backups are on a single disk.** As of 2026-11-24 every copy of the v4/v5 raw data and the export salt sits on one
  disk. The off-machine checklist is in `docs/RESULTS_V4_V5.md` §8.

## X1 sampler on/off equivalence (2026-11-25)
- **Two failures on g0m0 (Qwen, gpu-node-2).** The anchor's Phase 1 failed the frozen rev 4 `sampler_equivalence` rule twice:
  - attempt 1 was confounded by a warm prefix cache;
  - attempt 2 was clean, at +1.23 ms.

  Both FAIL verdicts stand.
- **The rule is a coin flip on this host.** Its 20 + 20 point rule fails about 53% of the time with no sampler effect (offline simulation).
- **Proposed fix.** Amendment A1 (`docs/X1_AMENDMENT_A1_SAMPLER_EQUIVALENCE.md`, proposal) replaces it with a paired-segment equivalence test.
- **A1's known limits:**
  - it is post hoc;
  - it bounds the sampler's effect on idle TTFT only, not under load;
  - its sample size was sized on one G0 session's noise, so a noisier platform may fail for lack of power. That outcome must be reported as inconclusive, not as sampler perturbation.
- **Final outcome (closeout 2026-11-25, `docs/X1_CLOSEOUT.md`).** The single A1 run failed: +0.85 ms, 90% CI [+0.26, +1.44], δ 1.05 ms. g0m0 is not admissible, so X1 is closed at G0 preflight with **no confirmatory X1 results**.
- **What the failure means.** Equivalence was not established. There is no evidence that the effect exceeds δ.
- **Effect shape.** The ON-procedure shift is intermittent (5 of 24 pairs at +3–5 ms) and its cause is unidentified.
- **Follow-on.** Any cross-platform claim now requires the separate X2 protocol (draft).
