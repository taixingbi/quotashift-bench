# QuotaShift — Implementation Status

Legend: ✅ done · 🟡 partial · ⬜ not started · 🚫 blocked (needs approval/quota)

Snapshot of RISK-Sched preserved as commit `273a57c` (first commit on `main`).

## Phase 0 — scaffold + local mock ✅
- ✅ `ScenarioConfig` with strict schema, fail-closed safety block, private-endpoint allowlist.
- ✅ Deterministic, phase-aware schedule compilation reusing `workload.generator` (stable SHA-256).
- ✅ Mock vLLM: `/v1/chat/completions` (+ `/v1/completions`), streaming + non-streaming, `usage`.
- ✅ JSONL events + per-request rows + Parquet via the shared recorder/runner.
- ✅ CLI: `validate`, `dry-run`, `run-local --mock`, `summarize`, `doctor`, `mock-server`.
- ✅ `experiments/{smoke,baseline,stateful_sequences}.yaml`.
- ✅ Tests: schema, replay/determinism, end-to-end mock.

## Phase 1 — gateway + tenant accounting ✅
- ✅ FastAPI gateway: `/healthz`, `/v1/chat/completions`, `/metrics`.
- ✅ Synthetic-tenant bearer auth (unknown → 401); per-tenant attribution (no misattribution).
- ✅ Fixed hard caps (per-tenant/total requests, per-request input/output, global in-flight, run deadline),
  fail-closed; idempotent per-request records (replay → 409); token ledger isolation (no borrowing).
- ✅ Private-only egress forwarder; rejects external backends and body URL overrides.
- ✅ Tests: attribution, budgets, idempotency, egress.

## Backend target toggle ✅
- ✅ `configs/targets/{aws,selfhost}.yaml` + `active.yaml`; `quotashift target {list,show,use,check}`; `QUOTASHIFT_TARGET`.
- ✅ Active: `selfhost` (Qwen2.5-7B-Instruct @ 192.168.86.173:8000, max_model_len 4096; `target check` OK 2026-11-19).
- ✅ `run-local --live` (self-hosted only); gateway falls back to active target. See ADR-Q09.

## Phase 2 — synthetic scenarios (B0, A1–A5) ✅
- ✅ Phase program + shapes (short/context_heavy/decode_heavy/mixed) and patterns (steady/burst_bounded).
- ✅ Matched-budget accounting + fail-closed gate (`quotashift budget`; `dry-run` reports it). Pre-registered
  `comparison.budget_tolerance`; token budget gated on the *total* (prefill+decode). Discrepancies
  (incl. requested vs realized) always reported. ADR-Q10.
- ✅ Every attack has an in-process, seed-stable control (victim traffic identical):
  B0 benign-only (`baseline.yaml`); A1 `uniform_arrivals` (`a1_burst_arrivals.yaml`);
  A2 `matched_total_short` (`a2_prefill_heavy.yaml`); A3 `matched_total_short` (`a3_decode_heavy.yaml`);
  A4 `homogeneous_mixture` (`a4_mixed_shapes.yaml`); A5 `shuffled_phase_order` (`stateful_sequences.yaml`).
  Measured match: A1/A5 exact; A2/A3 total tokens <0.4%; A4 exact count, total <0.1% — all seeds.

## Phase 3 — AWS Terraform ✅ (prepared; nothing deployed)
- ✅ `fmt`/`validate`/`test` (mock provider, 10 runs). Private `nat` default; one shared GPU vLLM (desired 0);
  gateway + generator Fargate (desired 0 / run-task); Cloud Map; S3/ECR/logs; cost-gate variables + check blocks.
- 🚫 Real `plan`/`apply`: owner-run and approval-gated. Known blockers in `docs/TERRAFORM_PROPOSAL.md`
  (G/VT vCPU quota = 0; account using root access keys).

## Phase 4 — controlled integration experiment ⬜ (needs approval)
## Phase 5 — attack-effect validation analysis ✅ (pipeline; validated on local mock)
- ✅ `quotashift experiment <scenario> --reps N --mock|--live`: runs attack + matched control over seeds
  `seed..seed+N-1` (identical serving config), then analyzes. ADR-Q11.
- ✅ Per-matched-seed victim degradation ratio (`ttft_p95`/`e2e_p95`), completed vs timed-out separated,
  warm-up excluded; attack-success rate vs pre-registered threshold; budget-normalized slowdown; bootstrap CI.
- ✅ Emits `summary.csv`, `summary.md` (with verdict incl. negatives), `figure_*.png`, `manifest.json`
  (per-seed budget report, run dirs, commands). Mock output labelled `synthetic_backend: true`.
