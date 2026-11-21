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
