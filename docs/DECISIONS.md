# Decisions (ADRs) — QuotaShift

RISK-Sched ADRs are archived in `docs/archive/risksched/DECISIONS.md`. This log starts fresh for QuotaShift.

## ADR-Q01 — Attack-side characterization only; no scheduler, no defense
QuotaShift measures whether workload *shape/timing* causes cross-tenant degradation under matched budgets. It
deliberately introduces no scheduler or defense (that would be a different paper). The reused RISK-Sched scheduler
`REGISTRY` is retained only as a fixed FCFS gateway config, not a studied variable.

## ADR-Q02 — Scenario is the experimental unit; it compiles to the existing trace machinery
`ScenarioConfig` carries victim/competitor roles, a fixed `safety` budget block, a `comparison` contract, and a
phase program. It compiles to the existing seeded `WorkloadConfig`/`generate_trace`, so the planned schedule and
its SHA-256 (`trace_hash`) are reused unchanged. The hash covers only planned fields, so wall-clock never affects it.

## ADR-Q03 — Private endpoints only, enforced twice
Scenario endpoints and the gateway forwarder both reject anything that is not loopback / RFC1918 / link-local /
`*.quotashift.internal` / `*.internal` / `*.local`, with no DNS resolution at validation time. External URLs, public
IPs, and body-level URL overrides are refused. `allow_external_target` and `require_private_endpoint=false` are not
expressible (pydantic `Literal`).

## ADR-Q04 — Fixed, fail-closed budgets for experimental equivalence
A scenario and its control run under identical caps (requests per tenant / total, per-request input/output tokens,
global in-flight, run deadline). The gateway refuses to start if a cap is missing and marks the run aborted when a
hard cap is hit. This is equivalence enforcement, not a defense.

## ADR-Q05 — Token ledger isolation (no borrowing) for the gateway
The gateway reserves `input + requested max_output` tokens per in-flight request against a fixed per-tenant quota
with `allow_borrow=False`, so one tenant can never consume another's in-flight budget. Reservation ≠ realized usage;
realized usage is charged separately from the backend `usage` field.

## ADR-Q06 — Private-by-default network (nat); public_egress_only demoted
Terraform defaults to `nat` (private subnets, no public IP on the GPU host or gateway). NAT's standing hourly cost
is the accepted price of no public addresses; it is documented in `docs/aws_cost_controls.md`. `public_egress_only`
remains available but trips an advisory `check`.

## ADR-Q07 — Model/revisions/digests are resolved, never invented
vLLM model `Qwen/Qwen2.5-7B-Instruct` @ `a09a35458c702b33eeacc393d103063234e8bc28` (HF API, 2026-11-19);
container base `python:3.12-slim-bookworm@sha256:935c3c5b...` (Docker Hub index, 2026-11-19). Prices are
user-supplied (`scripts/estimate_cost.py` refuses blanks).

## ADR-Q08 — Pre-registered degradation threshold; negative results reported
`comparison.preregistered_threshold` (victim-slowdown ratio) is fixed in the scenario file before runs. Attack
success is the fraction of repeated runs crossing it. If effects vanish under matched budgets, that is reported as
a negative result, not implied to be an attack.

## ADR-Q09 — Backend target toggle (aws | selfhost)
Where the fixed serving config runs is a *target profile* (`configs/targets/<name>.yaml`: private `backend_url`,
`model`, `model_revision`, `max_model_len`), selected by `configs/targets/active.yaml` or `QUOTASHIFT_TARGET`
(`quotashift target use <name>`). Both profiles serve `Qwen/Qwen2.5-7B-Instruct` at `max_model_len=4096`. The target
is not an experimental variable: a scenario and its control must run on the same target, and results from different
targets are not pooled. `run-local --live` sends to self-hosted targets only; AWS runs stay behind
`scripts/aws_ops.sh`. Selecting a target never starts cloud resources. The gateway falls back to the active target
when `QUOTASHIFT_BACKEND_URL`/`QUOTASHIFT_MODEL` are unset; the private-endpoint check applies to profiles too.

