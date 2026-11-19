# Terraform proposal — QuotaShift (validated offline; **nothing deployed**)

Location: `infra/terraform/`. Provider `hashicorp/aws = 6.73.0` (lock file with darwin_arm64 + linux_amd64 hashes).
Backend: partial S3 backend with native lockfile (`backend.hcl.example`); state is never committed.

## Offline verification (2026-11-19, no AWS contact)
| Command | Result |
|---|---|
| `terraform init -backend=false` | ok (provider from public registry) |
| `terraform fmt -check -recursive` | pass |
| `terraform validate` | **Success! The configuration is valid.** |
| `terraform test` (mock provider, `command = plan`) | **10 passed, 0 failed** |

The mock-provider plan validates graph, variables, conditionals, preconditions, `check` blocks and the security
assertions. It does **not** verify AWS-side facts (AMI availability, quotas, instance offering in the AZ, IAM
validity); those need the real read-only `plan` in §Preflight.

## What the stack builds (QuotaShift topology)
- **Network (default `nat`, private):** VPC, one private compute subnet + one public subnet, IGW, one NAT gateway,
  locked-down default SG, free S3 gateway endpoint. No public IP on the GPU host or gateway. `endpoints` mode
  (≈10 interface endpoints, no IGW, requires `model_source=s3`) is the no-NAT alternative; `public_egress_only`
  remains but trips an advisory `check`.
- **Shared GPU backend:** ECS EC2 cluster + ASG (**min 0 / max 1 / desired 0**), launch template (`g5.2xlarge`,
  ECS GPU AMI via SSM, IMDSv2 required, encrypted gp3, no key pair), vLLM task (host net, `GPU=1`, digest-pinned
  image, `Qwen/Qwen2.5-7B-Instruct` @ `a09a354…`, `max_model_len=4096`) + service (**desired 0**). Optional DCGM
  exporter daemon.
- **Gateway (Fargate, internal):** Cloud Map private DNS namespace `quotashift.internal`, gateway task + service
  (**desired 0**, `assign_public_ip=false`), SG ingress from generators on 8080 only, egress to vLLM.
  Created only when `gateway_image` is set.
- **Generators (Fargate run-task):** `benign-runner` + `scenario-runner` task defs (created when `runner_image`
  set); SG with no ingress, talk to the gateway, never to vLLM directly.
- **Storage/observability:** S3 results bucket (SSE-S3, versioning, lifecycle, public access blocked, TLS-only
  policy), ECR repos `*-runner` and `*-gateway` (immutable, scan on push), 3 CloudWatch log groups (14-day
  retention), optional AWS Budget (alerts only).
- **IAM least privilege:** GPU host role (ECS+SSM), task execution role, vLLM task role (read `models/*`), runner
  task role (rw `results/*`, read `configs/*`). No role attaches `AdministratorAccess` (asserted in tests).

## Cost gates (see `docs/aws_cost_controls.md`)
`gpu_desired_capacity`, `vllm_desired_count`, gateway `desired_count` default 0. `max_run_minutes` and
`spending_limit_usd` are required (no default, validated > 0) and enforced by a `check` block. `stop-gpu` is ungated.

## Preflight before any approval (read-only; `scripts/check_prereqs.sh`)
- `aws sts get-caller-identity`; G/VT vCPU quota `L-DB2E81BA` ≥ 8; `g5.2xlarge` AZ offering; resolve + pin the ECS
  GPU AMI; confirm model license and volume fit; `scripts/estimate_cost.py` with current Price-List values.

## Known blockers (2026-11-18 real-account preflight, read-only)
- **G/VT on-demand vCPU quota = 0** → `g5.2xlarge` (8 vCPU) cannot launch until an increase is granted. **BLOCKER.**
- **Account observed using root access keys** → switch to a least-privilege IAM identity before any apply.
- Prices in `scripts/estimate_cost.py` are user-supplied; fill the price file on the approval day (the estimator
  refuses blanks).

Deploy is owner-run and approval-gated (`scripts/aws_ops.sh`); nothing here has been applied.
