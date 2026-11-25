# X1-B: least-privilege, temporary-credential IAM migration checklist

**Status:** prepared 2026-11-24 for owner execution. **Nothing has been created, deactivated or rotated.**
- Every step marked ⚠️ changes the AWS account. The **owner** performs it, after explicit confirmation, normally in the console with MFA.
- The repository only provides policy drafts, verification commands and a guard in `scripts/aws_ops.sh`.

**Why.** P0 found that this workstation's AWS CLI credentials are the **account root user**: long-lived access keys
with unlimited rights. `docs/aws_cost_controls.md` forbids that.

**Target state:**
- No root access keys exist.
- Day-to-day CLI work uses **short-lived role credentials** (≤ 1 h by default), obtained after MFA.
- There are two roles:
  - `quotashift-x1-readonly`: P0-style lookups, `terraform plan`, healthcheck, collect;
  - `quotashift-x1-operator`: deploy, start/stop GPU, destroy; region us-east-1 only; EC2 instance type g6.xlarge only; Cost Explorer and quota-increase requests denied.

## Prepared in the repo (no AWS changes)

| File | Purpose |
|---|---|
| `infra/iam/x1-readonly-policy.json` | identity policy for the read-only role |
| `infra/iam/x1-operator-policy.json` | identity policy for the operator role |
| `infra/iam/x1-role-trust-policy.template.json` | role trust policy (IAM-role path, option B). Placeholders `<ACCOUNT_ID>` and `<OWNER_IAM_USER>`; requires MFA ≤ 1 h old |
| `scripts/aws_ops.sh` | **now refuses every action except `stop-gpu` when the caller is the root user.** `stop-gpu` stays allowed because it only reduces cost. The ARN is never printed |
| `scripts/check_prereqs.sh` | fails on root credentials; checks the g6.xlarge quota (4 vCPU) and offerings |

**Validation already done.** `aws accessanalyzer validate-policy` (read-only; creates nothing) returns **0 findings**
for both identity policies after one redundancy fix, and 0 for the trust template with dummy values. Unit tests:
`tests/unit/test_x1_iam.py`.