## ADR-Q10 — Matched-budget gate and exactly-matched controls (Phase 2)
Each attack scenario declares a `comparison.primary_control` and a pre-registered `budget_tolerance`
(default 0.05, fixed before runs like the threshold in ADR-Q08). `quotashift budget <scenario>` is a
fail-closed gate: it compiles the attack and control traces and refuses (exit 2) if a dimension the
comparison marks matched (request count and/or input+requested-output tokens) differs by more than the
tolerance. `dry-run` reports the same comparison without failing. Discrepancies — including the
unmatched dimensions and realized vs requested output — are always reported, never hidden.
All controls are generated in-process from the attack scenario (no sibling YAMLs) and hold on every seed,
so a matched pair can be replayed across repetitions without re-tuning. The matched token budget is the
*total* (prefill + requested decode); A2/A3 deliberately trade input length for request count while
holding that total, so their request-count delta is reported, not gated.
- `shuffled_phase_order` (A5): attack trace with phases reversed — exact on all dimensions.
- `uniform_arrivals` (A1): competitor arrivals re-spaced evenly; bodies and count unchanged — exact.
- `matched_total_short` (A2/A3): the competitor total-token budget re-expressed as fixed short requests,
  selected by cumulative tokens — total matched within one request per tenant (measured <0.4%); count free.
- `homogeneous_mixture` (A4): each competitor request replaced by a fixed mean-sized request at the same
  arrival time — request count identical, total matched to rounding (measured <0.1%).
Victim traffic is identical in attack and control for every control. Budgets compared are
planned/requested quantities; realized output is reported but never used to decide a match. `control_scenario`
remains only for an explicit B0 benign-only reference file.

## ADR-Q11 — Attack-effect analysis is paired, pre-registered and reports negatives (Phase 5)
`quotashift experiment <scenario> --reps N` runs the attack and its in-process matched control over seeds
`seed..seed+N-1` under an identical serving config (only the schedule differs), then analyzes the pair.
Victim degradation is the ratio of the victim's pre-registered metric (`ttft_p95` or `e2e_p95`) in the
attack over the control, computed **per matched seed** so each ratio holds the schedule's random draw fixed
between arms; completed and timed-out victim requests are separated, and the warm-up window is excluded.
Attack success is the fraction of seeds whose ratio crosses `comparison.preregistered_threshold` (ADR-Q08);
the effect is also reported budget-normalized (slowdown per measured competing tokens and per competing
requests), with a percentile bootstrap CI over the per-seed ratios. Outputs: `summary.csv`, `summary.md`
(with an explicit verdict, negative results included), `figure_victim_latency.png`,
`figure_degradation_ratio.png`, and `manifest.json` (per-seed matched-budget report, run dirs, hashes,
commands). Mock runs are labelled `synthetic_backend: true` and stated to be plumbing evidence, never a GPU
measurement. The analysis has no optimization objective and no scheduler contribution.

## ADR-Q12 — Rate-matched A2 sweep isolates prefill length (Phase 6; pre-registered 2026-11-20, before any run)
The budget-fixed A2 sweep (`a2_sweep_in*`) holds competitor total tokens fixed, which couples input length L
to request rate. The companion rate-matched sweep (`experiments/a2_rate_in{128,256,512,768}.yaml`; L=1024 is
`a2_prefill_heavy.yaml`) holds the competitor arrival process fixed — steady Poisson at 0.6 rps, identical
arrival times per seed (test-enforced) — and varies only L, so competitor total tokens scale with L by
construction. Serving config, victim traffic, caps and seeds (42–46, n=5/point) are unchanged.
Pre-registered before running:
- **Primary (per point, unchanged):** victim `ttft_p95` attack ÷ in-process `matched_total_short` control,
  threshold 1.5×, success rate and bootstrap CI as in ADR-Q11.
