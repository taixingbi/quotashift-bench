#!/usr/bin/env bash
# Read-only Terraform plan for review. Makes read-only AWS API calls; creates nothing.
set -euo pipefail
exec "$(dirname "$0")/aws_ops.sh" plan "${1:?env (dev|research)}"
