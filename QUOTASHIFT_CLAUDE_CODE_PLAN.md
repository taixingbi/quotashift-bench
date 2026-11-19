# QuotaShift — Claude Code Implementation Plan

**Repository:** `quotashift-bench`  
**Research target:** Attack-only, reproducible **cross-tenant resource-interference simulation** for LLM serving.  
**Infrastructure:** AWS ECS + EC2 GPU + Fargate, Terraform, Python, vLLM.  
**Scope:** Research infrastructure and controlled workload generation in an owned, isolated AWS account/VPC.  
**Non-goals:** defenses, RL, GPU-aware scheduling, production threat hunting, external-target testing, quota evasion.

## 0. Instructions for Claude Code

Act as a senior AI systems engineer and research software engineer. Implement this repository in small, tested phases. Read this file first and track progress in `IMPLEMENTATION_STATUS.md` (completed, in progress, blocked). Prefer boring, reproducible infrastructure over complex abstractions.

**Important workflow:**
1. Inspect the repository and existing files; preserve user changes.
2. Produce a short implementation checklist mapped to the phases below.
3. Implement Phase 0 and Phase 1 first, including tests; then proceed sequentially when dependencies work.
4. Do not claim an AWS deployment succeeded without executing and recording verification.
5. **Do not execute `terraform apply`, launch GPU instances, incur cloud charges, or run load experiments without explicit approval.** `terraform fmt`, `terraform validate`, `pytest`, static checks, and a dry-run are permitted.
6. Avoid hardcoding AWS credentials, account numbers, tokens, or real tenant data.
7. If an AWS API, AMI parameter, ECS/vLLM flag, or model specification is uncertain, check up-to-date official documentation instead of inventing it.
8. Pin dependencies and Docker image digests or version tags; record exact versions in run metadata.
9. Keep the serving backend and simulator private; never offer arbitrary user-provided public target URLs.

## 1. Research question and boundaries

**Question:** Under identical, authorized request/token budgets, can different temporal and request-shape distributions produce significantly different *cross-tenant* service degradation in an isolated, shared LLM serving system?

Benchmark only the *attack side*: workload synthesis, controlled replay, and reproducible characterization of cross-tenant impact. Observations serve to validate workload effects, not to evaluate defenses or introduce a new scheduler. No experiments against third-party APIs or production tenants.

Hypotheses to **test**, not assume:
- H1: Request-shape composition produces victim-impact differences even when attacker request/token budgets are matched.
- H2: Temporal sequence can matter beyond the same shuffled mixture of requests.
- H3: Some effects persist across random seeds, victim workload profiles, and repeated runs.

Do not describe routine overloading as a novel security finding without evidence of cross-tenant disparity and a well-defined attacker capability model.

## 2. Logical architecture

```text
 AWS account (owned by experimenter) / isolated VPC
 ┌────────────────────────────────────────────────────────────────────┐
 │ ECS Fargate scheduled/run tasks                                    │
 │  - benign-runner: fixed seeded virtual tenants                     │
 │  - scenario-runner: controlled synthetic resource-demand patterns  │
 │                             │                                      │
 │                             ▼                                      │
 │ internal-only tenant gateway (FastAPI, ECS Fargate service)        │
 │  - tenant identity, per-tenant accounting, experiment IDs          │
 │  - fixed authorized request/token budgets for comparability       │
 │                             │                                      │
 │                             ▼                                      │
 │ internal-only vLLM endpoint (ECS EC2 GPU, 1 instance initially)    │
 │  - Qwen2.5-7B-Instruct, pinned revision/image version              │
 │                             │                                      │
 │                   CloudWatch / optional vLLM metrics                │
 │                             │                                      │
 │                            S3                                      │
 │           manifests / events / metrics / summaries                 │
 └────────────────────────────────────────────────────────────────────┘
```

* ECS EC2 for the vLLM task with `resourceRequirements: [{"type":"GPU","value":"1"}]`, GPU-optimized ECS AMI.
* Fargate for CPU-only gateway and generators.
* Internal DNS (Cloud Map or internal ALB). No public inference/gateway listener. Restrict security groups to known task-to-task paths. Permit outbound model downloads only through explicit, documented means.
* One shared GPU / one shared vLLM backend for all virtual tenants; don't accidentally allocate a GPU per tenant.
* Keep workload generators outside inference task to avoid conflating CPU load with GPU contention.

## 3. Repository structure