- **Secondary (cross-point mechanism test):** attack-arm victim `ttft_p95` (per-seed median across seeds)
  increases monotonically in L over {128, 256, 512, 768, 1024}; reported with Spearman ρ over the 25 per-seed
  values. A flat or non-monotone curve is a negative result for the "prefill length" mechanism and is reported.
- The per-point ratio's control also grows with L (same total re-expressed as more short requests), so the
  ratio across points is **not** the mechanism test; the absolute attack-arm curve at fixed rate is.
- Prefix caching is enabled on the self-hosted target (see KNOWN_LIMITATIONS); it is held fixed and not
  varied. vLLM `prefix_cache_{queries,hits}_total` are snapshotted before/after each arm where possible.

## ADR-Q13 — Protocol v2: prefix-cache isolation as a separately versioned series (2026-11-21)
Motivation: per-arm deltas of `vllm:prefix_cache_{hits,queries}_total` in the historical runs showed the
control arm (always run second, replaying byte-identical victim prompts) hit the cache far more than the attack
arm (A1 0.28/0.94, A2 0.00/0.07, A3 0.00/0.31, A4 0.00/0.24, A5 0.02/0.98), biasing ratios upward.
v1 (default) is unchanged: historical A1–A5 files, schedule hashes (test-pinned) and results stay as they are.
v2 (`protocol_version: 2`, new scenario ids under `experiments/v2/`, `experiments/eseries/`):
1. **Per-arm salted-hash nonce** (`workload/isolation.py`): 4 words from one shared 174-word vocabulary
   replace the first 4 filler words of every prompt in both arms; word 0 is offset by |V|/2 between arms so the
   first token always differs; `isolation_salt` varies replications. Planned `input_token_count` and word count
   are unchanged, so matched-budget reports are identical before/after (test-enforced). On the live Qwen2.5
   tokenizer all 174 words are single tokens; victim prompt tokens are equal across arms (measured diff 0 on
   48 victim requests); v2 prompts are 3–5 real tokens shorter than v1 (4 pseudo-words -> 4 single-token words).
2. **Counterbalanced order**: odd paired seeds run the control first.
3. **Per-arm counter snapshots** before/after each arm; hit ratio, reset and unrelated-traffic checks
   (`instrumentation/engine_counters.py`) are written to every run and to the experiment report.
4. **Caching on/off**: `expect_prefix_caching` (on|off|any) is checked against `vllm:cache_config_info`
   before running and fails closed; `_v2_nocache` variants exist for the caching-disabled block.
Nonces do not guarantee zero hits; observed per-arm ratios must be checked (live v2 smoke: 0.000 in all 4 arms).

## ADR-Q14 — One gateway engine, two adapters; `multitenant/` prototype retired (2026-11-21)
`core.Gateway` is the single admission/queue engine. The live in-process runner (A1–A5, E-series) and the
FastAPI adapter (`gateway/app.py`, now built on `core.Gateway`) share identity, the token ledger, RPM/TPM windows
(`gateway/quotas.py`), queue caps, reconciliation/refund and cleanup. All new controls default off, so historical
runs and the Phase 1 adapter defaults (FCFS order, no rate limits, no queue timeout, whitespace estimate) are
unchanged. Migration of the `multitenant/` prototype (archived byte-identical in docs/HISTORICAL_ARCHIVE.md):
- `quotas.py` RollingWindow/RateLimiter -> `gateway/quotas.py` (code identical) + `RateLimits` config.
- `auth.py` hashed keys -> `gateway/identity.py` (`tenants:` with `key_sha256`/`key_env`; legacy `keys:` kept).
- `tenant_queue.py` per-tenant queues/capacity/timeout -> `core.Gateway` queues + `max_queue_per_tenant/total`,
  per-waiter queue timeout in the adapter.
- `config.py` private-backend + per-tenant limits -> existing `endpoint_is_private`, `Caps`, `RateLimits`.
  Per-tenant `max_tokens` caps/defaults and per-tenant SLO fields: NOT migrated (global caps suffice; SLOs live
  in scenarios).
