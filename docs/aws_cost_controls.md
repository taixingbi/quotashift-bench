# AWS cost controls — QuotaShift

Nothing is deployed. Every billable action is approval-gated in `scripts/aws_ops.sh`
(`QUOTASHIFT_APPROVED=<action>` env + interactive `yes`). Prices are never hardcoded; fill a price file and run
`scripts/estimate_cost.py` before requesting approval.

## Stop conditions
- **GPU ASG desired capacity defaults to 0** and `vllm_desired_count`/gateway `desired_count` default to 0:
  applying the stack starts no GPU and no standing service.
- **`max_run_minutes` and `spending_limit_usd` are required** Terraform variables (no defaults, validated > 0) and a
  `check` block refuses a plan if they are unset/non-positive.
- `scripts/aws_ops.sh stop-gpu <env>` is **ungated** (it only reduces cost) and scales the GPU ASG, the vLLM
  service, and the gateway service to 0.
- `scripts/destroy.sh <env> --dry-run` previews teardown (`plan -destroy`); `scripts/destroy.sh <env>` is gated.

## What bills
| State | What bills |
|---|---|
| Applied, GPU stopped (`nat` default) | NAT gateway **hourly, 24/7 while applied** + per-GB; S3/ECR/log storage; (no public IPv4, no instance) |
| GPU running | EC2 `g6.xlarge` (X1; $0.8048/h us-east-1, 2026-11-24) on-demand + its gp3 root volume + log ingestion (dominant cost) |
| + gateway / generators | Fargate vCPU/GB-hours while tasks run |
| `endpoints` mode | ~10 interface endpoints hourly per AZ, 24/7 while applied (requires S3-staged weights) |

**Idle cost trap:** the private-by-default `nat` mode bills a NAT gateway for as long as the stack exists, even with
the GPU at 0. To drop idle cost to ~storage only, `destroy` when not in use, or use `endpoints` mode.

## Preflight before any approval (read-only; `scripts/check_prereqs.sh`)
- `aws sts get-caller-identity` — use the **X1 role profiles** (`quotashift-x1-readonly` / `-operator`); `aws_ops.sh` refuses root.
- G/VT on-demand vCPU quota `L-DB2E81BA` ≥ 4 for `g6.xlarge` (observed **4** on 2026-11-24; X1: no increase requested).
- `g6.xlarge` offered in the chosen AZ (all 5 us-east-1 AZs, 2026-11-24); ECS GPU AMI pinned `ami-0b8f7c7154f9e8f8b`.
- Confirm the Qwen2.5-7B-Instruct license (Apache-2.0) and that the image + weights fit the root volume.
- `scripts/estimate_cost.py --prices <file> --gpu-hours <h> --network-mode nat` with current Price-List values.

## Cost Explorer
`scripts/aws_ops.sh cost-report <env>` is gated because each Cost Explorer request is billed (~$0.01). Budgets are
alerts only (set `budget_alert_emails`); they do **not** stop spend.

## X1 (2026-11-24)
- Spending limit **$60** (`spending_limit_usd`, `monthly_budget_usd`); `max_run_minutes = 1320` (longest stage, X1-N).
- The AWS Budget alarm is created only when `budget_alert_emails` is set in `envs/research.tfvars` — **set an owner email before X1-J** (alerts only; they do not stop spend).
- Estimated X1 AWS total ≈ $36 planned / $51 pessimistic (`docs/X1_P0_REPORT.md` addendum).
