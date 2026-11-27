# X2 AWS evidence integrity and cleanup proposal (G1 campaign complete)

**Status:** audit run on 2026-11-27, 17:58–18:16 EST, read-only.
- No resource was created, changed or deleted, and Cost Explorer was not called.
- **The cleanup below is a PROPOSAL.** Nothing in it is executed without the owner's explicit `destroy` approval and
  the backup preconditions in §3.

## 1. Evidence integrity

| Check | Result |
|---|---|
| Local checksum manifests, g1m0 and g1m1 (qualification, calibration A, main) | **9 manifests, 0 failures**: g1m0 root 4 files, calA 73, main 49 + RUNS 1,088; g1m1 root 20 (qualification, AWS logs, diagnostics), calA 73 + RUNS 288, main 49 + RUNS 1,088 |
| S3 `results/` vs the local mirror `results/aws/` | **3,287 objects, all single-part; size and MD5 equal for 3,287 / 3,287** (g1m0 1,624, g1m1 1,659, other 4) |
| Run directories in S3 | g1m0 calA **36**, main **136**; g1m1 calA **36**, main **136** (expected 36 / 136 each) |
| `results/` run-dir copies vs the mirror | 2,752 files, 0 differ |
| Stage logs | g1m0 and g1m1 calA `completed` 6/6, main `completed` 4/4, each with one server start |
| Phase pins | `experiments/x2/g1m0/PHASE_PINS.json` (calA), `experiments/x2_a2/g1m0/PHASE_PINS.json` (main), `experiments/x2/g1m1/PHASE_PINS.json` (calA), `experiments/x2_a2/g1m1/PHASE_PINS.json` (main); all verified by the frozen stage drivers before every block, and pins v5/X2/A2/A3/X1/A1 match today |
| Counter identity of every frozen trace (`scripts/x2_counter_check.py`) | g1m0 calA + main: frozen counter; g1m1 calA + main: X2-A3 sequential, as required |
| S3 bucket settings | versioning **Enabled**, SSE AES256, all four public-access blocks on; lifecycle: noncurrent versions expire after 30 days, staged models (`models/`) after 30 days, incomplete uploads after 7 days |
| CloudWatch logs | **Retention 14 days.** All runner (83 streams, 463 events) and vLLM (15 streams, 488,959 events) streams exported 2026-11-27 to git-ignored `reports/x2/cloudwatch/` with `SHA256SUMS` (100 files). Before this export, the g1m1 calA/main and most g1m0 runner logs existed only in CloudWatch |
| Backup manifest | `reports/backup/BACKUP_MANIFEST.json` refreshed 2026-11-27 (X2 raw evidence 3,564 files, 84.7 MB) |

### Gaps, reported and not fixed by deleting or overwriting anything

1. **No independent off-machine backup exists.**
   - `~/QuotaShift-backups/`, which holds the tfstate copies and the v5 archives, is on the **same internal disk** as
     the repository; it is 89 % full.
   - The only other copy of the raw X2 evidence is the S3 bucket, in the account that a destroy would remove.
   - Making the off-machine copy is an owner action (`docs/BACKUP_PLAN.md`). After it,
     `scripts/backup_manifest.py --verify` checks the copy.
2. **g1m0 calibration A had no run-directory checksum file (`RUNS_SHA256SUMS`).** A retroactive one now exists: `reports/x2/g1m0/calA/RUNS_SHA256SUMS.retroactive-2026-11-27`, 288 files, matching S3 by MD5.
   - It proves integrity from 2026-11-27 onward only, not before that date.
3. **The operator role cannot list S3 object versions** (`s3:ListBucketVersions` denied). The noncurrent-version
   state was not verified.
4. **CloudWatch retention is 14 days.** Logs written after today's export will expire unless they are exported again
   before destroy.

## 2. Standing cost while idle

| Item | Approximate cost |
|---|---|
| NAT gateway | $0.045/h, about $1.08/day |
| Public IPv4 | about $0.12/day |
| One interface endpoint | about $0.24/day |
| S3 storage (83 MB) | negligible |
| ECR (12 runner images, 2.8 GB) | about $0.28/month |
| CloudWatch | small |
| **Total** | **about $1.5/day** |

Prices are from `configs/infrastructure/prices.us-east-1.2026-11-24.yaml`.

- **Campaign estimate:** about $36 of $60, with about 21.5 GPU-h.
- **Until 2026-11-29** (G0 runs locally and needs no AWS): about +$3.

## 3. Cleanup proposal (not executed)

A read-only `terraform plan -destroy` previews **63 resources to destroy**: VPC, subnets, NAT, endpoint, ECS
cluster and services, three task definitions, the GPU ASG and launch template, IAM roles and policies, log groups,
both ECR repositories, the S3 bucket and its configuration, and the budget.

- `aws_s3_bucket.results` has **no `force_destroy`**, so destroy fails on the non-empty, versioned bucket.
- Both ECR repositories have `force_delete = false`, so destroy fails on the 12 runner images.

A plain destroy therefore fails part-way instead of deleting evidence. That is a safety property, not a plan.

**Preconditions, all owner actions before any destroy:**
1. An independent off-machine copy of `results/aws/`, `results/x2_*`, `reports/x2/g1m*/`,
   `reports/x2/cloudwatch/`, `.x2_inputs/` and `~/QuotaShift-backups/tfstate/`, verified with
   `backup_manifest.py --verify`.
2. A final CloudWatch export, after the last AWS action.
3. A decision on what to retain:
   - **Recommended:** keep the S3 bucket (cents per month) and the runner ECR repository, which holds the image digest
     every G1 result cites.
   - Remove the compute and network stack (NAT, endpoint, VPC, ECS, ASG), which carries all of the daily cost.
4. A state backup (`aws_ops.sh state-backup`).

**Proposed sequence** (each step needs approval; nothing here is executed):
1. `aws_ops.sh stop-gpu research`: already at 0/0, no tasks.
2. Targeted destroy of the cost-bearing stack only: `terraform destroy -target=…` for the NAT gateway, EIP,
   interface endpoint, ECS services, the GPU ASG and launch template. Run a targeted `plan -destroy` first and review
   it.
3. Later, optionally, after the off-machine copy, a full destroy with the bucket and runner repository either
   retained or removed from state first (`terraform state rm`). The bucket and images stay; their cost is about
   $0.30/month.
4. Re-run `plan` and confirm no NAT, EIP, endpoint or compute resources remain.

**Not proposed:** deleting S3 objects, ECR images or the local tfstate, or changing bucket versioning or lifecycle.
