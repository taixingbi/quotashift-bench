#!/usr/bin/env bash
# READ-ONLY preflight before requesting apply approval. No resources created or modified.
# Verifies identity, G/VT vCPU quota, g5.2xlarge availability, and the ECS GPU AMI.
set -euo pipefail
REGION="${AWS_REGION:-us-east-1}"
echo "== caller identity (expect a least-privilege IAM identity, NOT root keys) =="
aws sts get-caller-identity
echo "== Running On-Demand G and VT instances vCPU quota (L-DB2E81BA); g5.2xlarge needs 8 =="
aws service-quotas get-service-quota --service-code ec2 --quota-code L-DB2E81BA --region "$REGION" \
  --query 'Quota.Value' --output text || echo "quota lookup failed (check permissions)"
echo "== g5.2xlarge offerings in $REGION =="
aws ec2 describe-instance-type-offerings --location-type availability-zone \
  --filters Name=instance-type,Values=g5.2xlarge --region "$REGION" \
  --query 'InstanceTypeOfferings[].Location' --output text
echo "== ECS GPU-optimized AMI (SSM recommended) =="
aws ssm get-parameter --name /aws/service/ecs/optimized-ami/amazon-linux-2023/gpu/recommended/image_id \
  --region "$REGION" --query 'Parameter.Value' --output text
echo "Preflight complete. Pin gpu_ami_id, confirm price, then: scripts/plan_infra.sh <env>"