- ✅ First live run (self-hosted vLLM 0.17.1, Qwen2.5-7B-Instruct, 2026-11-20). A3–A5 at 5 seeds; A1/A2
  re-run at 20 seeds (42–61). Headline: A2 prefill-heavy 3.19× (CI [2.66, 3.75], 95% success); A1 burst 1.59×
  (CI [1.53, 1.65], 70%); A3/A4/A5 negative under matched budgets. All budgets matched on every seed; zero
  attack-arm timeouts. See `docs/RESULTS_selfhost.md`.
- ⬜ AWS measurements still blocked on quota. More A3–A5 reps held pending owner approval.

## Phase 6 — optional paper-strengthening 🟡
- ✅ A2 prefill-concentration dose-response (L=128/256/512/768/1024, fixed ~30k-token budget, 5 seeds/point,
  each point its own matched pair). Monotonic at the concentrated end (512→768→1024: 2.14→3.00→3.16×).
  Caveat: fixed budget couples L to request rate, so the low-L end mixes prefill length with queue pressure.
- 🟡 Rate-matched A2 sweep (`a2_rate_in{128,256,512,768}`, ADR-Q12): scenarios + tests + dry-runs done and
  pre-registered; live run pending owner approval (~50 min self-host GPU).
- ⬜ Second engine / vLLM version; second GPU type (AWS, blocked on quota).
- ✅ Temporal order with token composition and offered load held fixed: covered by A5 (negative, n=5).
- ⬜ Paper draft (`paper/` is empty).

## Phase 7 — consolidation, protocol v2, E-series prep (2026-11-21) ✅ (prepared; no full runs)
- ✅ Historical results/reports archived + verified outside the repo (docs/HISTORICAL_ARCHIVE.md); checksum test.
- ✅ One gateway engine (`core.Gateway`) for the live runner and the FastAPI adapter (ADR-Q14); `multitenant/`
  prototype migrated/documented and removed. Hashed keys, RPM/TPM (tenant + global) with reservation →
  actual-usage reconciliation and refunds, queue capacity/timeout, streaming passthrough, disconnect cleanup,
  retry/idempotency, optional vLLM-tokenizer input estimate. Defaults reproduce historical behaviour.
- ✅ Engine counter deltas per arm (resets, unrelated traffic, prefix-cache hit ratio); GPU telemetry via
  nvidia-smi / SSH prefix / DCGM / `quotashift gpu-exporter`; run manifests record path, policy, limits,
  backend identity, vLLM version, GPU type, cache config, actual counts.
- ✅ Workload: `constant`/`poisson` patterns, `long_context` shape, `rate_matched_short` control,
  controlled-dimension descriptors, `--path direct|gateway`, scenario-level gateway limits.
- ✅ Protocol v2 (ADR-Q13): per-arm salted nonce (budgets unchanged), counterbalanced arms, cache on/off
  pre-check. `experiments/v2/` (A2–A5 + rate sweep, cache on/off) and `experiments/eseries/` (E0–E6).
- ✅ Live harness smokes on .173 (2026-11-21): v2 paired smoke (2 seeds) — all 4 arms prefix-cache hit 0.000,
  engine tokens == client tokens, no unrelated traffic, 0 preemptions; HTTP gateway smoke — exact tokenizer
  estimate, RPM 429, streaming usage, disconnect cleanup. Harness validation only; no findings claimed.
- ⬜ Suite R (A2–A5 v2 replication, cache on/off) and E0–E6 runs — see `experiments/PLAN.md`; GPU exporter on host.

## Phase 8 — A7–A9 (protocol v3) ✅ designed + implemented + smoke-validated; full runs ⬜ (approval)
- ✅ Design/pre-registration: docs/A7_A9_EXPERIMENT_DESIGN.md (hypotheses, threat model, controls, endpoints,
  confounders, falsification; dated amendments). ADR-Q15.
- ✅ Prefix-structure, lifecycle plans/client, stream cancel, verified cache reset, cost accounting, CI
  classification, stop-on-leak. 19 configs in `experiments/v3/` (+ smokes); all pass the matched-budget gate.
- ✅ GPU smokes 2026-11-21 (2 paired seeds each, ~16 min GPU): A7-V hit 0.000/0.000; A7 hit 0.52–0.55 (shared) vs
  0.19–0.23 (unique), realized prompt tokens equal across arms; A8 no leaks, engine drain ≤ 0.05 s, retries 6/6
  bounded; A9 primary unavailable (no power), secondaries populated. Harness validation only — no findings.
- ⬜ Suite S full runs (120 runs, ~4.0 h) — experiments/PLAN.md; blocked items: verified reset (S1'), GPU power (A9 primary).

## Verification (this pass)
`uv run pytest -q` → see Phase 8 report; `ruff` + `mypy` clean;
`terraform fmt/validate/test` green. No AWS resources created.
