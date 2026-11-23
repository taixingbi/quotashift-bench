# QuotaShift

**Attack-side, reproducible cross-tenant resource-interference benchmark for LLM serving.**

QuotaShift asks: under identical, authorized request/token budgets, can different temporal and request-shape
distributions produce significantly different *cross-tenant* service degradation on a shared LLM serving system?
It benchmarks only the **attack side** — workload synthesis, controlled replay, and characterization of
cross-tenant impact — in an owned, isolated AWS account/VPC. It introduces **no scheduler and no defense**.

Status: **Protocol v4 complete on the self-hosted GPU (2026-11-22)**: 4/4 smokes, 9/9 calibration probes,
frozen L\* = 200 authorized tok/s, then R1, R2 and R3 executed with every validity gate passing. Historical A1–A9 and
v3.1 results are preserved unchanged. See `IMPLEMENTATION_STATUS.md` and `experiments/PLAN.md`. Terraform is prepared
for review; nothing is deployed and no AWS work was done.

## Current findings (read before citing any historical number)

- **The historical A2 "3.19× prefill-heavy" headline is superseded.** It reproduces exactly as computed (pre-registered
  `ttft_p95` = backend TTFT, ADR-Q16), but the corrected analysis invalidates the comparison:
  - The token-matched short control could not execute its budget: 4,573 of 5,700 competitor requests completed.
  - Control victims waited about 58 s at the gateway (P95), 60% were censored, and offered-load SLO success was 1.4%.
  - On user-facing TTFT the ratio is 0.018, and the ADR-Q17 gates fail (competitor completion, censoring, provenance,
    tokenization).
  - The historical control also front-loads its budget into the first half of the window (`docs/KNOWN_LIMITATIONS.md`).
  - Treat 3.19× as a measurement of a congested, front-loaded control, not as a prefill effect. The original record in
    `docs/RESULTS_selfhost.md` is kept as measured. The post-hoc reanalysis is `scripts/reanalyze_suite.py`.
- **Protocol v4** (`docs/PROTOCOL_V4.md`, frozen; results in `experiments/PLAN.md`):
  - **R1, at L\* = 200.** Decode-heavy vs short is supported (4.36×). Prefill-heavy vs short is negative (1.05×).
    - R1 matches *real tokenizer* token budgets, but it intentionally varies request count and input/output composition:
      23 requests of 1024/32 or 75 of 64/256, against about 190 of 64/64.
    - It is therefore a comparison of request shape at equal authorized tokens, not of equal request counts.
  - **R3, gateway vs direct vLLM.** The decode effect disappears when the same frozen traces are sent directly to
    vLLM (0.996×).
    - R3 compares two execution paths with different admission and batching behaviour. Direct vLLM ran up to 25
      concurrent requests, against the gateway's 8 slots.
    - It does not isolate the gateway's software overhead. The gateway/direct difference is admission queueing plus a
      change in engine batching.
  - **R2, request-granularity sweeps.** Three seeds per point, so the results are descriptive only, not strong
    inferential evidence.
    - They show shape-dependent victim delay that is dominated by gateway queueing at this serving configuration.
    - The frozen regime classifier labelled every point "feasible", including points where victim SLO success was 6%.
  - **Main v4 finding.** Shape-dependent victim harm is dominated by gateway admission queueing, not GPU interference;
    a small backend contribution remains.

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