```text
quotashift-bench/
├── CLAUDE.md
├── README.md
├── IMPLEMENTATION_STATUS.md
├── pyproject.toml
├── Makefile
├── .env.example
├── .gitignore
├── infra/
│   ├── bootstrap/               # optional Terraform state setup
│   └── terraform/
│       ├── versions.tf
│       ├── providers.tf
│       ├── variables.tf
│       ├── main.tf
│       ├── network.tf
│       ├── ecs.tf
│       ├── iam.tf
│       ├── logs.tf
│       ├── storage.tf
│       ├── outputs.tf
│       └── example.tfvars
├── gateway/
│   ├── Dockerfile
│   └── app/{main.py,models.py,identity.py,accounting.py,forwarder.py}
├── simulator/
│   ├── Dockerfile
│   └── quotashift/
│       ├── schema.py
│       ├── generator.py
│       ├── scheduler.py
│       ├── traffic.py
│       ├── clients.py
│       ├── recorder.py
│       ├── experiment.py
│       ├── validators.py
│       └── cli.py
├── experiments/
│   ├── smoke.yaml
│   ├── baseline.yaml
│   ├── burst.yaml
│   ├── prefill_heavy.yaml
│   ├── decode_heavy.yaml
│   ├── mixed.yaml
│   └── stateful_sequences.yaml
├── analysis/
│   ├── summarize.py
│   ├── compare.py
│   └── plot.py
├── scripts/
│   ├── check_prereqs.sh
│   ├── build_and_push.sh
│   ├── plan_infra.sh
│   ├── deploy.sh               # explicit confirmation required
│   ├── run_experiment.sh
│   ├── collect_results.sh
│   └── destroy.sh              # explicit confirmation required
├── tests/
│   ├── test_schemas.py
│   ├── test_scheduler.py
│   ├── test_budget.py
│   ├── test_replay.py
│   ├── test_gateway.py
│   ├── test_analysis.py
│   └── test_end_to_end_mock.py
└── docs/
    ├── architecture.md
    ├── threat_model.md
    ├── experiment_protocol.md
    ├── reproducibility.md
    └── aws_cost_controls.md
```

## 4. Phase-by-phase implementation

### Phase 0 — Repository scaffold and local mock

Deliver:
- Python 3.12 project with `uv` or pinned equivalent; `ruff`, `mypy`, `pytest`, `pydantic`, `PyYAML`, `httpx`, `pandas`, `pyarrow`.
- CLI (`quotashift validate`, `quotashift dry-run`, `quotashift run-local`, `quotashift summarize`).
- Strict scenario YAML schema validation with useful errors.
- Deterministic schedule generation from a fixed `seed` and run ID.
- In-memory fake OpenAI Chat Completions server for functional tests.
- JSONL event stream with request ID, tenant ID (synthetic), planned and actual timestamps, input/output token counts when known, response status, request duration, first-token latency when streaming is supported, and structured error.
- No cloud credentials needed for unit and mock integration tests.

Acceptance: `pytest`, `ruff check`, schema validation and deterministic replay tests pass. Identical seed/config produces identical *planned* schedule hashes.

### Phase 1 — Gateway and tenant-accounting semantics

Implement a small FastAPI gateway:
- Internal-only `/healthz`, `/v1/chat/completions`, `/metrics` (optional).
- Synthetic tenant IDs supplied via experiment-owned credentials, mapped to experiment ID and run ID; do not use real secrets in fixtures.
- Forward to private vLLM's OpenAI-compatible chat endpoint.
- Record tenant-level request counts and estimated/actual tokens for reporting.
- Fixed quotas for experimental equivalence; do not implement bypasses or defenses for comparison.
- Enforce allowlisted backend; reject unknown hosts and direct external URLs.
- Apply concurrency, duration, and request/token caps to all test traffic. Abort cleanly when hard limits are reached.

Unit tests: per-tenant attribution, denied unknown tenant, valid forwarding, hard budget cutoff, idempotent result record, and no access to external hosts.

### Phase 2 — Synthetic workload scenarios

Implement scenario classes as bounded, **in-lab** traffic demand profiles:

| ID | Scenario | Independent variables | Scientific comparison |
|----|----------|-----------------------|-----------------------|
| B0 | Benign-only baseline | tenant count, benign rate | Victim behavior with no competing tenant |
| A1 | Burst-shaped arrivals | temporal concentration, fixed totals | Same number of requests spread uniformly |
| A2 | Prefill-heavy | bounded input-context sizes | Matched total token budget, shorter inputs |
| A3 | Decode-heavy | bounded requested output length | Matched total token budget, shorter outputs |
| A4 | Mixed request shapes | mixture proportions | Equal-sized homogeneous workload |
| A5 | Stateful sequence | bounded phase order / dwell | Randomized-phase order with same mixture |

