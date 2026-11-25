# X1 AWS deployment readiness (X1-E completion)

**Date:** 2026-11-24. **Status: offline-ready, NOT deployed.**
- No AWS resource was created or modified. No apply, no S3 bucket, no image build or push.
- No GPU host was touched. No model was downloaded and no GPU work was run.
- No credential was changed.
- AWS was used only for read-only API calls, under `quotashift-x1-readonly`:
  - `terraform plan`;
  - Access Analyzer `validate-policy`.
  
  There is one exception: IAM `simulate-custom-policy`, a read-only policy evaluation, ran under the default profile, because the readonly role has no simulator permission.

## 1. Architecture as prepared (us-east-1, private only)

| Component | Configuration | Evidence |
|---|---|---|
| GPU host | ASG with **g6.xlarge only** (validation plus IAM), AMI `ami-0b8f7c7154f9e8f8b` pinned, desired 0 / max 1, no public IP, private subnet | tf tests; plan |
| vLLM | `vllm/vllm-openai@sha256:0dc46f74…` (0.17.1), host networking. Argv = the X1 template; dev mode on; Mistral flags via `envs/research.m1-mistral.tfvars` (`QUOTASHIFT_MODEL=m1-mistral`) | tf tests (both models); plans |
| Private DNS | Cloud Map namespace `quotashift.internal`, A record **`vllm.quotashift.internal`**, registered by the GPU host at boot under a fixed instance id (a scoped IAM inline policy allows only that) | tf test (mock apply); plan |
| Runner | Fargate task, 4 vCPU / 8 GB, private subnet, `assignPublicIp=DISABLED`. Runs `scripts/x1_stage.py` with the **in-process FCFS gateway** (the cap comes from each scenario, as v5). `QUOTASHIFT_IN_VPC_RUNNER=1` and `QUOTASHIFT_TARGET` = `x1-g1-{qwen,mistral}`, chosen from the model | tf tests; plan |
| Standalone gateway service | **Disabled** for X1. A Terraform precondition refuses `gateway_image` while `x1_inprocess_gateway = true`, because it would add a second admission layer | tf test |
| Results | Task volume → digest-pinned `amazon/aws-cli` 2.39.6 sidecar → `s3 sync` to the project results bucket after the runner completes | tf test |
| Security groups | vLLM :8000 only from the runner SG (and the legacy gateway SG); DCGM :9400 only from the runner SG; no CIDR ingress anywhere | plan inspection |
| Host telemetry | `x1-host-sampler` ECS daemon: host PID namespace, read-only root filesystem, no ports, script SHA-256 pinned, logs to CloudWatch | tf tests; plan |
| Budget | $60 monthly; alerts at 50/80/100% actual and 100% forecast. **Created only when `budget_alert_emails` is set** | tf test |
| Stop / destroy | `stop-gpu` (never gated; sets ASG and services to 0); `destroy` and `deploy` gated; a mock apply + destroy cycle leaves desired = 0 | tf test; `tests/unit/test_x1_iam.py` |
| Remote state | `infra/state-bootstrap/`: bucket `quotashift-tfstate-<suffix>`, versioning, SSE, all public access blocked, BucketOwnerEnforced, TLS-only policy, deny bucket deletion or disabling versioning, `prevent_destroy`, noncurrent versions kept 365 days, **S3-native locking** (`use_lockfile = true`) | bootstrap tf tests (2 of 2); read-only plan: 7 to add |
| State backup | `aws_ops.sh state-backup` (read-only `state pull` → `~/QuotaShift-backups/tfstate/`, mode 600, sha256 printed) after every apply and destroy | script |
| Runner image | `docker/Dockerfile` now copies `scripts/`, `experiments/` and the X1 protocol; build provenance via `GIT_SHA`/`GIT_DIRTY` args. `scripts/build_runner_image.sh` refuses a dirty tree and gates `build` and `push` separately. `git_info` falls back to the baked commit only when no `.git` exists, labelled `source: image-build` | `bash -n`; dry-run |
| Harness | `experiment --live` accepts an AWS target **only** with `QUOTASHIFT_IN_VPC_RUNNER=1`, so a workstation can never drive it | `tests/unit/test_x1_cli_vpc_guard.py` |
| IAM | **Operator policy revised:** it was missing the read actions Terraform needs (Describe/Get/List). Access Analyzer: 0 findings. Custom-policy simulator: **46 of 46** create, modify and read actions of the plan allowed, with the earlier guard rails unchanged | `tests/unit/test_x1_iam.py`; simulator |

**Read-only plans** (`quotashift-x1-readonly`, local state, nothing applied):

| Configuration | Plan |
|---|---|
| Qwen | **62 to add / 0 change / 0 destroy** |
| Mistral | **62 / 0 / 0** |
| With a placeholder runner digest | **65 / 0 / 0** |
| State bootstrap | **7 / 0 / 0** |

