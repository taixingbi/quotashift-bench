# RISK-Sched research platform (Paper A)

Tenant-aware, GPU/KV-aware **admission & dispatch** for multi-tenant LLM serving on a single vLLM engine —
experimental platform for an MLSys submission. Status: **Milestone 0/1 framework; no real-GPU results yet.**

- Plan: `CLAUDE_CODE_MLSYS_MASTER_PLAN.md` · Status: `docs/IMPLEMENTATION_STATUS.md` · Next: `PHASE_1_NEXT_STEPS.md`
- Architecture & control boundary: `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`
- Prior art: `docs/NOVELTY_MATRIX.md` (novelty currently at risk — read §3)
- Metrics / protocol: `docs/METRIC_DEFINITIONS.md`, `docs/EXPERIMENT_PROTOCOL.md`
- Reproduce: `docs/REPRODUCIBILITY.md`; AWS (not deployed): `docs/TERRAFORM_PROPOSAL.md`

```bash
uv sync && uv run pytest -q
make smoke e0-mock             # deterministic mock engine (synthetic timings, watermarked)
make smoke-http                # same gateway over HTTP/SSE to a local mock vLLM server
make tf-validate tf-test       # offline Terraform checks (mock AWS provider)
```