Do not include malicious prompt content: use deterministic synthetic benign prompts. Treat `max_tokens` as requested upper bound, not guaranteed actual generated tokens. Record both requested and actual token usage, and report budget discrepancies. Validate prompts against model context length.

Every scenario must declare:
- `scenario_id`, `run_id`, `seed`, `model`, `victim_tenants`, `competing_tenants`.
- durations, per-tenant hard request/token caps, max concurrent in-flight requests, per-request timeout, stop conditions.
- a shared budget class (e.g., total requests, input tokens, output token requests, wall-clock time) and explicit cap values.
- benign workload profile, comparison/control scenario, number of repetitions.

Schedules must be produced from explicit inputs and persisted before execution so any pattern can be replayed without a learning loop or external target selection.

### Phase 3 — AWS Terraform infrastructure

Use AWS provider and version constraints, avoiding unchecked latest defaults.

Create:
1. VPC with private subnets for tasks, security groups permitting only intended service paths, and required outbound routes. Clearly document NAT Gateway hourly/data costs or a VPC-endpoint alternative.
2. ECS cluster + capacity provider/Auto Scaling Group with one `g5.2xlarge` initially (variable). Use AWS-documented ECS GPU-optimized AMI and EC2 launch template userdata registering with correct cluster.
3. ECS task definition and service for `vllm/vllm-openai` with pinned tag/digest, `GPU=1`, conservative `max_model_len` (start 4096), configured model revision, bounded GPU memory utilization, health/readiness checks, appropriate shared-memory configuration, and explicit IAM roles. Verify flags against the pinned vLLM version.
4. Gateway task definition/service running Fargate, internal DNS to vLLM.
5. Fargate task definitions for short-lived benign/scenario workload generators; no always-on generators by default.
6. ECR repositories for custom Python images; S3 result bucket with encryption, lifecycle, block-public-access; CloudWatch log groups with defined retention.
7. IAM least privilege: task execution pulls images/logs, application tasks write to scoped S3 prefixes, deployment identity is separate. Never attach `AdministratorAccess` to tasks.
8. Outputs for cluster, private service discovery names, task definition ARNs, bucket name; do not output secret values.
9. Required tags: `Project=QuotaShift`, `Environment=research`, `Owner`, and `CostCenter` if available.

Preflight:
- `aws sts get-caller-identity` and region selection.
- `g5.2xlarge` regional availability / quota, AMI lookup, GPU driver compatibility, model download access, AWS pricing estimate, IAM permissions.
- Assert no public Gateway or LLM address.
- `terraform fmt -check`, `terraform validate`, `terraform plan` before approval for apply.

**Cloud cost stop conditions:** GPU ASG desired capacity defaults to 0 until deliberately enabled; require a positive `max_run_minutes`, user-provided spending limit and explicit deploy confirmation. Provide reliable teardown instructions and a `destroy` dry-run. Include NAT, storage, logs, public IP, and data transfer in cost assessment; do not invent prices.

### Phase 4 — Controlled integration experiment

Once the user explicitly approves AWS execution:
1. Provision infrastructure and confirm GPU instance joined ECS cluster and vLLM task started.
2. Confirm internal-only model endpoint health/readiness with a single small request.
3. Run `smoke.yaml`: two benign tenants + one competing tenant; small hard-coded bounded workload.
4. Confirm records in S3, task exit status, CloudWatch logs, and per-tenant attribution.
5. Run **one** baseline/control pair with the same seed and matched budgets; report *measured* vs requested tokens.
6. Terminate generator tasks and scale GPU to zero or destroy infra according to user instructions.

Keep all access within owned VPC and obey experiment caps. No internet-address targets, no adaptive quota bypass, no high-rate unbounded flood logic.

### Phase 5 — Attack-effect validation analysis

Only analyze whether workload patterns produced significant cross-tenant interference. No defense benchmark or optimization objective.

Primary outputs:
- **Victim degradation**: victim median/P95 TTFT and end-to-end latency ratio versus benign-only reference; separate successful and timed-out requests.
- **Attack success rate**: fraction of independently repeated runs crossing a *pre-registered* degradation threshold (configurable; never choose the threshold after seeing results).
- **Budget-normalized effect**: victim slowdown per measured competing workload tokens, with request-count-matched and token-matched views.
- **Reproducibility**: confidence intervals or bootstrap intervals across seeds/runs, plus full per-run manifests.

