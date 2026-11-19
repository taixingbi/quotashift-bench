# CLAUDE.md — RISK-Sched (Paper A, MLSys)

Read `CLAUDE_CODE_MLSYS_MASTER_PLAN.md` first. Current position: see `PHASE_1_NEXT_STEPS.md` and
`docs/IMPLEMENTATION_STATUS.md`.

## Hard rules
- Never deploy, apply, start EC2/GPU, run billable load, or call Cost Explorer without explicit owner approval.
  `scripts/aws_ops.sh` gates these; do not bypass it.
- Never fabricate data or results. Mock-backend outputs (`synthetic_backend: true`) are plumbing evidence only.
- Online policies must never see `OracleInfo` / realized output length (ADR-004). Oracle policies set `deployable=False`.
- This is Paper A: no RL (PPO/GRPO) here. No employer code, traces or architecture details.
- Claim boundary: gateway admission/dispatch ≠ token-step scheduling (ADR-001).

## Commands
- `uv sync`; `uv run pytest -q`; `uv run ruff check src tests scripts`
- `make smoke smoke-http e0-mock` (zero cost); `make tf-fmt tf-validate tf-test` (offline)
- CLI: `uv run python -m risksched.cli {doctor,validate-env,generate-workload,run,profile,report,compare,mock-server}`

## Conventions
- New schedulers: subclass `risksched.schedulers.base.SchedulerPolicy`, register in `schedulers/simple.py:REGISTRY`
  (or a new module), add invariant tests (accounting, isolation, leakage).
- Every design deviation → `docs/DECISIONS.md`; every limitation → `docs/KNOWN_LIMITATIONS.md`.
- Figures only via `risksched.evaluation.plots` from saved results.
