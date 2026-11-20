# Known limitations — QuotaShift

## Measurement validity
- **Mock backend is not a GPU measurement.** `run-local --mock` uses an uncalibrated engine simulator; timings are
  plumbing evidence only (`synthetic_backend: true`). Cross-tenant interference claims require the real vLLM path
  (Phase 4), which needs owner approval.
- **Synthetic prompts are a token-trace, not semantic inference.** Prompts are seeded benign templates; the mock
  counts whitespace words as tokens. Realized output length on a real engine is decided by the model, not the trace.

## Scope this pass
- **Matched-budget enforcement is partial.** The phase program, shapes, and a deterministic shuffled-phase control
  exist, but strict request/token *budget matching* across a scenario and its control (A1–A4) is the next increment
  (Phase 2). Until then, treat dry-run budgets as planned means of the arrival process, not guarantees.
- **No analysis/statistics yet.** Victim-degradation ratios, bootstrap CIs, and the attack-success computation
  against the pre-registered threshold are Phase 5.
- **Gateway TTFT.** The Phase 1 gateway forwards non-streaming and records usage from the response body, so it does
  not expose first-token latency; streaming passthrough with per-token accounting is deferred to the integration path.

## Infrastructure
- **Not deployed.** Terraform is validated offline only (mock provider). AWS-side facts (AMI availability, quotas,
  instance offering in the AZ, IAM validity) are unverified until a real `plan`.
- **Deploy blockers (2026-11-18 preflight).** G/VT on-demand vCPU quota is 0 (g5.2xlarge needs 8); the account was
  observed using root access keys. Both must be resolved before any apply (see `docs/TERRAFORM_PROPOSAL.md`).
- **NAT standing cost.** The private-by-default `nat` mode bills a NAT gateway hourly for as long as the stack is
  applied, even with the GPU stopped. Destroy or switch to `endpoints` (with S3-staged weights) to avoid it.
- **vLLM service discovery.** The gateway's `vllm_backend_url` defaults to an internal name; wiring the host-network
  vLLM task into Cloud Map / resolving the GPU host's private address is finalized at deploy time.

## Self-hosted target
- **Revision unpinned.** The self-hosted vLLM (`configs/targets/selfhost.yaml`) does not report its HF revision via
  `/v1/models`, so `model_revision` is `null` until the host's `--revision` is recorded. Its GPU type, vLLM version and
  flags are owner-managed and not captured by this repo; self-host and AWS results are not directly comparable.

## Reused code
- The scheduler `REGISTRY` (fcfs/static_quota) is retained as a fixed config; it is not a QuotaShift contribution and
  is not exercised as an experimental variable.

## Attack-effect analysis (Phase 5)
- **Mock results are plumbing only.** A `--mock` experiment exercises the gateway, matched-budget pairing and the
  analysis/reporting path; its latencies are simulator outputs (`synthetic_backend: true`) and must never be read as
  evidence of real cross-tenant interference. Only a live target (self-hosted or AWS) yields a measurement.
- **Small-sample statistics.** The default 5 repetitions give a bootstrap CI for exploration, not a significance
  claim. Increase repetitions based on observed variance before drawing conclusions; a wide CI around 1.0× is a
  negative result, reported as such.
- **Attack-success rate depends on the pre-registered threshold.** It is fixed per scenario before runs (ADR-Q08/Q11);
  the rate is only meaningful relative to that threshold and the chosen degradation metric.
