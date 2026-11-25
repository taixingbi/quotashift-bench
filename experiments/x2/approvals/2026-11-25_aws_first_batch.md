# X2 AWS-first batch (owner authorization P2–P8, 2026-11-25): stage audit record

Tokens granted: `state_bootstrap`, `iam_x2_exec`, `build_image`, `push_image`, `deploy` (initial + runner-image update),
`start-gpu` (first boot + g1m0 qualification), `x2-inputs`, `run-stage`, `x2_qual_g1m0`. The budget-alert recipient was
supplied by the owner and is kept only in the git-ignored `infra/terraform/owner.auto.tfvars` (mode 600).

| Step | Time (EST) | Identity | Outcome |
|---|---|---|---|
| P1 owner/budget config | 12:16 | local | written by Claude at the owner's explicit instruction; git-ignored; the address is in no tracked file |
| P2 state bucket | 12:16–12:17 | operator role | plan = the reviewed 7 creates; applied; versioning Enabled, SSE AES256, public-access block 4 × true, TLS-only policy, tag Project=QuotaShift. Bootstrap state backed up (mode 600, ~/QuotaShift-backups/tfstate). Main stack re-initialised on the S3 backend (`use_lockfile`), state empty; local override archived, not deleted |
| P3 ECS Exec IAM | 12:18 | owner user | **BLOCKED.** The live operator inline policy equals the reviewed B1 copy (18 statements, no managed policies); the proposed policy differs only by `X2EcsExecIntoRunnerOnly`. `iam:PutRolePolicy` was **denied** to `quotashift-x1-owner` (least privilege), so nothing changed (live == B1, trust unchanged). Root credentials are excluded by the owner, so the change needs the owner |
| P4 Session Manager plugin | 12:19–12:21 | local | `brew install --cask` needs sudo (refused non-interactively). Installed user-space instead: the Homebrew-fetched pkg (cask SHA-256 checked), signed and notarized "Developer ID Installer: AMZN Mobile LLC (94KV3E626L)", expanded without installing; binary (team 94KV3E626L) copied to ~/.local/bin; `session-manager-plugin --version` 1.2.896.0 |
| P5 deploy | — | — | **not started**: the batch is sequential and P3 is unresolved; deploying now would start NAT billing (about $1.08/day) with qualification unable to run |
| P6 image build | 12:20–12:21 | local | `build_runner_image.sh build` (`build_image`) from clean commit `5103a70`, linux/amd64, tag `quotashift-runner:5103a7059325` (local only; **not pushed**: the project ECR is created by P5). In-image checks (no network): `pin_x2`, `pin_x1`, `pin_x1_amendment` match; `pin_v5` full check lists v5-pinned *test* files absent from the image by design (X2 verifies only the v5 modules it imports, and those match); uid 10001; git 2.39.5; /app/results, /app/reports, /app/experiments writable; no raw evidence, no results directories, no email; build provenance `5103a70…`, dirty=false; `x2_runner_entry` refuses outside the VPC (rc 3) |
| Stop | 12:22 | — | batch halted at P3. AWS resources in existence: the state bucket only (7 bucket-configuration resources); no GPU, NAT, ECS or ECR |