- `admission.py` FCFS/static -> existing `fcfs`/`static_quota` policies. Weighted-fair (WFQ): intentionally
  NOT migrated — new scheduling policies are out of scope (ADR-Q01); admission is fixed per attack/control pair.
- `metrics.py` prometheus_client histograms: NOT migrated; `/metrics` keeps the plain-text per-tenant
  counters (+ queue depth, rejections by reason); per-request latencies come from recorder rows.

## ADR-Q15 — Protocol v3 for A7–A9 (2026-11-21)
A7 (prefix-cache state), A8 (request lifecycle churn) and A9 (token budget vs GPU cost) are a separate series
(`protocol_version: 3`, `experiments/v3/`), designed and pre-registered in docs/A7_A9_EXPERIMENT_DESIGN.md before
any run. v3 adds reuse-preserving arm-salted prefixes (`workload/prefix_cache.py`), deterministic bounded lifecycle
plans kept beside the trace so the Request schema and historical hashes are unchanged (`workload/lifecycle.py`;
client cancel = closing the stream, client timeout, ≤ 2 retries, global retry budget), an optional verified cache
reset (`instrumentation/cache_reset.py`, fail closed), direction-aware pre-registered endpoints with CI-based
classification (supported / negative / inconclusive / unavailable), per-arm cost accounting (prefill-computed tokens,
engine time sums, busy time, KV/waiting, GPU dynamic energy when power is sampled), and stop-on-leak cleanup gates.
Thresholds (1.25×) are justified per scenario, not inherited from A1–A5. Lifecycle plans refuse the in-process
simulator (it cannot cancel streams). No defense, scheduling change or public target is involved.

## ADR-Q16 — TTFT definitions and metric-labelled reports (2026-11-21)
User-facing TTFT = `t_first_token − t_offered`; backend TTFT = `t_first_token − t_sent`; gateway queue =
`t_sent − t_offered`; offered-load SLO success = victims meeting SLO / victims offered. The historical key
`ttft_p95` keeps its computed meaning (backend TTFT) so A1–A9 results reproduce unchanged; user-facing reanalysis
is a labelled post-hoc correction. Reports derive every label/unit from `MetricInfo` and fail closed on mismatch.
Full record: `docs/ADR_TTFT_METRIC_CORRECTION.md`.

## ADR-Q17 — Fail-closed validity gates and tokenizer-sized prompts (2026-11-21)
`evaluation/validity.py` gates (HTTP 400/backend errors ≤ 1%, admission and competitor completion ≥ 95%, primary
metric present, tokenized context fits, planned = reported tokens for tokenizer-unit scenarios, clean provenance,
victim censoring ≤ 5% for latency primaries) set the classification to `invalid` and exit 5. Protocol v3.1
(`docs/PROTOCOL_V3_1_LONGCTX_AMENDMENT.md`) sizes prompts in real tokens (`prompt_token_unit: tokenizer`) and
tokenizes every request on the live server before sending anything. Thresholds fixed before any v3.1 run.

## ADR-Q18 — Protocol v4: feasibility-calibrated, real-token, full-window comparisons (2026-11-21, pre-registration draft)
v4 (`docs/PROTOCOL_V4.md`) studies request granularity, token accounting, GPU compute and gateway concurrency:
R1 token-matched P/D vs short at a calibrated common feasible load (selection rule fixed before calibration), R2
fixed-budget granularity sweeps (feasible vs overload reported separately), R3 gateway vs direct-vLLM replay.
New mechanisms: fixed-size exact-count phases with arrivals iid uniform over the window; the `token_matched_fixed`
control (budget spread over the WHOLE window — the historical `matched_total_short` front-loads it, see
KNOWN_LIMITATIONS); `ignore_eos` (realized = authorized); frozen trace manifest enforced before sending;
`arrival_coverage` and `realized_output_equals_authorized` gates; `feasibility_gates: classify` for sweeps. Historical
A1–A9 results and controls are unchanged. No v4 GPU run is made before owner approval of each stage.

