# X2 G1 (AWS L4) deployment: prerequisites and approval request

**Date:** 2026-11-25, 12:08–12:15 EST.

**Owner decision:** AWS first (g1m0, then g1m1, on one g6.xlarge in sequence); no G0 experiment over Wi-Fi.

**Done so far:** read-only and offline only. Nothing was created, built or started, and no IAM change was made.

## 1. Read-only verification (readonly role)

| Check | Result |
|---|---|
| Terraform plan, `research.tfvars` + `research.x2.tfvars` (Qwen), local backend, placeholder owner, no budget email | **61 to add, 0 to change, 0 to destroy.** 62 with a budget email, 63 once `runner_image` is set |
| Plan contents | us-east-1; launch template **g6.xlarge**, no public IP; GPU ASG min 0 / max **1** / desired 0; private subnets (no public IP on launch); 1 NAT; vLLM service desired 0, pinned **0.17.1** image digest, `Qwen/Qwen2.5-7B-Instruct --revision a09a3545…` with the full template; **X1 sampler and DCGM daemons absent**; X2 snapshot daemon present; spending limit **$60**; `max_run_minutes` 1320 |
| Price List (published 2026-11-24, effective 2026-11-01) | g6.xlarge on-demand **$0.8048/h**, unchanged |
| Service quota, Running On-Demand G and VT | **4 vCPU**: exactly one g6.xlarge |
| Existing budgets / project ECR repositories | none / none (two unrelated repositories exist) |
| State bootstrap plan | **7 to add** (versioned, encrypted, private, TLS-only state bucket) |
| Proposed operator policy (`infra/iam/x1-operator-policy.x2-proposed.json` = live policy + `ecs:ExecuteCommand` on `quotashift-*` tasks, container `runner`, us-east-1) | IAM Access Analyzer **0 findings**; 8,633 of 10,240 characters |

## 2. Cost projection (GPU stopped between stages; 5 GPU starts per platform at about 15 min each)

| Scenario | GPU-h | Stack lifetime | Total (`estimate_cost.py`, 2026-11-24 prices, NAT mode) |
|---|---|---|---|
| Plan | 25 | 7 days | **$37.21** (GPU $20.12, NAT $10.26, Fargate $4.94) |
| Pessimistic | 34 | 10 days | **$49.58** |

- **The NAT gateway costs about $1.08 per day** while the stack exists, whether or not the GPU runs. Long pauses between stages therefore cost money, and `destroy` removes it.
- **Stop rule:** a projection above **$60** stops the campaign. The $60 budget alarm (actual and forecast) is the backstop.

## 3. Prerequisites and approvals, in order

| # | Item | Who / token |
|---|---|---|
| P1 | Create `infra/terraform/owner.auto.tfvars` (git-ignored) with your owner handle and **budget alert email**. I won't send your email to AWS unless you say so; you can fill the file in, or tell me which address to use | owner |
| P2 | Remote state: choose a random `bucket_suffix` (6–16 lowercase alphanumerics, no account id); apply `infra/state-bootstrap` (7 resources); write `infra/terraform/backend.hcl` and remove the local `backend_override.tf`. *Alternative:* keep local state with `aws_ops.sh state-backup` after every apply | **approve `state_bootstrap`** (or choose local state) |
| P3 | Operator IAM: replace the operator inline policy with `infra/iam/x1-operator-policy.x2-proposed.json` (adds only `ecs:ExecuteCommand`, runner container only); re-run the policy simulation afterwards | **approve `iam_x2_exec`** |
| P4 | Install the AWS Session Manager plugin locally (ECS Exec client) | owner, or approve the install |
| P5 | Deploy the stack: `aws_ops.sh plan research` with the X2 overlay → I review that **it equals §1 plus the budget resource** → `QUOTASHIFT_APPROVED=deploy aws_ops.sh deploy research`. Creates the 62 resources, with the GPU at **0** | **approve `deploy`** |
| P6 | Runner image: start Docker Desktop; `build_runner_image.sh build` from the clean commit, then `push` to the project ECR created by P5; set `runner_image` to the digest; re-plan (+1 task definition) and deploy that delta | **approve `build_image`, `push_image`**, and a second `deploy` |
| P7 | First-boot checks (B7, B-X2-9): `start-gpu`; vLLM healthy under the template; Cloud Map record; snapshot daemon answers from the runner only; runner can write `/app/results` as uid 10001; ECS Exec works; then `stop-gpu` | **approve `start-gpu`** (first boot, about 30 min) |
| P8 | **g1m0 qualification**: `x2-inputs`, then `run-stage` with `x2_qual_g1m0` (ECS Exec, interactive "yes"), about 1.8 h; `stop-gpu` afterwards | **approve `x2_qual_g1m0`** (+ `x2-inputs`, `run-stage`, `start-gpu`) |
| P9+ | Only if Q1 passes: `x2_freeze_calA_g1m0`, `x2_cal_g1m0`, `x2_freeze_main_g1m0`, `x2_main_g1m0`; then the same for g1m1 (Mistral overlay, same instance type); then `destroy` | separate approvals, per the owner's batch policy |

## 4. Notes

- **Instance identity across stages.** Stopping the GPU between stages means qualification, calibration A and main may run on different physical L4 hosts of the same instance type.
  - The frozen protocol defines the platform as the instance type and template, and checks server identity **within** each stage.
  - The instance id and the server start time are recorded per stage. Different hosts across stages are reported as a threat; they are not a protocol deviation.
- **G0 stays paused** until Ethernet, as the owner instructed.
