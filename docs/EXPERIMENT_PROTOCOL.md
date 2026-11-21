# Experiment protocol — QuotaShift

## Principles
- **Matched budgets.** A scenario and its control run under identical `safety` caps and the same victim workload.
  The only thing that changes is the competing tenant's shape/timing (or phase order).
- **Pre-registration.** Fix `comparison.preregistered_threshold` (victim-slowdown ratio) and `repetitions` in the
  scenario file before running. Never choose the threshold after seeing results.
- **Determinism.** Each `(scenario, seed)` yields one planned schedule with a stable SHA-256; the schedule is
  written before execution and can be replayed. The shuffled-phase control is a deterministic permutation.
- **Honesty.** Record requested vs. measured tokens; separate successful from timed-out/errored requests; keep
  warm-up separate; report negative results.

## Local (zero cost) loop
```bash
uv run quotashift validate   experiments/<scenario>.yaml
uv run quotashift dry-run    experiments/<scenario>.yaml           # planned schedule + hash (and --control)
uv run quotashift run-local  experiments/<scenario>.yaml --mock    # mock engine, not a GPU measurement
uv run quotashift summarize  --input results --output reports
```

## Controlled integration loop (Phase 4; owner-approved only)
1. `scripts/check_prereqs.sh <env>` (read-only): identity, G/VT vCPU quota, g5.2xlarge offering, ECS GPU AMI.
2. `scripts/plan_infra.sh <env>` (read-only plan) → review.
3. Approve, then `scripts/deploy.sh <env>`; `scripts/aws_ops.sh start-gpu <env>` (billing starts).
4. Confirm the private vLLM endpoint is healthy with one small request.
5. Run `smoke.yaml` (2 victims + 1 competitor); confirm S3 records, task exit, per-tenant attribution.
6. Run one matched baseline/control pair at a fixed seed; report measured vs. requested tokens.
7. `scripts/aws_ops.sh stop-gpu <env>` (ungated; reduces cost) and/or `scripts/destroy.sh <env>`.

## Analysis (Phase 5)
- Victim median/P95 TTFT and E2E latency ratio vs. the benign-only reference (B0), success vs. timeout split.
- Attack success = fraction of repeated runs crossing the pre-registered threshold.
- Budget-normalized victim slowdown per measured competing tokens (request- and token-matched views).
- Bootstrap confidence intervals across seeds/runs; full per-run manifests and hashes.
- Lock model revision, vLLM version/flags, max context length, hardware, replica count, and benign arrival
  distribution across every compared run.

## Protocol v2 (ADR-Q13) and the E-series
- v2 scenarios (`protocol_version: 2`) live in `experiments/v2/` (A2–A5 replications, `_nocache` variants) and
  `experiments/eseries/` (E0–E6). v1 files are never edited.
- Before a v2 run: `quotashift budget <f>` (gate on the exact post-nonce traces) and `quotashift dry-run <f>`
  (also lists which dimensions the control holds fixed vs lets vary). `expect_prefix_caching` must match the server.
- Each arm records before/after engine counters; reports include per-arm prefix-cache hit ratio, arm order and
  `unrelated_traffic_suspected`. Arms with suspected unrelated traffic are reported and excluded from claims.
- Execution path: `--path gateway` (admission/quota/queueing) or `--path direct` (engine interference only).
- Full run plan, counts, timings and disk: `experiments/PLAN.md`.

## Protocol v3 (A7–A9)
Design and pre-registration: docs/A7_A9_EXPERIMENT_DESIGN.md; configs `experiments/v3/`; plan `experiments/PLAN.md`
§ Suite S. Lifecycle scenarios need an HTTP backend (`--live` or mock_http); `--mock` (in-process simulator) is
refused. A cleanup/accounting leak stops the experiment (exit 4) and is recorded as a defect.
