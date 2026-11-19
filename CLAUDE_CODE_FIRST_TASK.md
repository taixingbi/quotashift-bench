# Claude Code — First Turn

Read `CLAUDE_CODE_MLSYS_MASTER_PLAN.md` in full. This is **Paper A (GPU-aware multi-tenant LLM serving, targeting MLSys main)**, NOT the hidden-capacity gateway paper and NOT the separate Safe RL paper.

Proceed with **Milestone 0 and Milestone 1 only**. Inspect the existing repository before designing anything. Build the zero-cost mock backend and deterministic three-tenant request/metric framework; write the related-work novelty matrix and proposed AWS ECS GPU Terraform (plan/validate only). Prepare a reproducible E0 GPU profiling harness for Qwen3 1.7B/4B on vLLM. Run automated tests and zero-cost smoke experiments, and report exact evidence and missing pieces. Do not claim real GPU results unless they were actually measured. Do not deploy anything, call paid AWS APIs, start GPU instances, or run stress tests without explicit approval.

At the end provide: changed files, exact commands executed, pass/fail summary, actual output paths, AWS resources in the proposed plan, cost risks, novelty uncertainties, and a short plan for the next phase.
