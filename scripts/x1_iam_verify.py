"""X1 IAM verification against the LIVE roles (read-only: iam:SimulatePrincipalPolicy evaluates, never calls).

    uv run python scripts/x1_iam_verify.py            # needs credentials allowed to call iam:SimulatePrincipalPolicy

Two suites on the live role ARNs:
  guard rails   23 decisions (g6.xlarge / us-east-1 / Project tag only; Cost Explorer, quota, spot, access keys denied;
                no self-modification, no admin attach, no foreign role names; stack roles manageable)
  terraform     the create / modify / read actions the X1 Terraform plan and aws_ops.sh need (must all be allowed)
Account ids are never printed.
"""

from __future__ import annotations

import json
import subprocess
import sys

USE1 = {"aws:RequestedRegion": "us-east-1"}


def _acct() -> str:
    return subprocess.check_output(["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"],
                                   text=True).strip()


def sim(acct: str, role: str, action: str, res: str | None = None, ctx: dict | None = None) -> str:
    cmd = ["aws", "iam", "simulate-principal-policy", "--policy-source-arn", f"arn:aws:iam::{acct}:role/quotashift-x1-{role}",
           "--action-names", action, "--output", "json"]
    if res:
        cmd += ["--resource-arns", res.replace("ACCT", acct)]
    if ctx:
        cmd += ["--context-entries"] + [f"ContextKeyName={k},ContextKeyValues={v},ContextKeyType=string"
                                        for k, v in ctx.items()]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        return "ERROR " + r.stderr.strip().replace(acct, "<acct>")[:160]
    return json.loads(r.stdout)["EvaluationResults"][0]["EvalDecision"]


