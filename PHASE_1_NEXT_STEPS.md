# Phase 1 — Next Steps (for the next Claude Code turn)

State at hand-off (2026-11-18): Milestone 0 complete; Milestone 1 harness complete and validated on mock
backends only. **No real GPU data exists.** 87 tests pass, 1 GPU test skipped. Nothing deployed; no AWS calls made.

## Update 2026-11-18 (AWS chosen)
- Read-only preflight + real `terraform plan` done: 43 to add, nothing running by default (docs/TERRAFORM_PROPOSAL.md).
- **Blocker:** G/VT on-demand vCPU quota = 0 in us-east-1. Increase to 4 **requested 2026-11-18** (request id `ac76b4907e9a4163904e1e2cd638d974f2oDpO1S`, status PENDING).
- `terraform apply dev.tfplan` approved by owner but blocked by the Claude Code permission classifier; nothing applied yet.
- Credentials in use are **root** access keys → create a least-privilege IAM user/role for deploys.

## Topic pivot 2026-11-18 (ADR-011)
Security framing: defend the shared engine against resource-exhaustion attacks (latency-DoS, KV Fill & Squeeze,
output/reasoning-length inflation, denial-of-wallet). Infra unchanged. See docs/THREAT_MODEL.md.
Next for the pivot (zero cost, can start now):
1. Full read: *Rethinking Latency DoS* (2602.07878), PrefixShield (2608.01657), OverThink defenses, Engorgio.
2. Add attack tenant profiles to the workload generator (T1 length inflation, T3 fill/squeeze timing, T4 budget
   drain, T5 edge pacing) and validate them on the mock engine (mock = plumbing only).
3. Security metrics in `evaluation/metrics.py`: amplification factor, benign SLO delta vs paired no-attack run,
   false-positive throttling.
4. Baseline defenses as `SchedulerPolicy`: static quotas (OWASP), KV-utilization admission threshold.
5. On GPU (after quota + approvals): E0 as planned, then reproduce T1/T3 on Qwen3 to confirm the threat is real.

## Decisions needed from the owner (blocking)
1. GPU access for E0: (a) local RTX 3090 (zero cloud cost), or (b) AWS: approve a read-only `terraform plan`
   then a deploy + ≤2 GPU-hour Qwen3-1.7B smoke (see `docs/TERRAFORM_PROPOSAL.md`).
2. Confirm `owner` tag, region, network mode (`public_egress_only` default), budget alert email.
3. Confirm project license (Apache-2.0 provisional) and make the first git commit so manifests carry a SHA.

## Work items (in order)
1. **Novelty de-risking (before any method code):** read in full JITServe, FairInference (2609.18112),
   Cascade (2608.06557), Robust KV under length uncertainty (2607.16892), "Scheduling the Unschedulable"
   (2604.06970), Equinox, QLM. Update `docs/NOVELTY_MATRIX.md` to V2 (full text) and decide go / narrow.
2. **E0 on GPU (after approval):**
   - Start vLLM v0.33.0 with Qwen3-1.7B; `validate-env --backend-url`; run `pytest -m gpu` (opt-in).
   - Verify A2/A3 in `docs/ASSUMPTIONS.md` (metric names, token-ID prompts, include_usage, ignore_eos).
   - Reduced grid (1 trial) → full `configs/experiments/e0.yaml` for Qwen3-4B (3 trials) → rate sweep re-centred
     on the measured knee. Record KV cache size from the vLLM log, driver/CUDA, image digest.
   - Gate: controlled saturation, 0 event-validation errors, repeatable across trials.
3. **Calibrate SLOs and tenant rates** from E0; freeze in `configs/tenants/` and `EXPERIMENT_PROTOCOL.md` §3.
4. **Milestone 2 baselines** through the existing `SchedulerPolicy` interface: vLLM priority hints (ADR-002 B),
   per-tenant RPM/TPM token buckets, WFQ/DRR, tuned GPU-aware heuristic (uses `BackendObservation`), then
   E2/E3/E4 with ≥2 seeds per smoke scenario; add paired bootstrap CIs to `compare`.
5. Public prompt datasets with license audit to replace synthetic templates.
6. Infra follow-ups: build/push runner image by digest, DCGM scraping in the runner, tflint/checkov, CI workflow.

## Known open bugs / risks
- vLLM `priority` semantics and metric names unverified on v0.33.0.
- DCGM exporter on ECS GPU AMI without GPU reservation unverified.
- Runner (asyncio) overhead at high concurrency unmeasured.