## 2. Remaining blockers (exact)

| # | Blocker | Who | Kind |
|---|---|---|---|
| B1 ✅ done 2026-11-24 21:15 (verified: live = reviewed `9727889`; trust unchanged; simulator 23/23 + 54/54) | ~~Re-apply the revised operator inline policy~~ (`infra/iam/x1-operator-policy.json`) to role `quotashift-x1-operator`. The live role lacks read permissions, so `deploy` would fail | owner approval → `aws iam put-role-policy` | AWS change (IAM) |
| B2 | Copy `infra/terraform/owner.auto.tfvars.example` to the **git-ignored** `owner.auto.tfvars`, and set `owner` and `budget_alert_emails` locally. `aws_ops.sh deploy` now **refuses** any plan without the budget alarm | owner | local file (never committed) |
| B3 | Choose the remote state option: approve **applying `infra/state-bootstrap`** (one S3 bucket, about $0/month at this size), then write `backend.hcl` and remove the local `backend_override.tf`, **or** approve local state with `state-backup` after every apply | owner | AWS change / decision |
| B4 | **Build the runner image** (`build_image`) and **push it to the project ECR** (`push_image`). ECR exists only after deploy, so: deploy → push → set `runner_image` → re-plan → apply | owner approvals | build / push |
| B5 | **Freeze Commit 1** (`x1_freeze1`) after confirming the implementation choices in `docs/X1_FREEZE_CANDIDATE.md` §2. Live stages refuse without it | owner | repo freeze |
| B6 | G0 stages first (X1-C/D/H/I): the local environment, model downloads, P1 plus preflight Phase 1, calibration traces, calibration A/B | owner approvals | local GPU |
| B7 | Verify on first boot: Cloud Map registration from the AL2023 GPU AMI (AWS CLI present, permissions sufficient), DCGM exporter on the L4, NVIDIA driver vs the 0.17.1 image | P1 on G1 (X1-K) | first live check |

## 3. Approval sequence (each a separate owner approval; cost on g6.xlarge)

| Order | Stage | Action | Cost |
|---|---|---|---|
| 1 | B1 | Re-apply the operator policy | $0 |
| 2 | B2, B3 | Budget email; state bucket (or local state) | ≈ $0 |
| 3 | X1-G | Freeze Commit 1 | $0 |
| 4 | X1-C, X1-D | gpu-node-2: 0.17.1 environment, model downloads, restart with the template, P1 + Phase 1 | $0 (local) |
| 5 | X1-H | Calibration-trace freeze (both models, on gpu-node-2) | $0 |
| 6 | X1-I | G0 calibration A → Phase 2 → calibration B, both models (about 2 × 3.6 h) | $0 (local) |
| 7 | X1-J | `deploy` (operator profile); push the runner image; set `runner_image`; re-plan / apply | NAT ≈ $1.08/day while applied |
| 8 | X1-K | `start-gpu`: G1 P1, Phase 1, calA → Phase 2 → calB, both models → `stop-gpu` | ≈ 7.6 GPU-h ≈ $6.1 |
| 9 | X1-L | Freeze 3: rates, predictions, main-stage traces for all 4 platforms | $0 |
| 10 | X1-M | G0 main stages (2 × 7.8 h) | $0 (local) |
| 11 | X1-N | G1 main stages (2 × 7.8 h, ×1.3 budget ceiling) → `stop-gpu` | ≈ 15.7–20.4 GPU-h ≈ $12.6–16.4 |
| 12 | X1-O | `destroy`, export, frozen analysis | $0 after destroy |

## 4. Updated execution and cost estimates

**Per-platform wall time.** From `v5_stage.estimate_min`: 2.6 min per 120 s arm, plus 2 min of tokenization per block.

| Phase | Minutes |
|---|---|
| Calibration A | 105.6 |
| Calibration B | 112.0 |
| Main | 469.6 |
| **Total** | **687 min ≈ 11.5 h**, plus about 1 h of P1, preflight, smoke and model load |

**Totals:**
- G0 (local): about 25 h of GPU time for both models.
- G1 (AWS): about 25–27 GPU-h nominal, or 32 h at the 1.3 budget ceiling.

**AWS cost** (`scripts/estimate_cost.py`, prices re-verified 2026-11-24; NAT 120 h, 60 GB NAT, 120 GB EBS, 3 GB logs, Fargate runner 4 vCPU / 8 GB for 27 h):

| Scenario | GPU-hours | Total |
|---|---|---|
| Plan | 30 | **$40.03** (GPU $24.14, NAT $8.10, Fargate $5.33, other $2.46) |
| Pessimistic | 45 | **$52.30** |

- **Cap:** the **$60** cap and every cost control are kept.
- **Fargate prices** in the price file are still marked unverified list prices.
- **Not included:** Cloud Map private hosted zone (about $0.50 per month, pro-rated), taxes and support.
