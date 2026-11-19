# Implementation Status (2026-11-18, end of Milestone 0/1 turn)

| Item (master plan) | Status | Evidence |
|---|---|---|
| M0.1 repo audit | done | `docs/REPO_AUDIT.md` |
| M0.2 pin stack / ECS GPU prerequisites | partial: pins chosen by digest/SHA; GPU/driver/AMI compatibility unverified | `docs/REPRODUCIBILITY.md`, ADR-010 |
| M0.3 novelty matrix, protocol, metrics, Terraform proposal | done (drafts; prior art not read in full) | `docs/NOVELTY_MATRIX.md`, `EXPERIMENT_PROTOCOL.md`, `METRIC_DEFINITIONS.md`, `TERRAFORM_PROPOSAL.md` |
| M0.4 architecture decision + future vLLM-integration options | done | `docs/DECISIONS.md` ADR-001/002 |
| M0.5 deterministic mock smoke + schema validators | done | `tests/`, `results/smoke/*` |
| M0 gate: no AWS charges | met (no AWS API calls made) | — |
| M1.1 local mock provider + real vLLM adapter | done (adapter untested against real vLLM) | `serving/mock_server.py`, `serving/openai_backend.py`, `results/smoke_http/*` |
| M1.2 one-model one-GPU serving profile | **not done** — no NVIDIA GPU available; awaiting approval | commands in `REPRODUCIBILITY.md` |
| M1.3 E0 sweep harness (256/1k/4k/8k × 128/512/1k/2k × 1..64) | harness done; validated on mock only | `configs/experiments/e0.yaml`, `results/e0_smoke/*` |
| M1.4 compute/KV/knee profiling on real GPU | **not done** | — |
| M1.5 plots (throughput, TTFT, TPOT, KV, queue, preemptions, goodput vs load) | done for mock data, auto-generated + watermarked | `results/e0_smoke/*/figures/` |
| M1 gate: repeatable E0 on a GPU | **not met** (blocked on GPU access/approval) | — |
| Docker Compose local stack | written; `compose config` validated; image **not built** | `docker/` |
| Terraform | fmt/validate/mocked-plan tests pass; real plan not run | `infra/terraform/` |
| M2–M5 (baselines, predictors, RISK-Sched, E2–E8) | not started (out of scope) | — |

Test suite: **87 passed, 1 skipped** (`uv run pytest -q`; the skip is the opt-in real-GPU test). Lint clean.