## ADR-Q19 — ACCEPTED (2026-11-24, Freeze Commit 1): gateway concurrency cap as a pre-registered blocking factor (Protocol v5; proposed 2026-11-22)
- **Context.** v4 R3 showed that the R1 decode effect is admission queueing at the 8-slot FCFS gateway. The post-hoc
  slot-time analysis (`reports/v4/posthoc_slot_time/`, exploratory) supports a slot-occupancy mechanism.
- **Proposal.** v5 (`docs/PROTOCOL_V5_DRAFT.md`) varies the gateway cap C ∈ {8, 16, 32} **between blocks**, keeping it
  identical within each block's attack/control pair, with a direct-vLLM reference.
- **Rule this relaxes.** It interprets the CLAUDE.md rule "the serving config is fixed and identical across a scenario
  and its control" as holding *within* each comparison pair. It makes a serving parameter a characterization factor:
  not tuned and not a defense. **This needs explicit owner approval**, because the workload is no longer the only
  varied quantity across the study.
- **Other changes.**
  - The primary endpoint changes from P95 to mean user-facing TTFT, motivated by v4's P95 threshold fragility.
  - Execution and victim-SLO feasibility are separate criteria.
  - A/A arms use independent traces.
  - Engine queue histograms are captured.
- **Rev 2 (2026-11-23; still PROPOSED, not approved for GPU execution).**
  - H2 is split into H2a (cap dose-response; per-seed slope, t-test plus exact sign-flip) and H2b (equivalence at
    C = 32 by TOST; disclosed as a replication of the R3 direct observation, not a blind prediction).
  - Quantitative FCFS predictions are frozen in `experiments/v5/FCFS_PREDICTIONS.json`. They use v4 C = 8 gateway
    inputs only, enforced by a leakage guard, with tolerances from LOSO at C = 8.
  - "Victim-SLO feasibility" is renamed **baseline** victim-SLO feasibility, which uses the control arm only.
    Attack-arm SLO degradation is an outcome.
  - H4's engine-queue criterion is reformulated to the verified semantics of the vLLM 0.17.1 histogram: an
    engine-global, finish-time mean, buckets of 0.3 s or more, aborted requests not observed.
  - Offline tooling and tests are added (`build_v5`, `freeze_v5`, `v5_fcfs_predictions`, `v5_analysis`).
  - Run-level loader added to `v5_analysis.py` (§9 item 8; 2026-11-23, before any v5 data). Its operational
    choices are listed in `PROTOCOL_V5_DRAFT.md` §9.1 for owner review. They cover: Holm with p = 1 for
    non-evaluable members; H4(b) operationalized as "lower at C = 32 than at C = 8, and H3 passing at C = 16 and 32";
    H5 saturation measured at each arm's own cap; and enforced no-interim-look refusal.
  - §9 item 9 gates added (2026-11-23):
    - `cap_configured` (fail) and `occupancy_reconstruction` (flag) run for protocol_version ≥ 5 only, so v4 gate
      sets are unchanged.
    - `server_identity` is a per-stage gate in the loader.
    - Scrapes add `t_gw_rel_s`.
    - The in-process simulator now applies `max_concurrency_cap`. This is a mock fidelity fix; GPU results are
      unaffected.
