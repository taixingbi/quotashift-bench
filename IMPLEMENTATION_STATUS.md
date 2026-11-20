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

## Phase 2 — synthetic scenarios (B0, A1–A5) 🟡
- ✅ Phase program + shapes (short/context_heavy/decode_heavy/mixed) and patterns (steady/burst_bounded).
- ✅ Matched-budget accounting + fail-closed gate (`quotashift budget`; `dry-run` reports it). Pre-registered
  `comparison.budget_tolerance`. Discrepancies (incl. requested vs realized) always reported. ADR-Q10.
- ✅ Two exactly-matched controls (zero delta by construction): `uniform_arrivals` (A1, `experiments/a1_burst_arrivals.yaml`)
  and `shuffled_phase_order` (A5, `experiments/stateful_sequences.yaml`); B0 benign-only reference (`baseline.yaml`).
- 🟡 Shape/mixture controls A2 (prefill-heavy) / A3 (decode-heavy) / A4 (mixed) via paired `control_scenario`
  YAMLs (token-matched within tolerance) are the next increment.

## Phase 3 — AWS Terraform ✅ (prepared; nothing deployed)
- ✅ `fmt`/`validate`/`test` (mock provider, 10 runs). Private `nat` default; one shared GPU vLLM (desired 0);
  gateway + generator Fargate (desired 0 / run-task); Cloud Map; S3/ECR/logs; cost-gate variables + check blocks.
- 🚫 Real `plan`/`apply`: owner-run and approval-gated. Known blockers in `docs/TERRAFORM_PROPOSAL.md`
  (G/VT vCPU quota = 0; account using root access keys).

## Phase 4 — controlled integration experiment ⬜ (needs approval)
## Phase 5 — attack-effect validation analysis ⬜ (victim degradation, pre-registered threshold, bootstrap CIs)
## Phase 6 — optional paper-strengthening ⬜

## Verification (this pass)
`uv run pytest -q` → 129 passed (1 gpu-only deselected); `ruff` + `mypy` clean;
`terraform fmt/validate/test` green. No AWS resources created.