### Operator-policy guard rails (all tested)
- **Allow** only:
  - the resource types the Terraform stack manages (VPC, subnets, NAT, security groups, endpoints, launch template, ASG, ECS, service discovery, logs, ECR, the project's S3 buckets and budget);
  - in us-east-1.
- **Only g6.xlarge instances:**
  - `ec2:RunInstances` for instances requires `ec2:InstanceType = g6.xlarge` and the tag `Project=QuotaShift`;
  - an explicit **Deny** covers every other instance type.
- **IAM roles:** only `role/quotashift-*` and `instance-profile/quotashift-*`.
  - `iam:PassRole` only to `ecs-tasks` and `ec2`.
  - `AttachRolePolicy` only for the three AWS-managed ECS/SSM policies the stack uses.
- **Deny:**
  - Cost Explorer (`ce:*`);
  - quota-increase requests;
  - creating users, access keys or login profiles;
  - creating or versioning policies;
  - Organizations, account, SSO and identity-store changes;
  - spot, fleet, reserved-instance and savings-plan purchases;
  - any action outside us-east-1, except global services.
- **Expect one revision.** If `terraform plan` or `apply` under the operator role hits an AccessDenied for a needed read action, the policy is widened **by one named action at a time**, re-validated and recorded. It is never replaced with a wildcard.

## Checklist (owner executes; ⚠️ = account change; ✅ = read-only verification)

**A. Protect the root user first (console)**
1. ⚠️ Sign in as root with the password. Confirm that **MFA is enabled** on root (hardware or authenticator); enable it if not.
2. ✅ IAM → Security credentials (root): note how many **access keys** exist and their *last used* time. Record only the key-ID suffix, never the secret.

**B. Choose the temporary-credential mechanism**
- **Option A (recommended): IAM Identity Center.**
  1. ⚠️ Enable IAM Identity Center in us-east-1 (no charge).
  2. ⚠️ Create one user for the owner, with MFA.
  3. ⚠️ Create two permission sets, `QuotaShiftX1ReadOnly` and `QuotaShiftX1Operator`, with session durations of 4 h and 1 h. Attach the two JSON files as inline policies.
  4. ⚠️ Assign both sets to the owner's user on this account.
  5. Local configuration, no AWS change:

     ```
     aws configure sso --profile quotashift-x1-readonly
     aws configure sso --profile quotashift-x1-operator
     ```

     Credentials come from `aws sso login` and expire automatically.
- **Option B: IAM roles plus an MFA-only user.**
  1. ⚠️ Create the roles `quotashift-x1-readonly` and `quotashift-x1-operator`, with the trust template filled in and the two JSON policies inline. Set the operator's max session to 1 h.
  2. ⚠️ Create an IAM user for the owner whose only permission is `sts:AssumeRole` on those two roles, with MFA.
  3. Local configuration: profiles with `role_arn` + `mfa_serial` + `source_profile`, so the CLI asks for an MFA code and receives temporary credentials.
  
  Option B still needs one long-lived access key on that limited user, which is why A is preferred.

**C. Verify the new identity before touching root keys** (all ✅, read-only)
1. Run:

   ```
   AWS_PROFILE=quotashift-x1-readonly aws sts get-caller-identity --query Arn --output text
   ```

   Expect `…assumed-role/…QuotaShiftX1ReadOnly…` or `…assumed-role/quotashift-x1-readonly/…`, and **not** `:root`.
2. Re-run the P0 reads under the read-only profile:

   ```
   AWS_PROFILE=quotashift-x1-readonly scripts/check_prereqs.sh
   ```

   This covers quota, g6.xlarge offerings and the AMI. Also run the Price List query from `docs/X1_P0_REPORT.md` §3.
3. Confirm the deny rules with the read-only IAM policy simulator, never with live calls. Cost Explorer requests can be billed, so don't probe them live:
   - `aws iam simulate-principal-policy --policy-source-arn <readonly role ARN> --action-names ce:GetCostAndUsage` → `explicitDeny`;
   - and for the operator role:

     ```
     aws iam simulate-principal-policy --policy-source-arn <operator role ARN> \
       --action-names ec2:RunInstances --context-entries Key=ec2:InstanceType,Values=g5.2xlarge,Type=string
     ```

     → `explicitDeny`. Repeat with `g6.xlarge` and the tag `Project=QuotaShift` → `allowed`.
4. Confirm the repo guard: `scripts/aws_ops.sh healthcheck research` with the **default (root)** profile → `REFUSED … ROOT`. With `AWS_PROFILE=quotashift-x1-readonly` → passes the identity check. It may still fail because nothing is deployed, which is expected.

**D. Retire the root access keys** (⚠️, owner only, after C fully passes)
1. ⚠️ **Deactivate**, do not delete, each root access key.
2. Remove the root key from `~/.aws/credentials` and `~/.aws/config`. Keep a dated note of the removal, not the secret.
3. Run normal read-only work for **≥ 7 days**, or until the next X1 stage, using only the new profiles.
4. ⚠️ **Delete** the deactivated root keys.
5. ✅ IAM credential report, or root Security credentials: **0 root access keys**.

**E. Record**
1. Add a dated entry to `docs/DECISIONS.md` (ADR-X1-B): mechanism (A or B), role and permission-set names, session durations, completion date of C and D. Record no ARNs, account IDs or key IDs.
2. Set `AWS_PROFILE=quotashift-x1-operator` only for approval-gated stages (X1-J, X1-K, X1-N, X1-O). Use the read-only profile for everything else.

**Rollback.** Until D.4, re-activating the root key restores the old state. After D.4, root console access with MFA
remains for break-glass use. No QuotaShift step ever needs root.

**Not done by Claude:** creating Identity Center, users, roles or permission sets, and deactivating, rotating or deleting any key.