- **Rev 3 (2026-11-23; owner review of §9.1; still PROPOSED, not frozen, nothing run on a GPU).**
  - Fixed-family Holm, with p = 1 and an explicit "not evaluable" for non-evaluable members: **accepted**.
  - **H4(b) separated from H3.** The paired per-seed reduction d = q8 − q32 of the attack-arm victim mean gateway queue
    is reported with a 95% CI. It is SUPPORTED iff max(one-sided paired t p, exact sign-flip p) < 0.05. H3 prediction
    accuracy no longer enters it.
  - **Primary estimand** stated as the geometric mean of the per-seed ratios.
  - **H5** is described as an explanatory consistency test.
  - **Occupancy reconstruction** stays a flag. It gains a `gateway_timestamp_alignment` flag, a lag scan around the new
    `t_gw_rel_s`.
  - **Server identity** is checked before and after every block during execution, as well as at analysis.
  - **Original v4 statements** in KNOWN_LIMITATIONS are restored verbatim, with dated corrections beside them.
  - **Items 10 and 11** (`v5_stage.py`/`run_v5.sh`, `export_v5_raw.py`) are implemented.
  - **Reruns:** each block's single rerun is pre-generated (`experiments/v5/reruns/`).
  - **Raw output:** v5 raw output is git-ignored so that the provenance gate's clean-tree check can hold during a
    stage. Sanitized exports and manifests are committed instead.
  - **Mock fidelity:** the in-process simulator now samples after each instant's dispatches. Before, a sample at an
    arrival instant missed the request sent then.
- **Rev 3 approval (2026-11-23, owner).**
  - ADR-Q19 is **APPROVED in principle**: the gateway cap may vary across pre-registered blocks, and stays identical
    within each attack/control pair.
  - The H4(b) paired rule is **APPROVED**.
  - Before the freeze: the sign-symmetry assumption is documented (§6); the §3.3 table transcription is fixed (99.8 →
    99.7, JSON unchanged); a text/code/JSON consistency test is added; the export's fail-closed handling of unknown
    file types is tested; P1 read-only tooling is added (`p1_host_evidence.py`, `p1_verify_host.py`).
  - Freeze commit 1 waits for the P1 evidence.
- **P1 decisions (2026-11-23, owner).**
  - **Model snapshot:** `a09a35458c702b33eeacc393d103063234e8bc28` is accepted on exclusion evidence. The
    classification stays `verified_by_exclusion`, not `verified_direct`. No waiver is needed.
  - **`max_num_seqs`:** 256 is conditionally accepted as `inferred_from_source_default`, under a narrowly scoped,
    hash-pinned rule in `p1_verify_host.py` and the P1 gate. The CUDA-graph capture size is recorded as consistency
    only.
  - **Record:** `verified_by` = "project owner", the owner's choice.
  - **P1 passed** at 2026-11-24 01:11 UTC. Freeze commit 1 has not been created.
- **Accepted (2026-11-24).**
  - The owner formally accepted P1 (commit `0f1252d`) and ADR-Q19.
  - The gateway cap varies only between pre-registered blocks, and is identical within each attack/control pair.
  - At Freeze Commit 1, `docs/PROTOCOL_V5_DRAFT.md` was renamed `docs/PROTOCOL_V5.md` (status FROZEN). Earlier
    entries that cite the draft name are historical and kept as written.
  - The 46 generated YAMLs were regenerated so their header comment cites the new name. That is a one-line comment
    change per file; `FROZEN_SCHEDULE.json` reproduces exactly.
  - All frozen artifacts are pinned in `experiments/v5/FROZEN_SHA256.json`.
- **Unchanged.** v4 and its results.

## ADR-Q20 — Consolidated v4/v5 report: post-hoc conventions (2026-11-24, after every v5 stage finished)
- **Context.** After both v5 stages were accepted on review, the owner asked for a consolidated report
  (`docs/RESULTS_V4_V5.md`), figures, and a cross-platform validation design. No frozen code, threshold, prediction or
  seed changes.
- **Decisions.** Everything below is labelled **[post-hoc]** wherever it appears.
  - Tables and figures come from a new read-only script, `scripts/v5_consolidated.py`. It reads only frozen outputs and
    raw request logs.
  - **FCFS prediction-error split.** A (cell, arm) is a "zero-queue" case iff its frozen predicted cell mean is < 1 ms.
    Otherwise it is "nonzero", and only nonzero cases get relative errors.
  - **Error sign.** Error = observed − predicted, so positive means under-predicted.
  - **Offered slot demand** = Σ(t_terminal − t_sent) over all requests / (C × 120 s). It is descriptive only, and
    undefined on the direct path.
  - The H3 verdict stays as frozen. Extrapolated L = 400 scores are reported but never enter the verdict.
