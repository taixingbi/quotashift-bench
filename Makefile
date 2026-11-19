# Zero-cost targets run locally. AWS targets that create/start/destroy resources are approval-gated in scripts/aws_ops.sh.
ENV ?= dev
SEED ?= 11
.PHONY: setup test test-all lint smoke smoke-http e0-mock tf-fmt tf-validate tf-test tf-plan deploy start-gpu stop-gpu healthcheck collect destroy cost-report compose-smoke

setup:          ; uv sync
test:           ; uv run pytest -q -m "not slow and not gpu"
test-all:       ; uv run pytest -q
lint:           ; uv run ruff check src tests
smoke:
	uv run python -m risksched.cli run --config configs/experiments/smoke.yaml --scheduler fcfs --seed $(SEED)
	uv run python -m risksched.cli run --config configs/experiments/smoke.yaml --scheduler static_quota --seed $(SEED)
smoke-http:     ; uv run python -m risksched.cli run --config configs/experiments/smoke_http.yaml --scheduler fcfs --seed $(SEED)
e0-mock:        ; uv run python -m risksched.cli profile --config configs/experiments/e0_smoke.yaml --seed $(SEED)
compose-smoke:  ; docker compose -f docker/compose.yaml up --build --abort-on-container-exit runner
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
