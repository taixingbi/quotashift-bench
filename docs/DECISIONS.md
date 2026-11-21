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