- **Proposed, not adopted.** `docs/PROTOCOL_X1_CROSS_PLATFORM_DRAFT.md` would promote the control-arm slot demand at
  C = 8 to a *preregistered* load-calibration variable for cross-platform work. That needs owner approval and a freeze
  of its own.

## ADR-X1-P0 — X1 planning decisions and P0 outcome (2026-11-24; owner decisions; P0 read-only)
- **Owner decisions.**
  - M1 = mistralai/Mistral-7B-Instruct-v0.3.
  - G1 = NVIDIA L4 24 GB (AWS g6 family).
  - Full 2 × 2 design, in separately approved stages.
  - n = 16 for X-a and X-d, n = 10 elsewhere, subject to joint power.
  - P vs S excluded from core X1 and kept as optional extension X1-E1.
  - Only P0 (read-only) approved. No provisioning, downloads, GPU runs or freeze.
- **P0 outcome** (`docs/X1_P0_REPORT.md`):
  - revision `c170c708…`, Apache-2.0, supported by vLLM 0.17.1;
  - fp16 fits on both GPUs;
  - L4 offered in all us-east-1 AZs; on-demand G/VT quota is 4 vCPU (enough for g6.xlarge only);
  - g6.xlarge $0.8048/h, g6.2xlarge $0.9776/h; AWS total ≈ $32–52.
- **Draft rev 2** (`docs/PROTOCOL_X1_CROSS_PLATFORM_DRAFT.md`):
  - one serving template on vLLM 0.17.1 for all platforms;
  - both models per GPU on one host;
  - X1-H5 pools from dedicated calibration seeds 7003–7007, frozen before the main stage;
  - staged approval plan X0–X1-O.
- **Open, owner to decide before freeze:**
  - power option (a) n = 24, (b) H1 null log 1, or (c) accept;
  - g6.xlarge vs g6.2xlarge;
  - fp16 vs bf16.
- **Security finding.** The workstation's AWS credentials are the root user. Replace them with a least-privilege identity before any AWS stage (stage X1-B).

## ADR-X1-G1 — G1 = AWS g6.xlarge; n = 24 on X-a/X-d with the 1.25 primary threshold (owner, 2026-11-24)
- **Decision.**
  - G1 = EC2 **g6.xlarge** in us-east-1 (4 vCPU, 16 GiB RAM, 1 × L4). This replaces the g6.2xlarge recommendation.
  - **No** 8-vCPU quota request.
  - Kept: full 2 × 2, fp16, the existing model revisions, n = 24 for X-a and X-d, the primary X1-H1 threshold of 1.25× (power option (a) only), the $60 cap and the cost controls.
- **Consequences** (draft rev 3):
  - CPU and RAM are treated as cross-platform confounders, with preflight checks for CPU utilisation, available RAM, model-load success, KV capacity and tokenization throughput;
  - per-arm `host_cpu_headroom` and `host_ram_headroom` flag gates;
  - G1 contrasts that carry a flag are reported as "GPU+host, host-limited".
- **Cost.** Recalculated AWS cost ≈ $36 planned, $51 pessimistic.
- **Not done:** no provisioning, Terraform apply, restart, download or GPU run.

## ADR-X1-R4 — X1 draft rev 4: two-phase preflight, observable load criteria, tokenization rationale; X1-B prepared (2026-11-24)
- **Owner review of rev 3.**
  - X1-A approved conditionally, for final revisions; X1-B preparation approved.
  - Kept: g6.xlarge, fp16, vLLM 0.17.1, n = 24 on X-a/X-d (n = 10 elsewhere), the 1.25× threshold, the optional 4-core diagnostic, and the power, cost and statistical rules.
