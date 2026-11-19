#!/usr/bin/env bash
# Approval-gated AWS operations. NOTHING here runs automatically from tests or CI.
#   scripts/aws_ops.sh <plan|deploy|healthcheck|start-gpu|stop-gpu|collect|destroy|cost-report> <dev|research>
# Gated actions require BOTH env QUOTASHIFT_APPROVED=<action> and an interactive "yes".
set -euo pipefail
ACTION="${1:?action}"; ENVIRONMENT="${2:?env (dev|research)}"
TF="terraform -chdir=infra/terraform"
VARS="-var-file=envs/${ENVIRONMENT}.tfvars"

gate() {
  if [[ "${QUOTASHIFT_APPROVED:-}" != "$1" ]]; then
    echo "REFUSED: '$1' is approval-gated. Re-run with QUOTASHIFT_APPROVED=$1 after explicit approval." >&2; exit 3
  fi
  read -r -p "Type 'yes' to $1 in ${ENVIRONMENT} (account $(aws sts get-caller-identity --query Account --output text)): " ok
  [[ "$ok" == "yes" ]] || { echo "aborted"; exit 3; }
}
out() { $TF output -raw "$1"; }

case "$ACTION" in
  plan)        # read-only AWS API calls; no resources created
    $TF init -backend-config=backend.hcl -input=false
    $TF plan $VARS -out="${ENVIRONMENT}.tfplan" ;;
  deploy)      gate deploy; $TF apply "${ENVIRONMENT}.tfplan" ;;          # applies the REVIEWED plan file only
  start-gpu)   gate start-gpu
    aws autoscaling set-desired-capacity --auto-scaling-group-name "$(out gpu_asg_name)" --desired-capacity 1
    echo "Waiting for container instance..."; sleep 120
    aws ecs update-service --cluster "$(out cluster_name)" --service "$(out vllm_service_name)" --desired-count 1 >/dev/null
    echo "GPU STARTED - billing is running. Stop with: scripts/aws_ops.sh stop-gpu ${ENVIRONMENT}" ;;
  stop-gpu)    # always allowed: reduces cost
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
      --granularity DAILY --metrics UnblendedCost --filter '{"Tags":{"Key":"Project","Values":["mlsys-gpu-scheduling"]}}' ;;
  *) echo "unknown action $ACTION" >&2; exit 2 ;;
esac
