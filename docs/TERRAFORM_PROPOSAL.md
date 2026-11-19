# Terraform Proposal (validated offline; **nothing deployed**)

Location: `infra/terraform/`. Provider `hashicorp/aws = 6.73.0` (lock file with darwin_arm64 + linux_amd64 hashes).
Backend: partial S3 backend with native lockfile (`backend.hcl.example`); state never committed.

## What was executed (2026-11-18)
| Command | Result | AWS contact |
|---|---|---|
| `terraform -chdir=infra/terraform init -backend=false` | ok (provider download from public registry) | none |
| `terraform -chdir=infra/terraform fmt -check -recursive` | pass | none |
| `terraform -chdir=infra/terraform validate` | **Success! The configuration is valid.** | none |
| `terraform -chdir=infra/terraform test` (mock provider, `command = plan`) | **7 passed, 0 failed** | none (mock provider; no credentials) |
| Negative control: `terraform test -var gpu_desired_capacity=1` | default-safety assertion **fails as intended** | none |
| `terraform plan -var-file=envs/dev.tfvars` against account …6513, **local state** (`backend_override.tf`, gitignored) | **Plan: 43 to add, 0 to change, 0 to destroy**; saved `infra/terraform/dev.tfplan`, log `results/tf_plan_dev.txt` | read-only (2026-11-18) |

The mock-provider plan is an *offline* plan: it validates graph, variables, conditionals, preconditions and
security assertions, but it does not verify AWS-side facts (AMI availability, quotas, instance-type offering
in the AZ, IAM policy validity). Those require the real `terraform plan` + preflight in §5.

## Resources in the default plan (43; identical in mocked and real plan)
Networking: `aws_vpc`, `aws_default_security_group` (locked down), 1 public subnet, IGW, public route table +
route + association, **S3 gateway endpoint (free)**, SGs `runner` and `gpu_host`, ingress rules
`vllm_from_runner` (tcp/8000, SG-referenced) and `dcgm_from_runner` (tcp/9400, SG-referenced), 2 egress rules.
Compute: `aws_ecs_cluster` (Container Insights off), `aws_launch_template.gpu` (g6.xlarge, ECS GPU AMI AL2023 via
SSM, IMDSv2 required, 120 GB encrypted gp3, no key pair), `aws_autoscaling_group.gpu` (**min 0 / max 1 /
desired 0**), `aws_ecs_task_definition.vllm` (host network, GPU=1, digest-pinned v0.33.0, Qwen3-4B pinned
revision, prefix caching off) + `aws_ecs_service.vllm` (**desired 0**), DCGM exporter task + DAEMON service.
IAM: GPU host role + instance profile (ECS + SSM managed policies), task execution role, vLLM task role
(read `models/*` only), runner task role (rw `results/*`, read `configs/*`).
Storage/observability: S3 results bucket (+ ownership controls, public access block, SSE-S3, versioning,
lifecycle, TLS-only policy), ECR runner repo (immutable, scan on push) + lifecycle, 3 log groups (14 days).
Not created by default: NAT gateway, interface endpoints, AWS Budget (needs emails), runner task definition
(needs a digest-pinned ECR image).

Variants tested: `network_mode=nat` (1 NAT + private subnet, no public IP on GPU host),
`network_mode=endpoints` (10 interface endpoints, no IGW; **requires** `model_source=s3`, enforced by precondition).

## Idle vs running cost profile
| State | What bills | Notes |
|---|---|---|
| Applied, GPU stopped (default) | S3 storage, ECR storage, log storage, (Route-less) VPC = ~0; Budgets free tier | No NAT, no endpoints, no instance, no public IPv4 |
| GPU running | EC2 g6.xlarge on-demand, its public IPv4, 120 GB gp3 (exists only while instance exists), log ingestion | dominant cost = instance-hours |
| + runner task | Fargate vCPU/GB-hours + public IPv4 for the task | only during runs |
| `nat` mode | NAT hourly **24/7 while it exists** + per-GB processing | largest *idle* cost trap |
| `endpoints` mode | 10 endpoints × AZ × hourly **24/7 while they exist** + per-GB | second idle cost trap |

