#!/usr/bin/env bash
# Apply the REVIEWED plan file. Approval-gated (QUOTASHIFT_APPROVED=deploy + interactive yes).
set -euo pipefail
exec "$(dirname "$0")/aws_ops.sh" deploy "${1:?env (dev|research)}"