Guard against confounders:
- Warm-up vs cold-start separation.
- Lock model revision, vLLM version, max context length, hardware, service replica count, streaming mode, and benign arrival distribution.
- Compare identical schedule versus shuffled-phase controls; report schedule overlap, queueing and measured token usage.
- Record background CPU/GPU load where feasible, but don't turn it into a GPU scheduling study.
- Re-run each matched pair at least 5 times for initial exploration; increase repetitions based on variability rather than claiming statistical significance prematurely.

Produce `summary.csv`, `summary.md`, `figure_*.png`, full run manifest JSON, raw JSONL/Parquet, and a reproducibility section containing exact commands and hashes.

### Phase 6 — Optional paper-strengthening work

Do *after* the first complete controlled dataset:
- Compare another serving engine or vLLM version only if the central phenomenon is supported.
- Validate selected findings on a second GPU instance type if budget permits.
- Test whether temporal order matters after controlling for token composition and offered load.
- Document negative results; if effects disappear under matched budgets, explicitly report that rather than implying a new attack.

## 5. Scenario schema example

```yaml
schema_version: 1
scenario_id: a5_stateful_sequence
seed: 42
model: qwen2_5_7b
runtime_seconds: 180
victim_tenants: [victim_a, victim_b]
competing_tenants: [synthetic_competitor]
safety:
  require_private_endpoint: true
  allow_external_target: false
  max_total_requests: 150
  max_global_inflight: 4
  max_requests_per_tenant: 60
  max_input_tokens_per_request: 1024
  max_output_tokens_per_request: 256
  max_runtime_seconds: 240
  abort_on_budget_exhaustion: true
comparison:
  primary_control: shuffled_phase_order
  matched_request_budget: true
  matched_token_budget: true
  repetitions: 5
phases:
  - name: uniform
    duration_seconds: 60
    pattern: steady
    request_shape: short
  - name: prefill_heavy
    duration_seconds: 60
    pattern: steady
    request_shape: context_heavy
  - name: mixed
    duration_seconds: 60
    pattern: burst_bounded
    request_shape: mixed
```

These are deliberately low, configurable proof-of-function limits, **not a claim about attack effectiveness**. Account for the fact that actual output tokens may be lower than the requested cap. An internal experiment must fail closed if caps cannot be enforced.

## 6. Developer commands and UX

Provide working implementations and README examples for:

```bash
make install
make lint
make test
quotashift validate experiments/smoke.yaml
quotashift dry-run experiments/stateful_sequences.yaml
quotashift run-local experiments/smoke.yaml --mock
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform validate
terraform -chdir=infra/terraform plan -var-file=example.tfvars
# With separate explicit user approval: deploy / execute capped experiment
quotashift summarize --input results/ --output reports/
```

Expose CLI help, clear error messages, clean shutdown, and exit codes. Add `make clean-local`, but ensure it cannot delete S3 buckets or live cloud resources.

## 7. Acceptance criteria

- [ ] Clean checkout can run unit and mock E2E tests without AWS or GPU.
- [ ] YAML schema rejects unknown targets, nonprivate endpoints, invalid phase durations, and budget violations.
- [ ] Schedules generated with the same seed are identical and have stable SHA-256 hashes.
- [ ] Gateway labels every request with synthetic tenant and experiment ID, no cross-tenant misattribution.
- [ ] One ECS GPU backend is shared by all tenants; no unintended per-tenant services.
- [ ] All ECS model/gateway endpoints are private; SG access minimized.
- [ ] `terraform validate` succeeds and deployment is approval-gated.
- [ ] Smoke run writes well-formed manifests, raw events, and a summary to S3.
- [ ] A paired baseline/control experiment can be replayed and reproduced by seed.
- [ ] Failures and negative results are preserved, not filtered out of summaries.
- [ ] Repository includes cost controls and clean teardown instructions.
- [ ] The paper contribution remains attack simulation and characterization only.

## 8. First action for Claude Code

> Inspect the current directory. If there is no implementation, scaffold `quotashift-bench` using the structure above. Implement **Phase 0 and Phase 1 with unit tests and a fully local mock end-to-end example**, then prepare Terraform Phase 3 for review. Do not deploy AWS resources or start GPU instances without asking me. Summarize changed files, exact test commands, test results, and the next implementation step.

## Official technical references

- AWS ECS GPU task definitions: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/ecs-gpu.html
- AWS GPU container instance setup: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/gpu-launch.html
- ECS Fargate task definition parameters: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html
- vLLM Docker guide: https://docs.vllm.ai/en/stable/deployment/docker/
- vLLM Quickstart: https://docs.vllm.ai/en/stable/getting_started/quickstart/
- Claude Code Plan Mode: https://code.claude.com/docs/en/claude-code-on-the-web
