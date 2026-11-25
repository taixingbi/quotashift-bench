#!/usr/bin/env bash
# Offline Terraform tests on a CLEAN copy of the module: local, git-ignored deployment files (*.auto.tfvars with the
# owner's budget email and the pinned runner image, backend.hcl, plans, state) are auto-loaded by `terraform test` and
# would change the defaults the tests assert. Mock provider only: no credentials, no API calls.
set -euo pipefail
cd "$(dirname "$0")/.."
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/infra" "$T/scripts"
rsync -a --exclude .terraform --exclude '*.auto.tfvars' --exclude backend.hcl --exclude '*.tfplan' --exclude local-state \
  --exclude '*.tfstate*' infra/terraform "$T/infra/"
cp scripts/x1_host_sampler.py scripts/x2_host_snapshot.py "$T/scripts/"
cd "$T/infra/terraform" && terraform init -backend=false -input=false >/dev/null && terraform test
