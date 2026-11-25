#!/usr/bin/env bash
# Approval-gated AWS operations. NOTHING here runs automatically from tests or CI.
#   scripts/aws_ops.sh <plan|plan-destroy|deploy|healthcheck|start-gpu|stop-gpu|collect|destroy|cost-report|state-backup|run-stage> <dev|research> [stage args]
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
  deploy)      gate deploy                                                  # applies the REVIEWED plan file only
    # X1: refuse a plan without the $60 budget alarm (owner.auto.tfvars must set budget_alert_emails)
    $TF show -json "${ENVIRONMENT}.tfplan" | python3 -c 'import json,sys; rc=json.load(sys.stdin).get("resource_changes",[]); sys.exit(0 if any(r["type"]=="aws_budgets_budget" and r["change"]["actions"]!=["delete"] for r in rc) else 1)' \
      || { echo "REFUSED: the reviewed plan has no budget alarm (set budget_alert_emails in infra/terraform/owner.auto.tfvars)" >&2; exit 3; }
    $TF apply "${ENVIRONMENT}.tfplan" ;;
  start-gpu)   gate start-gpu
    aws autoscaling set-desired-capacity --auto-scaling-group-name "$(out gpu_asg_name)" --desired-capacity 1
    echo "Waiting for container instance..."; sleep 120
    aws ecs update-service --cluster "$(out cluster_name)" --service "$(out vllm_service_name)" --desired-count 1 >/dev/null
    GW="$(out gateway_service_name 2>/dev/null || true)"
    [[ -n "$GW" && "$GW" != "null" ]] && aws ecs update-service --cluster "$(out cluster_name)" --service "$GW" --desired-count 1 >/dev/null || true
    echo "GPU STARTED - billing is running. Stop with: scripts/aws_ops.sh stop-gpu ${ENVIRONMENT}" ;;
  stop-gpu)    # always allowed: reduces cost. Order: stop X1 runner tasks, then gateway/vLLM services, then the GPU ASG.
    for T in $(aws ecs list-tasks --cluster "$(out cluster_name)" --desired-status RUNNING --query 'taskArns' --output text 2>/dev/null || true); do
      [[ "$T" == "None" || -z "$T" ]] || aws ecs stop-task --cluster "$(out cluster_name)" --task "$T" --reason "stop-gpu" >/dev/null || true
    done
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
  state-backup) # read-only: copy the current remote state to the owner's local encrypted-backup folder (mode 600)
    D="${QUOTASHIFT_STATE_BACKUP_DIR:-$HOME/QuotaShift-backups/tfstate}"; mkdir -p "$D"; chmod 700 "$D"
    F="$D/${ENVIRONMENT}-$(date -u +%Y%m%dT%H%M%SZ).tfstate"
    $TF state pull > "$F"; chmod 600 "$F"; shasum -a 256 "$F" ;;
  run-stage)   # X1: one approved stage on the in-VPC runner (Fargate run-task); args after <env> go to the stage driver
    gate run-stage
    shift 2
    # dependencies: runner task definition exists (runner_image set) and exactly one vLLM task is RUNNING
    RF="$(out runner_task_definition_family 2>/dev/null || true)"
    [[ -n "$RF" && "$RF" != "null" ]] || { echo "REFUSED: no runner task definition (set runner_image, re-plan, deploy)" >&2; exit 3; }
    RUN="$(aws ecs describe-services --cluster "$(out cluster_name)" --services "$(out vllm_service_name)" --query 'services[0].runningCount' --output text)"
    [[ "$RUN" == "1" ]] || { echo "REFUSED: vLLM service runningCount=$RUN (start-gpu first; exactly one vLLM task)" >&2; exit 3; }
    [[ $# -gt 0 ]] || { echo "run-stage needs stage-driver arguments" >&2; exit 2; }
    # the per-stage approval token (x1_<calA|calB|main>_<g1m0|g1m1>) is forwarded to the in-VPC stage driver
    [[ "${QUOTASHIFT_STAGE_APPROVAL:-}" =~ ^x1_(calA|calB|main)_g1m[01]$ ]] \
      || { echo "REFUSED: set QUOTASHIFT_STAGE_APPROVAL=x1_<calA|calB|main>_<g1m0|g1m1> (owner approval for that stage)" >&2; exit 3; }
    OVR=$(python3 -c 'import json,os,sys; print(json.dumps({"containerOverrides":[{"name":"runner","command":["python","scripts/x1_stage.py",*sys.argv[1:]],"environment":[{"name":"QUOTASHIFT_APPROVED","value":os.environ["QUOTASHIFT_STAGE_APPROVAL"]}]}]}))' "$@")
    aws ecs run-task --cluster "$(out cluster_name)" --task-definition "$(out runner_task_definition_family)" --launch-type FARGATE \
      --network-configuration "awsvpcConfiguration={subnets=[$(out private_subnet_ids_csv)],securityGroups=[$(out runner_security_group_id)],assignPublicIp=DISABLED}" \
      --overrides "$OVR" --query 'tasks[0].taskArn' --output text ;;
  cost-report) # NOTE: each Cost Explorer API request is billed (~$0.01). Gated for that reason.
    gate cost-report
    aws ce get-cost-and-usage --time-period "Start=$(date -u -v-30d +%F 2>/dev/null || date -u -d '30 days ago' +%F),End=$(date -u +%F)" \
      --granularity DAILY --metrics UnblendedCost --filter '{"Tags":{"Key":"Project","Values":["QuotaShift"]}}' ;;
  *) echo "unknown action $ACTION" >&2; exit 2 ;;
esac
