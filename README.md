# QuotaShift

**Attack-side, reproducible cross-tenant resource-interference benchmark for LLM serving.**

QuotaShift asks: under identical, authorized request/token budgets, can different temporal and request-shape
distributions produce significantly different *cross-tenant* service degradation on a shared LLM serving system?
It benchmarks only the **attack side** — workload synthesis, controlled replay, and characterization of
cross-tenant impact — in an owned, isolated AWS account/VPC. It introduces **no scheduler and no defense**.

Status: **live self-hosted A1–A5 results (protocol v1, archived); consolidated gateway + protocol v2 (prefix-cache
isolation) + E0–E6 prepared, not yet run** — see `IMPLEMENTATION_STATUS.md`, `experiments/PLAN.md`.
Terraform prepared for review, nothing deployed (no new AWS work).

- Plan: `QUOTASHIFT_CLAUDE_CODE_PLAN.md` · Status: `IMPLEMENTATION_STATUS.md`
- Architecture & boundaries: `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/THREAT_MODEL.md`
- Protocol / metrics: `docs/EXPERIMENT_PROTOCOL.md`, `docs/METRIC_DEFINITIONS.md`
- Reproduce / AWS: `docs/REPRODUCIBILITY.md`, `docs/TERRAFORM_PROPOSAL.md`, `docs/aws_cost_controls.md`

Self-hosted GPU target setup and pre-flight: [docs/SELFHOST.md](docs/SELFHOST.md).

## Quickstart (no AWS, no GPU)
```bash
uv sync
uv run pytest -q                                   # unit + mock integration
uv run quotashift validate experiments/smoke.yaml  # schema + private-endpoint + budget checks
uv run quotashift dry-run experiments/stateful_sequences.yaml   # planned schedule + stable SHA-256 (sends nothing)
uv run quotashift run-local experiments/smoke.yaml --mock       # in-process mock vLLM + gateway
uv run quotashift summarize --input results --output reports
```

## Offline infrastructure checks (mock AWS provider; no credentials)
```bash
make tf-fmt tf-validate tf-test
```

## Components
- `src/quotashift/scenario.py` — scenario spec (victim/competitor roles, fixed safety budgets, comparison
  contract, phase program) and deterministic, phase-aware schedule compilation (stable SHA-256).
- `src/quotashift/gateway/` — internal FastAPI gateway: synthetic-tenant auth, fixed per-tenant/total/in-flight/
  token caps (fail-closed), idempotent per-request accounting, per-tenant attribution, private-only egress.
- `src/quotashift/serving/` — mock vLLM (OpenAI `/v1/chat/completions` + `/v1/completions`, streaming + usage,
  emulated prefix-cache counters).
- `src/quotashift/workload/isolation.py` — protocol v2 per-arm nonce; `instrumentation/engine_counters.py` —
  per-arm engine deltas; `quotashift gpu-exporter` — GPU telemetry (run on the GPU host).
- Historical archive: `docs/HISTORICAL_ARCHIVE.md`. Experiment series: `experiments/` (v1, frozen),
  `experiments/v2/`, `experiments/eseries/`.
- `infra/terraform/` — private-by-default VPC, one shared GPU vLLM backend (desired 0), gateway + generator
  Fargate tasks, S3/ECR/logs, cost gates. Approval-gated via `scripts/aws_ops.sh`.

Mock runs are simulator plumbing (`synthetic_backend: true` in every manifest), never GPU measurements.
