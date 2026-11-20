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
