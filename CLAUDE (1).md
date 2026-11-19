# QuotaShift project instructions for Claude Code

Read `QUOTASHIFT_CLAUDE_CODE_PLAN.md` before working. This is a reproducible, **attack-only** multi-tenant LLM resource-interference research simulator running exclusively in an authorized, isolated AWS VPC.

Priorities:
1. Bounded synthetic workloads; no public/third-party targets or quota circumvention.
2. Implement and test the local fake backend, scenario parser, deterministic schedule generator, private tenant gateway, and experiment recorder first.
3. Terraform: GPU vLLM on ECS EC2; CPU-only gateway and generators on Fargate; shared private serving backend; S3/CloudWatch results.
4. Fixed and enforced budgets, explicit stop conditions, version/seed logging, and paired controls.
5. Metrics only for validating attack simulation, NOT a defense, RL, or scheduling study.
6. No cloud deployment, GPU startup, paid operations, or live experiment without user approval.
7. Update `IMPLEMENTATION_STATUS.md` after each phase; record actual command/test results, never fabricate success.

Start with Phase 0 and 1 from the plan; then prepare a reviewable Terraform plan.