- **Preflight ordering.**
  - Phase 1 runs before calibration: model load, KV capacity, idle RAM, isolated tokenization latency, idle TTFT floor, sampler on/off equivalence.
  - Phase 2 runs after calibration A and before calibration B, at the calibrated high rate: CPU and RAM under load, tokenization capacity.
- **Model loading.** Failure is judged on observable serving failure or identity mismatch only. WARNING lines are never relevant. ERROR/Traceback lines on a healthy server only flag for owner review.
- **Tokenization.** The rev 3 "p99 > 50 ms during a concurrency-8 burst" mixed per-request cost with queueing. It is replaced by:
  - isolated p99 ≤ 25 ms (flag > 2 × G0);
  - utilisation ρ = λ_peak × E[S] ≤ 0.10 (the 10× rule, justified by the M/G/1 wait ≤ 0.11 E[S]);
  - an open-loop burst at 10 × λ_peak that is sustained (≥ 95%), with p99 excess ≤ 10 ms (flag > 5 ms).
- **Preserved.** RAM ≥ 1 GiB, zero OOM kills, KV ≥ 20,480 tokens.
- **Sampler.** `scripts/x1_host_sampler.py` measured 0.046% of one core and 12.6 MiB on gpu-node-2 (60 s, read-only). The fail threshold is 1% of a core. A load check (sampler on/off idle TTFT) runs in Phase 1.
- **X1-B.**
  - `docs/X1_IAM_MIGRATION_CHECKLIST.md`, plus `infra/iam/*.json`: Access Analyzer reports 0 findings.
  - `aws_ops.sh` refuses root credentials for every action except `stop-gpu`.
  - No credential was created, deactivated or rotated.

## ADR-X1-A — X1 protocol rev 4 approved as final; X1-B roles created (2026-11-24)
- **X1-A.** The owner approved rev 4 as final with no content change. It is not frozen. Freeze Commit 1 (X1-G) needs separate approval, after `scripts/x1_analysis.py` and the X1 schedule generator are built and tested.
- **X1-B, Option B, on the owner's instruction.**
  - Claude created IAM roles `quotashift-x1-readonly` (4 h) and `quotashift-x1-operator` (1 h). Each has the validated inline policy (Access Analyzer: 0 findings) and a trust policy limited to IAM user `quotashift-x1-owner`, with MFA no older than 1 h.
  - **Security fix before creation.** A deny was added so the operator cannot modify, re-trust or pass any `quotashift-x1-*` role. This closes a self-escalation path in the rev 4 draft policy.
  - **Policy-simulator check:** 23 of 23 decisions as expected. These cover:
    - g6.xlarge only, us-east-1 only, project tag;
    - Cost Explorer, quota increases, spot and access keys denied;
    - no self-modification or admin-policy attach;
    - stack roles manageable.
  - **Not done.** The owner user, MFA, access key, local profiles and every root-key step (deactivate or delete) are left to the owner.
  - **Recorded identifiers.** No ARNs or account IDs are recorded here.

## ADR-X1-B-MFA — MFA requirement removed from the X1 roles (owner decision, 2026-11-24)
- **Change.** Owner instruction "rm mfa".
  - The trust policies of `quotashift-x1-readonly` and `quotashift-x1-operator`, live in AWS and in the template, no longer require MFA. They still allow `sts:AssumeRole` only from IAM user `quotashift-x1-owner`.
  - `infra/iam/x1-owner-user-policy.json` drops its MFA condition and its MFA-device statement.
  - Access Analyzer reports 0 findings for both.
- **Trade-off.** That user's access key alone now yields operator credentials. Kept as mitigations:
  - the operator guard rails (g6.xlarge, us-east-1, project tag, Cost Explorer / quota / spot / credential changes denied, no self-modification);
  - 1 h operator sessions;
  - the key's only permission is assuming the two roles.
- **Unchanged.** Root-account MFA, which is not part of this change, and the plan to retire the root access keys.
