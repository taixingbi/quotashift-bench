# Zero-cost targets run locally. AWS targets that create/start/destroy resources are approval-gated in scripts/aws_ops.sh.
ENV ?= dev
SEED ?= 11
.PHONY: setup test test-all lint typecheck validate dry-run run-local summarize tf-fmt tf-validate tf-test tf-plan deploy start-gpu stop-gpu healthcheck collect destroy cost-report

setup:          ; uv sync
test:           ; uv run pytest -q -m "not slow and not gpu"
test-all:       ; uv run pytest -q
lint:           ; uv run ruff check src tests scripts
typecheck:      ; uv run mypy src/quotashift
validate:       ; uv run quotashift validate experiments/smoke.yaml && uv run quotashift validate experiments/baseline.yaml && uv run quotashift validate experiments/stateful_sequences.yaml
dry-run:        ; uv run quotashift dry-run experiments/stateful_sequences.yaml
run-local:      ; uv run quotashift run-local experiments/smoke.yaml --mock
summarize:      ; uv run quotashift summarize --input results --output reports
tf-fmt:         ; terraform -chdir=infra/terraform fmt -check -recursive
tf-validate:    ; terraform -chdir=infra/terraform init -backend=false -input=false >/dev/null && terraform -chdir=infra/terraform validate
tf-test:        ; terraform -chdir=infra/terraform test      # mock provider: no credentials, no API calls
# --- touches AWS (read-only plan) / approval-gated below ---
tf-plan:        ; scripts/aws_ops.sh plan $(ENV)
deploy:         ; scripts/aws_ops.sh deploy $(ENV)
start-gpu:      ; scripts/aws_ops.sh start-gpu $(ENV)
stop-gpu:       ; scripts/aws_ops.sh stop-gpu $(ENV)
healthcheck:    ; scripts/aws_ops.sh healthcheck $(ENV)
collect:        ; scripts/aws_ops.sh collect $(ENV)
destroy:        ; scripts/aws_ops.sh destroy $(ENV)
cost-report:    ; scripts/aws_ops.sh cost-report $(ENV)
