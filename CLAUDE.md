# CLAUDE.md — QuotaShift

Read `QUOTASHIFT_CLAUDE_CODE_PLAN.md` first. Current position: `IMPLEMENTATION_STATUS.md`.

QuotaShift is an **attack-side, reproducible cross-tenant resource-interference benchmark** for LLM serving,
run in an owned, isolated AWS account/VPC. It characterizes whether different temporal and request-shape
distributions cause different victim-tenant degradation *under identical, authorized request/token budgets*.
It is not a scheduler and not a defense.

## Hard rules
- Never run `terraform apply`, start EC2/GPU, incur cloud charges, or call Cost Explorer without explicit owner
  approval. `scripts/aws_ops.sh` gates these (`QUOTASHIFT_APPROVED=<action>` + interactive yes); do not bypass it.
  `terraform fmt/validate/test`, `pytest`, static checks and a read-only `plan` are allowed.
- Never fabricate data or results. Mock-backend outputs (`synthetic_backend: true`) are plumbing evidence only,
  never GPU measurements. Do not invent AWS prices, AMI IDs, model revisions, or image digests — look them up.
- **Attack-side characterization only**: no defenses, no RL, no scheduler contribution. The experimental variable
  is the *workload scenario*; the serving config (gateway quotas, vLLM flags) is fixed and identical across a
  scenario and its control.
- **Private, owned targets only**: endpoints must be private (loopback/RFC1918/`*.quotashift.internal`). No external
  URLs, no third-party APIs, no production tenants. The scenario schema and gateway forwarder both enforce this.
- Tenants and prompts are synthetic. No malicious prompt content; prompts are deterministic benign templates.
- Pre-register the degradation threshold before runs; never choose it after seeing results. Report negative results.

## Commands
- `uv sync`; `uv run pytest -q`; `uv run ruff check src tests scripts`; `uv run mypy src/quotashift`
- `make validate dry-run run-local summarize` (zero cost, local mock)
- `make tf-fmt tf-validate tf-test` (offline, mock AWS provider)
- CLI: `uv run quotashift {doctor,validate,dry-run,run-local,summarize,mock-server}`

## Conventions
- New scenarios: write a YAML under `experiments/` validated by `quotashift.scenario.ScenarioConfig`
  (`extra=forbid`, fail-closed safety block). Add schema/replay/budget tests.
- Reused serving/gateway/metrics core lives under `src/quotashift/`; the scheduler `REGISTRY` is kept only as a
  fixed FCFS gateway config, not a studied variable.
- Every design decision → `docs/DECISIONS.md`; every limitation → `docs/KNOWN_LIMITATIONS.md`.
- AWS cost controls → `docs/aws_cost_controls.md`; infra state → `docs/TERRAFORM_PROPOSAL.md`.