GUARD = [
    ("readonly", "ce:GetCostAndUsage", None, None, "explicitDeny"),
    ("readonly", "ec2:DescribeInstances", None, USE1, "allowed"),
    ("readonly", "ec2:DescribeInstances", None, {"aws:RequestedRegion": "us-west-2"}, "explicitDeny"),
    ("readonly", "ec2:RunInstances", None, USE1, "implicitDeny"),
    ("readonly", "iam:CreateAccessKey", None, None, "explicitDeny"),
    ("readonly", "pricing:GetProducts", None, USE1, "allowed"),
    ("operator", "ec2:RunInstances", "arn:aws:ec2:us-east-1:ACCT:instance/i-0",
     {"ec2:InstanceType": "g6.xlarge", "aws:RequestTag/Project": "QuotaShift", **USE1}, "allowed"),
    ("operator", "ec2:RunInstances", "arn:aws:ec2:us-east-1:ACCT:instance/i-0",
     {"ec2:InstanceType": "g5.2xlarge", "aws:RequestTag/Project": "QuotaShift", **USE1}, "explicitDeny"),
    ("operator", "ec2:RunInstances", "arn:aws:ec2:us-east-1:ACCT:instance/i-0",
     {"ec2:InstanceType": "g6.xlarge", "aws:RequestTag/Project": "Other", **USE1}, "implicitDeny"),
    ("operator", "ec2:RunInstances", "arn:aws:ec2:us-west-2:ACCT:instance/i-0",
     {"ec2:InstanceType": "g6.xlarge", "aws:RequestTag/Project": "QuotaShift", "aws:RequestedRegion": "us-west-2"},
     "explicitDeny"),
    ("operator", "autoscaling:SetDesiredCapacity", None, USE1, "allowed"),
    ("operator", "ce:GetCostAndUsage", None, None, "explicitDeny"),
    ("operator", "servicequotas:RequestServiceQuotaIncrease", None, USE1, "explicitDeny"),
    ("operator", "ec2:RequestSpotInstances", None, USE1, "explicitDeny"),
    ("operator", "iam:PutRolePolicy", "arn:aws:iam::ACCT:role/quotashift-x1-operator", None, "explicitDeny"),
    ("operator", "iam:PassRole", "arn:aws:iam::ACCT:role/quotashift-x1-operator",
     {"iam:PassedToService": "ec2.amazonaws.com"}, "explicitDeny"),
    ("operator", "iam:UpdateAssumeRolePolicy", "arn:aws:iam::ACCT:role/quotashift-x1-operator", None, "explicitDeny"),
    ("operator", "iam:PutRolePolicy", "arn:aws:iam::ACCT:role/quotashift-research-vllm-abc", None, "allowed"),
    ("operator", "iam:PassRole", "arn:aws:iam::ACCT:role/quotashift-research-exec-abc",
     {"iam:PassedToService": "ecs-tasks.amazonaws.com"}, "allowed"),
    ("operator", "iam:PassRole", "arn:aws:iam::ACCT:role/quotashift-research-exec-abc",
     {"iam:PassedToService": "lambda.amazonaws.com"}, "implicitDeny"),
    ("operator", "iam:CreateRole", "arn:aws:iam::ACCT:role/admin-backdoor", None, "implicitDeny"),
    ("operator", "iam:CreateAccessKey", None, None, "explicitDeny"),
    ("operator", "iam:AttachRolePolicy", "arn:aws:iam::ACCT:role/quotashift-research-vllm-abc",
     {"iam:PolicyARN": "arn:aws:iam::aws:policy/AdministratorAccess"}, "explicitDeny"),
]
TF_NEEDED = [
    *[(a, None, None) for a in (
        "ec2:CreateVpc", "ec2:CreateSubnet", "ec2:CreateInternetGateway", "ec2:AttachInternetGateway",
        "ec2:AllocateAddress", "ec2:CreateNatGateway", "ec2:CreateRouteTable", "ec2:CreateRoute",
        "ec2:AssociateRouteTable", "ec2:CreateSecurityGroup", "ec2:AuthorizeSecurityGroupIngress",
        "ec2:AuthorizeSecurityGroupEgress", "ec2:RevokeSecurityGroupEgress", "ec2:CreateVpcEndpoint",
        "ec2:CreateLaunchTemplate", "ec2:CreateTags", "ec2:DescribeVpcs", "ec2:DescribeInstances",
        "autoscaling:CreateAutoScalingGroup", "autoscaling:SetDesiredCapacity", "autoscaling:DescribeAutoScalingGroups",
        "ecs:CreateCluster", "ecs:RegisterTaskDefinition", "ecs:CreateService", "ecs:UpdateService", "ecs:RunTask",
        "ecs:StopTask", "ecs:DescribeTasks", "ecs:ListTasks", "ecs:DescribeServices", "logs:CreateLogGroup",
        "logs:PutRetentionPolicy", "logs:DescribeLogGroups", "ecr:CreateRepository", "ecr:PutLifecyclePolicy",
        "servicediscovery:CreatePrivateDnsNamespace", "servicediscovery:CreateService", "servicediscovery:GetNamespace",
        "route53:CreateHostedZone", "ssm:GetParameter", "sts:GetCallerIdentity")],
    ("iam:CreateRole", "arn:aws:iam::ACCT:role/quotashift-research-vllm-x", None),
    ("iam:GetRole", "arn:aws:iam::ACCT:role/quotashift-research-vllm-x", None),
    ("iam:PutRolePolicy", "arn:aws:iam::ACCT:role/quotashift-research-gpuhost-x", None),
    ("iam:AttachRolePolicy", "arn:aws:iam::ACCT:role/quotashift-research-gpuhost-x",
     {"iam:PolicyARN": "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"}),
    ("iam:CreateInstanceProfile", "arn:aws:iam::ACCT:instance-profile/quotashift-research-gpu", None),
    ("iam:AddRoleToInstanceProfile", "arn:aws:iam::ACCT:instance-profile/quotashift-research-gpu", None),
    ("iam:PassRole", "arn:aws:iam::ACCT:role/quotashift-research-gpuhost-x", {"iam:PassedToService": "ec2.amazonaws.com"}),
    ("iam:CreateServiceLinkedRole", None, {"iam:AWSServiceName": "ecs.amazonaws.com"}),
    ("s3:CreateBucket", "arn:aws:s3:::quotashift-research-results-abc", None),
    ("s3:PutBucketPublicAccessBlock", "arn:aws:s3:::quotashift-research-results-abc", None),
    ("s3:GetBucketAcl", "arn:aws:s3:::quotashift-research-results-abc", None),
    ("s3:PutObject", "arn:aws:s3:::quotashift-tfstate-a1b2c3d4/quotashift/research/terraform.tfstate", None),
    ("budgets:ModifyBudget", "arn:aws:budgets::ACCT:budget/quotashift-research-monthly", None),
]


def main() -> int:
    acct = _acct()
    g_ok = 0
    for role, act, res, ctx, exp in GUARD:
        got = sim(acct, role, act, res, ctx)
        g_ok += got == exp
        if got != exp:
            print(f"GUARD MISMATCH {role} {act}: {got} (expected {exp})")
    t_ok = 0
    for act, res, ctx in TF_NEEDED:
        got = sim(acct, "operator", act, res, {**USE1, **(ctx or {})})
        t_ok += got == "allowed"
        if got != "allowed":
            print(f"TERRAFORM NEED NOT ALLOWED {act}: {got}")
    print(f"guard rails {g_ok}/{len(GUARD)} as expected; terraform/aws_ops needs {t_ok}/{len(TF_NEEDED)} allowed")
    return 0 if g_ok == len(GUARD) and t_ok == len(TF_NEEDED) else 1


if __name__ == "__main__":
    sys.exit(main())
