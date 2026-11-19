#!/usr/bin/env bash
# Tear everything down. Pass --dry-run for a read-only preview (plan -destroy).
# Approval-gated (QUOTASHIFT_APPROVED=destroy + interactive yes) for the real destroy.
set -euo pipefail
ENVIRONMENT="${1:?env (dev|research)}"
if [[ "${2:-}" == "--dry-run" ]]; then exec "$(dirname "$0")/aws_ops.sh" plan-destroy "$ENVIRONMENT"; fi
exec "$(dirname "$0")/aws_ops.sh" destroy "$ENVIRONMENT"