**Indicative magnitudes only** (from public us-east-1 list prices as remembered by the assistant — *unverified*;
fill `configs/infrastructure/prices.example.yaml` from the AWS Pricing Calculator before approval and run
`scripts/estimate_cost.py`): g6.xlarge ≈ $0.8/h; public IPv4 ≈ $0.005/h; NAT ≈ $0.045/h + $0.045/GB;
interface endpoint ≈ $0.01/h/AZ each (×10); gp3 ≈ $0.08/GB-month; CloudWatch Logs ingestion ≈ $0.50/GB;
Fargate ≈ $0.04/vCPU-h + $0.0044/GB-h.

## Estimated usage for the next phase (E0 on L4)
- Full E0 grid in `configs/experiments/e0.yaml`: 4 prompt × 4 output × 6 concurrency × 3 trials = 288 cells
  (+ warm-up) and 8 rates × 3 trials × ~2–12 min rate sweep. Wall time is **unknown until measured**;
  planning range **8–15 GPU-hours** (could be 2× higher if long-context cells are slow).
- Recommended first approval: **Qwen3-1.7B smoke, 1 trial, reduced grid, ≤2 GPU-hours, hard stop**; then the 4B grid.
- Model download ~3.4 GB (1.7B) / ~8 GB (4B) + vLLM image ~9.7 GB compressed per fresh instance.

## Cost risks (ranked)
1. **Forgotten running GPU instance** (accrues ~24×/day). Mitigation: desired 0 by default; `stop-gpu` ungated;
   `max_total_seconds` budget in E0; budget alerts (alerts only — not a hard stop).
2. **NAT/endpoint modes left applied** — bill 24/7 even with GPU stopped. Default mode avoids both.
3. Repeated instance launches pulling a ~10 GB image (startup time ≈ GPU billing time; `prefer-cached`).
4. Log ingestion from verbose vLLM logs at high request rates (14-day retention bounds storage, not ingestion).
5. Cost Explorer API calls (~$0.01/request) — `cost-report` is gated.
6. S3 versioning of large result files (noncurrent versions expire after 30 days).

## Preflight before any approval request (read-only)
- `aws service-quotas get-service-quota --service-code ec2 --quota-code L-DB2E81BA` (Running On-Demand G and VT
  instances, vCPU) ≥ 4 in the chosen region.
- `aws ec2 describe-instance-type-offerings --location-type availability-zone --filters Name=instance-type,Values=g6.xlarge`
- Resolve and record the ECS GPU AMI ID; confirm its NVIDIA driver supports the CUDA version in the pinned vLLM image.
- Confirm Qwen3 license (Apache-2.0 on HF) and that no HF token is needed.
- Confirm the image fits the 120 GB root volume with model cache.

## Real-account preflight (2026-11-18, read-only)
| Check | Result |
|---|---|
| Caller identity | account `<redacted>…6513`, **root user access keys** — switch to a least-privilege IAM identity before apply |
| Running On-Demand G and VT instances quota (L-DB2E81BA) | **0 vCPU → BLOCKER**; g6.xlarge needs 4 |
| g6.xlarge offerings | us-east-1a/b/c/d/f; L4 reports 22,888 MiB; 4 vCPU / 16 GiB |
| ECS GPU AMI (SSM recommended) | `ami-06a271b771d5a8b7b` = `al2023-ami-ecs-gpu-hvm-2023.0.20261113-kernel-6.1-x86_64-ebs`, ECS agent 1.108.3, Docker 25.0.18 — pin via `gpu_ami_id` |
| Existing project resources / running instances / budgets | none / 0 / none |

## Prices (AWS Price List API, 2026-11-18) → `configs/infrastructure/prices.us-east-1.yaml`
g6.xlarge $0.8048/h · public IPv4 $0.005/h · gp3 $0.08/GB-mo · NAT $0.045/h + $0.045/GB · VPC interface endpoint
$0.01/h · CloudWatch Logs ingest $0.50/GB · S3 Standard $0.023/GB-mo · ECR $0.10/GB-mo · Fargate (unverified list
price) $0.04048/vCPU-h + $0.004445/GB-h.

`scripts/estimate_cost.py` (defaults: 2 GB logs, 20 GB S3, 120 GB EBS): **2 GPU-h smoke ≈ $3.41**,
**15 GPU-h full E0 ≈ $15.46** (excl. tax / data transfer out). Idle (applied, GPU at 0): ≈ S3 + ECR storage only.
