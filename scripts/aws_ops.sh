#!/usr/bin/env bash
# Approval-gated AWS operations. NOTHING here runs automatically from tests or CI.
#   scripts/aws_ops.sh <plan|plan-destroy|deploy|healthcheck|start-gpu|stop-gpu|collect|destroy|cost-report> <dev|research>
# Gated actions require BOTH env QUOTASHIFT_APPROVED=<action> and an interactive "yes".
set -euo pipefail
ACTION="${1:?action}"; ENVIRONMENT="${2:?env (dev|research)}"
TF="terraform -chdir=infra/terraform"
VARS="-var-file=envs/${ENVIRONMENT}.tfvars${QUOTASHIFT_MODEL:+ -var-file=envs/${ENVIRONMENT}.${QUOTASHIFT_MODEL}.tfvars}"   # X1: QUOTASHIFT_MODEL=m1-mistral

gate() {
  if [[ "${QUOTASHIFT_APPROVED:-}" != "$1" ]]; then
    echo "REFUSED: '$1' is approval-gated. Re-run with QUOTASHIFT_APPROVED=$1 after explicit approval." >&2; exit 3
  fi
  read -r -p "Type 'yes' to $1 in ${ENVIRONMENT} (account $(aws sts get-caller-identity --query Account --output text)): " ok
  [[ "$ok" == "yes" ]] || { echo "aborted"; exit 3; }
}
out() { $TF output -raw "$1"; }

# X1-B (least-privilege migration): never operate with the account ROOT user. `stop-gpu` stays allowed with any
# identity because it only reduces cost. The ARN is not printed (it contains the account id).
refuse_root() {
  local arn
  arn="$(aws sts get-caller-identity --query Arn --output text 2>/dev/null || true)"
  if [[ -z "$arn" ]]; then
    echo "REFUSED: cannot determine the AWS caller identity (configure the quotashift-x1 profile)." >&2; exit 3
  fi
  if [[ "$arn" == *":root" ]]; then
    echo "REFUSED: the active AWS credentials are the account ROOT user. Use the least-privilege, temporary-credential" \
         "profile from docs/X1_IAM_MIGRATION_CHECKLIST.md (e.g. AWS_PROFILE=quotashift-x1-operator)." >&2; exit 3
  fi
}
[[ "$ACTION" == "stop-gpu" ]] || refuse_root

case "$ACTION" in
  plan)        # read-only AWS API calls; no resources created
    $TF init -backend-config=backend.hcl -input=false
    $TF plan $VARS -out="${ENVIRONMENT}.tfplan" ;;
  plan-destroy) # read-only teardown preview; creates/destroys nothing
    $TF init -backend-config=backend.hcl -input=false
    $TF plan -destroy $VARS ;;
  deploy)      gate deploy; $TF apply "${ENVIRONMENT}.tfplan" ;;          # applies the REVIEWED plan file only
  start-gpu)   gate start-gpu
    aws autoscaling set-desired-capacity --auto-scaling-group-name "$(out gpu_asg_name)" --desired-capacity 1
    echo "Waiting for container instance..."; sleep 120
    aws ecs update-service --cluster "$(out cluster_name)" --service "$(out vllm_service_name)" --desired-count 1 >/dev/null
    GW="$(out gateway_service_name 2>/dev/null || true)"
    [[ -n "$GW" && "$GW" != "null" ]] && aws ecs update-service --cluster "$(out cluster_name)" --service "$GW" --desired-count 1 >/dev/null || true
    echo "GPU STARTED - billing is running. Stop with: scripts/aws_ops.sh stop-gpu ${ENVIRONMENT}" ;;
  stop-gpu)    # always allowed: reduces cost
    GW="$(out gateway_service_name 2>/dev/null || true)"
    [[ -n "$GW" && "$GW" != "null" ]] && aws ecs update-service --cluster "$(out cluster_name)" --service "$GW" --desired-count 0 >/dev/null || true
    aws ecs update-service --cluster "$(out cluster_name)" --service "$(out vllm_service_name)" --desired-count 0 >/dev/null || true
    aws autoscaling set-desired-capacity --auto-scaling-group-name "$(out gpu_asg_name)" --desired-capacity 0
    echo "GPU desired capacity set to 0." ;;
  healthcheck)
    aws ecs describe-services --cluster "$(out cluster_name)" --services "$(out vllm_service_name)" \
      --query 'services[0].{desired:desiredCount,running:runningCount,events:events[0:3].message}'
    aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$(out gpu_asg_name)" \
      --query 'AutoScalingGroups[0].{desired:DesiredCapacity,instances:Instances[].{id:InstanceId,state:LifecycleState}}' ;;
  collect)     mkdir -p results/aws; aws s3 sync "s3://$(out results_bucket)/results/" results/aws/ ;;
  destroy)     gate destroy; $TF destroy $VARS ;;
  cost-report) # NOTE: each Cost Explorer API request is billed (~$0.01). Gated for that reason.
    gate cost-report
    aws ce get-cost-and-usage --time-period "Start=$(date -u -v-30d +%F 2>/dev/null || date -u -d '30 days ago' +%F),End=$(date -u +%F)" \
      --granularity DAILY --metrics UnblendedCost --filter '{"Tags":{"Key":"Project","Values":["QuotaShift"]}}' ;;
  *) echo "unknown action $ACTION" >&2; exit 2 ;;
esac
