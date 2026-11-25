#!/usr/bin/env bash
# READ-ONLY preflight before requesting apply approval. No resources created or modified.
# Verifies identity (refuses ROOT), G/VT vCPU quota, g6.xlarge availability (X1 G1), and the ECS GPU AMI.
set -euo pipefail
REGION="${AWS_REGION:-us-east-1}"
echo "== caller identity (expect a least-privilege IAM identity, NOT root keys) =="
ARN="$(aws sts get-caller-identity --query Arn --output text)"
if [[ "$ARN" == *":root" ]]; then echo "FAIL: credentials are the account ROOT user; see docs/X1_IAM_MIGRATION_CHECKLIST.md" >&2; exit 3; fi
echo "caller is not root: ${ARN##*:}"
echo "== Running On-Demand G and VT instances vCPU quota (L-DB2E81BA); g6.xlarge needs 4 (X1: no increase requested) =="
aws service-quotas get-service-quota --service-code ec2 --quota-code L-DB2E81BA --region "$REGION" \
  --query 'Quota.Value' --output text || echo "quota lookup failed (check permissions)"
echo "== g6.xlarge offerings in $REGION =="
aws ec2 describe-instance-type-offerings --location-type availability-zone \
  --filters Name=instance-type,Values=g6.xlarge --region "$REGION" \
  --query 'InstanceTypeOfferings[].Location' --output text
echo "== ECS GPU-optimized AMI (SSM recommended) =="
aws ssm get-parameter --name /aws/service/ecs/optimized-ami/amazon-linux-2023/gpu/recommended/image_id \
  --region "$REGION" --query 'Parameter.Value' --output text
echo "Preflight complete. Pin gpu_ami_id, confirm price, then: scripts/plan_infra.sh <env>"
