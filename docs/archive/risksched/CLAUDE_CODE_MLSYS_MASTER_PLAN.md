# Claude Code Master Plan — GPU-Aware Multi-Tenant LLM Serving (Paper A)

You are the lead ML systems research engineer and reproducibility lead for a publication-oriented project.

**Working title:** RISK-Sched: Uncertainty-Calibrated, Tenant-Aware GPU Scheduling for LLM Serving

**Target:** MLSys main research track (next eligible cycle). This is an experimental research plan, not a claim of novelty or acceptance. Treat all performance improvements as hypotheses until measured.

**Scope:** This is **Paper A**, which focuses on GPU-observable self-hosted inference, not the previous work on hidden-capacity managed gateways and **not Paper B on Safe RL**. Do **not** implement PPO/GRPO/RL in this repository unless separately requested. The innovation must be scheduling/resource isolation under heterogeneous workloads and uncertain output length, not merely deploying ECS, adding TPM limits, or collecting GPU metrics.

## 0. Operating instructions for Claude Code

1. First inspect the repository, existing Terraform, containers, benchmarks, code licenses and docs. Reuse compatible code only when authorized; do not invent missing modules or report experiments that were not run.
2. Work incrementally. Begin with **Milestone 0 and Milestone 1 only**, deliver their acceptance evidence, then proceed to the next milestone upon my instruction. Within an authorized milestone, execute tests and fix issues autonomously.
3. Before creating AWS resources, show `terraform plan`, anticipated resources and a cost budget, then **request explicit deployment approval**. Never auto-apply, start EC2, run billable load tests, or destroy shared infrastructure. No production environment access.
4. Pin Python, PyTorch, CUDA, NVIDIA driver, vLLM, OS/AMI, Docker image digests, model revisions, tokenizer revisions, and Terraform providers. Verify actual compatibility in the environment rather than assuming a particular release works.
5. Record actual evidence. Never fabricate data, pass/fail results, confidence intervals, citations, or claims of statistical significance. All paper figures must be generated from saved raw results with provenance.
6. Use exclusively personal or explicitly authorized AWS accounts and public/independently generated workloads. Never copy JPMorgan internal code, traces, account information, credentials, policies, or architecture details.
7. Maintain `docs/DECISIONS.md`, `docs/KNOWN_LIMITATIONS.md`, `docs/IMPLEMENTATION_STATUS.md` and `docs/NOVELTY_MATRIX.md`. Log design deviations and what they imply for paper claims.
8. At each milestone, report actual files changed, executed commands, tests, evidence locations, costs/usage when applicable, blockers, and the exact next actions.

## 1. Research questions and scientific boundary

- **RQ1 (resource uncertainty):** Do unpredictable output lengths create measurable compute/KV-cache contention and SLO interference between tenants under realistic GPU serving conditions?
- **RQ2 (mechanism):** Can an uncertainty-calibrated, GPU/KV-aware tenant risk-budget scheduler improve offered-load SLO goodput and worst-tenant isolation over strong token-aware and SLO-aware baselines?
- **RQ3 (generalization):** Does it remain effective under unseen workload mixtures, output-length distribution shifts, and different GPUs/models?
- **RQ4 (cost):** What is the scheduling overhead, GPU utilization cost and fairness/throughput tradeoff?

The novelty claim is **tentative**: tenant-level allocation of SLO-violation risk jointly with GPU compute and KV pressure, with online calibration and unused-resource reclamation. Test whether prior work already provides these mechanisms and narrow or change the claim if necessary.

### Mandatory prior-art audit

Study and document method-level overlap, implementation availability, and fair comparison design for at least:
- VTC — *Fairness in Serving Large Language Models* (OSDI 2024), https://www.usenix.org/conference/osdi24/presentation/sheng
- JITServe — *SLO-aware LLM Serving with Imprecise Request Information* (NSDI 2026), https://www.usenix.org/conference/nsdi26/presentation/zhang-wei ; artifact https://github.com/UIUC-MLSys/JITServe
- Current vLLM FCFS and priority scheduling, scheduling limits, KV preemption, and production metrics, https://docs.vllm.ai/
- Additional closely related multi-tenant isolation, token prediction, risk-constrained scheduling, admission, and KV-aware works discovered during the audit.

Deliver a `NOVELTY_MATRIX.md` with each competing method, information used, granularity, scheduling decisions, performance objective, fairness model, supported workloads, and **specific difference** from the proposal. If no defensible gap remains, stop and recommend a narrower research question before coding the new method.

## 2. System architecture

Three virtual tenants initially, later 10 and 30. All share **one** GPU-backed vLLM engine and one loaded model. Tenant identity exists in the gateway/workload generator, **not** as separate AWS accounts, separate Bedrock models or separate GPUs.

```
Trace Replayer / Workload Generator (CPU)
             |
    Tenant A / B / C requests
             |
 Multi-Tenant Gateway (CPU, ECS Fargate or CPU ECS on EC2)
 - auth placeholder / tenant ID
 - per-tenant queue, deadlines, token accounting
 - admission and dispatch / plugin controller
 - request + stream telemetry
             |
  GPU-aware policy service (CPU, co-locate initially if simpler)
  - estimates output uncertainty, compute/KV pressure, tenant risk
             |
    vLLM Inference Task (ECS on EC2 GPU, one dedicated GPU)
    - continuous batching and KV cache
    - Qwen3 small/medium model
             |
 Prometheus-compatible metrics / event logs / S3 experiment artifacts
```

**Important claim boundary:** A gateway can control admission, waiting and request submission order, but cannot directly control per-token GPU scheduling already inside vLLM. If claiming true token-step scheduling, implement a verified vLLM scheduler integration or a minimal pinned-version fork, and demonstrate those decisions affect the engine. Otherwise call this a GPU-aware admission/dispatch controller. Do not pretend that `max_tokens`, global TPM, vLLM `max_num_batched_tokens`, `max_num_seqs`, or physical KV block reservations mean the same thing.

### Request schema

```
request_id, tenant_id, arrival_time, prompt_text_or_token_ids,
input_token_count, max_output_tokens, workload_class,
slo_type, ttft_deadline_ms, tpot_target_ms, e2e_deadline_ms,
priority_weight, seed, trace_id
```

Maintain schema versions and distinguish planned/requested limits from realized generated output length. Do not feed realized output length into deployable online policies. Oracle baselines may access it but must be explicitly marked non-deployable.

### Tenant profiles

- Tenant A: interactive chatbot, short prompt, TTFT/TPOT-sensitive, steady arrivals.
- Tenant B: RAG/doc AI, long prefill and varied output, moderate arrival rate.
- Tenant C: agent or batch, bursty arrival and long decode; noisy neighbor.

All traffic rates, prompt lengths, deadlines and weights are workload parameters **calibrated from E0**, not pre-assumed achievable. Use heterogeneous tenants and varied mixes; avoid assuming three tenants are equivalent to real security-isolated customers.

## 3. AWS infrastructure: Terraform-first and cost-contained

Create `infra/terraform/` with explicit `dev` and `research` variables or workspaces:

- VPC, minimal subnets, security groups restricted to required traffic; do not expose vLLM or metrics to the public Internet. Use SSM Session Manager rather than public SSH where possible.
- ECS cluster plus EC2 Auto Scaling group / capacity provider for **one dedicated NVIDIA GPU EC2 instance** to start (e.g., g6.xlarge L4 24GB, subject to Region availability, quotas and pricing verification). Use GPU-optimized ECS AMI and task `resourceRequirements: GPU=1`.
- GPU vLLM ECS service/task with fixed desired count=1. Disable autoscaling during controlled experiments.
- CPU Gateway (Fargate is permitted for CPU tasks; **Fargate does not host GPU tasks**) and CPU workload generator, with configurable private networking.
- ECR repositories (pin deployed image digests); least-privilege task and execution IAM roles; CloudWatch log groups with retention; S3 raw-results bucket with lifecycle rules and encryption.
- Metrics collector: simplest compatible Prometheus-compatible endpoint/storage for vLLM, node/GPU metrics and gateway metrics. Prefer ephemeral local/sidecar collection with periodic S3 export for initial studies; avoid costly always-on monitoring stacks.
- GPU state via DCGM exporter/NVIDIA utilities, and engine metrics via vLLM `/metrics`. Ensure policy sees only the intended online metrics; diagnostic/oracle-only fields are separated.
- Configurable optional private endpoints vs NAT. **Explicitly estimate NAT Gateway, public IPv4, EBS, S3, log ingestion, data-transfer and idle-GPU costs**; prefer cheaper secure alternatives when viable. No hardcoded pricing.
- Terraform state backend with safe isolation and state locking. Never commit secrets or state files. Tag all resources `Project=mlsys-gpu-scheduling`, `Owner`, `Environment`, `CostCenter` when appropriate.
- Scripts/Make targets for `plan`, `deploy` (approval-gated), `healthcheck`, `stop-gpu`, `start-gpu` (approval-gated), `collect`, `destroy` (approval-gated), and `cost-report`.
- AWS Budgets alert / cost monitoring as configurable, plus a `max_experiment_seconds`, request-count limit and capped generator concurrency. Budget alerts are not a hard spending cutoff: stop experiments and EC2 instances explicitly.
- GPU quotas, image-size constraints, model-download auth/license, EBS size and startup time must be preflight-checked.

Local Docker Compose development must work before any AWS deployment. GPU-dependent integration tests can run on authorized local NVIDIA hardware or in ECS.

## 4. Repository structure

```
.
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── uv.lock / compatible lockfile
├── Makefile
├── infra/terraform/
├── docker/
├── configs/
│   ├── models/
│   ├── tenants/
│   ├── infrastructure/
│   ├── schedulers/
│   └── experiments/e0.yaml ... e8.yaml
├── src/risksched/
│   ├── gateway/          # per-tenant queues, admission, dispatch
│   ├── workload/         # deterministic arrivals, replay and actual prompts
│   ├── serving/          # vLLM adapter and integration
│   ├── profiling/        # GPU/KV and model latency profiles
│   ├── predictors/       # output-length uncertainty and calibration
│   ├── schedulers/       # FCFS, static, adaptive, gpu heuristic, risk
│   ├── instrumentation/  # metrics, timestamps, request events
│   ├── evaluation/       # metrics and paired statistical tests
│   └── cli.py
├── baselines/            # pinned artifacts / integrations, license notes
├── tests/unit/
├── tests/integration/
├── tests/invariants/
├── scripts/
├── results/              # gitignored raw outputs, with reproducible summaries
└── docs/
    ├── EXPERIMENT_PROTOCOL.md
    ├── NOVELTY_MATRIX.md
    ├── METRIC_DEFINITIONS.md
    ├── ASSUMPTIONS.md
    ├── DECISIONS.md
    ├── KNOWN_LIMITATIONS.md
    ├── IMPLEMENTATION_STATUS.md
    └── REPRODUCIBILITY.md
```

## 5. Execution and measurements: be exact

All requests MUST have event records such as `offered`, `accepted`, `queued`, `sent_to_vllm`, `first_token`, `completed`, `rejected`, `timed_out`, `backend_error`, `cancelled`, with request/tenant/experiment IDs.

- Compute user-facing E2E latency and TTFT from consistent timing at the load generator/gateway; do not subtract monotonic clocks from different processes. Record synchronized wall times for correlation, plus per-process monotonic deltas for latency.
- Distinguish **gateway queue** vs **vLLM internal waiting** vs **prefill** vs **decode**.
- Capture generated token counts from output/usage when available, validate counting using pinned tokenizer, and record metadata for missing counts.
- Separate time-to-first-token (TTFT), inter-token latency (ITL), time per output token (TPOT), and full response latency. Do not claim they are interchangeable.
- Record GPU utilization, memory allocated, engine KV cache utilization, running/waiting requests, preemptions, prefix-cache hits, and batching throughput. Check metric names against the pinned version at runtime; do not hardcode nonexistent names.
- Primary metric: **SLO-compliant goodput in successful requests/second** (and offered-load success fraction), counting rejected, expired, failed and timed-out offered requests as unsuccessful. Secondary: weighted tenant-goodput, worst-tenant SLO attainment, fairness, P95/P99 TTFT, TPOT, E2E, cache preemptions, overhead, total output tokens/sec, GPU utilization.
- TTFT/TPOT SLOs should be calibrated in a feasible regime from E0, then fixed before main comparisons. An overloaded system cannot satisfy every offered request; report offered-load and rejection explicitly.
- Work-conserving, tenant fairness, non-starvation and weighted fairness metrics must be precisely defined. Jain's index should use appropriately normalized tenant service satisfaction, not incomparable raw throughput.
- At experiment end, account for unfinished requests by explicit timeout/terminal policy. Report excluded/cancelled requests.
- Prefix-cache and CUDA warmup effects must be controlled; declare whether caching is enabled and control repeated prompts to avoid accidental unfair cache advantages.
- Persist full config, seed, model/revision, tokenizer/revision, git SHA, image digest, instance, driver/CUDA/vLLM versions, GPU clocks/temperature info if available, wall-clock, error logs, and source dataset hash with every run.

## 6. Phased implementation and exact acceptance gates

### Milestone 0 — Codebase/novelty/infrastructure audit (no paid cloud resources)

1. Inspect current repo and code permissions. Map reusable gateway/loadtest code, metrics and Terraform.
2. Pin software stack, check ECS GPU prerequisites and public datasets/artifacts/licenses.
3. Write `docs/NOVELTY_MATRIX.md`, `docs/EXPERIMENT_PROTOCOL.md`, `docs/METRIC_DEFINITIONS.md`, and cost-aware Terraform proposal.
4. Decide initial approach: gateway-level admission/dispatch; write an explicit option/decision record for future vLLM Scheduler integration.
5. Implement deterministic mocked-backend smoke tests and schema validators to prove basic control loop feasibility.

**Gate:** architecture decision, reproducible local smoke, tests passing, no AWS charges; report unresolved prior-art overlaps.

### Milestone 1 — E0: model/GPU resource profiling platform

1. Start a local container version using a mocked provider; add a real vLLM adapter.
2. Provide one-model, one-GPU serving profile on local RTX 3090 when permitted and later ECS GPU L4; target Qwen3 1.7B for smoke then Qwen3 4B for primary experiments, subject to actual memory/context feasibility.
3. Sweep candidate prompt lengths 256/1k/4k/8k, requested outputs 128/512/1k/2k, concurrency 1/4/8/16/32/64. Skip/mark unsupported or OOM configurations; no invented datapoints.
4. Profile compute-bound, KV-pressure and saturation knee using real GPU measurements and multiple trials. Distinguish requested `max_tokens` from realized output.
5. Produce plots of throughput, TTFT, TPOT, KV cache use, queue, preemptions, and successful requests versus offered load.

**Gate:** repeatable E0 run; valid events/accounting; clear feasible workload and SLO calibration documented. Do not proceed if the platform cannot demonstrate controlled saturation.

### Milestone 2 — Phase 1: multi-tenant benchmark and classical baselines

1. Implement 3 logically separate virtual tenants (then 10/30), independent arrival processes, queues, SLOs, weights, token accounts, rate bursts and deadline misses; one shared GPU/vLLM.
2. Implement load generator with deterministic seeds, open-loop arrivals (primary), optional closed-loop sensitivity and realistic token-length distributions. Use actual legal, public prompt content or documented prompt templates; synthetic token lengths alone are a token-trace simulation, NOT faithful semantic inference replay.
3. Implement baseline controllers through identical interfaces:
   - vLLM FCFS, no gateway admission
   - vLLM priority scheduling, where supported
   - static global + per-tenant RPM/TPM token bucket
   - weighted fair queuing / deficit round robin
   - tuned GPU-aware heuristic (uses allowed metrics)
   - previous adaptive admission approach **only if independently reproducible and clearly distinguished from the old managed-gateway paper**
4. Run E2 load sweep, E3 heterogeneity and E4 noisy-neighbor with these baselines. Include per-tenant plots and detailed offered/rejected/served accounting.
5. Compare 3/10/30-tenant patterns and at least two independent workload seeds per smoke scenario. Do not present small smoke samples as inferential evidence.

**Gate:** measurable tenant interference in at least one realistic regime, stable baseline comparison, documented reasons for any negative result. Keep the baseline even if it is stronger than the proposed method.

### Milestone 3 — E1: uncertainty experiments and baseline predictor

1. Dataset split by trace/time/workload family before fitting any estimator; retain held-out test traces.
2. Compare input/requested-max-based reservation, a trained point predictor, a trained quantile predictor, an uncertainty-calibrated predictor, and **oracle true output length (upper bound only)**.
3. Calibrate P50/P90/P95 actual output-length coverage; report errors separately for prompt length, tenant, workload class, and distribution shift. Do not leak target completion lengths into predictor features.
4. Stress under real output-length variance plus controlled counterfactual miscalibration; report measured KV pressure, preemption, waste, SLO misses and calibration error.
5. Explicitly compare with JITServe's imprecise-information treatment, not just simplistic `max_tokens` reservation.

**Gate:** demonstrate a reproducible *remaining* gap after strong predictors and prior-art-aligned baselines. If none, stop method development and revise RQ.

### Milestone 4 — Phase 2: proposed RISK-Sched method

Implement a minimal, interpretable method in increments; keep each variant independent for ablation:

A. **GPU/KV resource estimator:** empirically profiled prefill/decode cost and KV growth; never equate GPU utilization alone with free capacity.

B. **Output uncertainty estimator:** calibrated probability or quantiles conditional on available request features; update online using observed token progress without looking ahead.

C. **Tenant SLO-risk budget:** per-tenant allowance for probability/volume of SLO misses, considering normalized tenant service debt and configured weights. Include a safe fall-back when prediction confidence is poor.

D. **Resource-aware dispatch/admission:** select among waiting requests based on expected goodput gain, feasible KV/compute footprint, remaining deadlines, fairness debt and risk budgets. Specify what is decided at gateway level and what, if anything, runs at token-step level inside vLLM.

E. **Work-conserving reclamation:** allow safe reallocation of unused budget; prevent starvation; verify decision overhead remains small relative to inference.

Do not overclaim probabilistic risk constraints as deterministic guarantees. Implement `RISK-Sched-lite` before any complex learned predictor. If token-step scheduling is required, pin and validate a separately packaged vLLM scheduler extension, compare it independently to gateway-only controls, and measure instrumentation cost.

**Gate:** no information leakage; safety/invariant tests pass; Full vs no-GPU-info vs no-risk-budget ablations function on real GPU; improvement relative to strong heuristic is tested, not assumed.

### Milestone 5 — Final MLSys experiment suite E0–E8

E0 **GPU profiling:** identify saturation knee, compute-bound, KV-bound, preemptions, and capacity across models/GPU.

E1 **Output-length uncertainty:** real predictors, oracle vs `max_tokens`, point vs calibrated quantile, coverage and shift.

E2 **Load sweep:** 0.5, 0.8, 1.0, 1.2, 1.5, 2.0 × calibrated saturation throughput. Report infeasible regimes separately.

E3 **Heterogeneous mixes:** chat-short, long-prompt RAG, decode-heavy agent, long-context; vary mixes and input/output lengths.

E4 **Noisy neighbor and fairness:** burst tenant C while tenants A/B remain steady; vary burst intensity/duration, tenant count and weights. Report worst-tenant as well as aggregate goodput and offered-load failures.

E5 **KV cache pressure:** sweep context and concurrency, measure vLLM preemptions/recompute and real KV-block occupancy; test both compute-bound and KV-bound operating points.

E6 **Distribution shift:** train/calibrate on one set of workload regimes and hold out longer outputs, new tenant mixes, burst frequencies and contexts; online update budget must be specified and charged to overhead.

E7 **Cross-model/cross-GPU:** development on RTX 3090 when convenient; main ECS L4 24GB with Qwen3 1.7B/4B; extended L40S 48GB with Qwen3 8B if available/budgeted. Try a distinct model family where feasible. Re-profile hardware-specific cost without retuning on the final test set.

E8 **Ablation and system overhead:** Full / no-GPU-awareness / no-uncertainty / no-risk-budget / no-online-calibration / fixed-quantile / no-resource-reclamation; record policy decision P50/P99, CPU, memory, throughput lost to controller, GPU utilization, statistical uncertainty.

Add a **robustness check** for tracing/metrics failures and mismatched estimator confidence. This is an ablation/sensitivity, not a separate paper claim unless significant.

## 7. Strong baselines, independent reproductions, fairness of comparison

Mandatory: native vLLM FCFS, native priority, static per-tenant tokens, weighted fairness, tuned GPU-aware heuristic, and the proposed method.

Strong external baselines, as available and compatible:
- VTC (OSDI 2024): use the published artifact/licensing terms; record exact implementation/semantic equivalence and integration costs.
- JITServe (NSDI 2026): use its pinned vendored vLLM/integration; do **not** falsely claim an apples-to-apples head-to-head if runtime versions/metrics differ materially. If rebuilding the environment is required, run matching versions or clearly state compatibility limits and method differences.
- Other recent tenant fairness / KV-aware systems from the audited literature.

A prior system's artifact may need its own container/revision. Preserve exact dataset, GPU, model, SLO and trace whenever comparing, and label unavoidable implementation differences. Tune all methods using equal validation budget; keep held-out test settings fixed.

## 8. Experiments: rigor and failure criteria

- At least five independent repeats for final key real-GPU conditions (increase for unstable results). Pair methods by identical offered-demand trace, workload seeds and configuration; control run order and hardware warmup.
- Use bootstrap 95% confidence intervals at independent-run/trace level, not treat individual requests as independent experimental units. Report raw per-run results and paired effect sizes.
- Never remove slow, error, rejection or OOM runs silently. Failures become explicit rows, with root-cause notes. OOM is not a valid throughput measurement.
- Pre-register primary metric and key comparisons in `EXPERIMENT_PROTOCOL.md` before the final evaluation. Use separated tuning and test traces.
- Do not choose threshold/SLO solely to favor RISK-Sched. Show sensitivity over feasible targets and tenant weights.
- Distinguish a scheduler's real gain from external resource scaling or larger model quality. Keep number of GPU instances/tasks fixed per comparison.
- Report raw token counts and achieved GPU tokens/sec as well as SLO goodput, to expose policies that optimize request count by prioritizing only cheap work.
- The project is successful as a *scientific experiment* even if a strong baseline matches or outperforms RISK-Sched; do not manipulate workloads to conceal that outcome.

## 9. CLI and reproducible artifacts

Implement commands along these lines (adapt only if justified; keep documented parity):

```
python -m risksched.cli doctor
python -m risksched.cli validate-env
python -m risksched.cli generate-workload --config configs/tenants/three_tenants.yaml --seed 11
python -m risksched.cli profile --config configs/experiments/e0.yaml --backend mock
python -m risksched.cli run --config configs/experiments/e4.yaml --scheduler fcfs --seed 11
python -m risksched.cli run --config configs/experiments/e4.yaml --scheduler gpu_heuristic --seed 11
python -m risksched.cli run --config configs/experiments/e4.yaml --scheduler risk_sched --seed 11
python -m risksched.cli compare --experiment e4
python -m risksched.cli report --experiment e4
pytest -q
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform validate
terraform -chdir=infra/terraform plan
```

Output structure:

```
results/<experiment>/<timestamp>_<scheduler>_<seed>/
  manifest.json              # full provenance
  config.resolved.yaml
  requests.parquet            # request-level timestamps/terminal outcomes
  events.parquet
  metrics_timeseries.parquet
  metrics_summary.json
  logs/
  figures/
```

Figures must be automatically rebuilt from results, with no hand-edited result values. Every figure caption should state model, hardware, tenants, workload, runs and interval definition. Provide data/plots for unsuccessful or null-hypothesis experiments too.

## 10. Test suite and acceptance standards

Unit/invariant tests for:

- Nonnegative and conserved token budgets, correct units and token reservation/refund.
- Tenant isolation (a tenant cannot use another tenant's reserved capacity beyond the explicitly configured borrowing policy).
- Global budget accounting and max-output cap, without treating max-output as realized tokens.
- Queue/deadline/retry/cancel behavior, no duplicate completions, no starvation under specified feasible conditions.
- Correct offered-load denominator with rejected, expired and incomplete requests.
- Arrival trace determinism and independent seed handling.
- No oracle/future-output information fed to online policies.
- GPU/KV metric parsing and missing-data fallback for the pinned vLLM version.
- Prediction split, coverage and online calibration.
- Histogram percentile calculations and per-request latency origin consistency.
- Metric stream interruption and recovery, slow backend, OOM handling, stop-time cap.
- Terraform formatting/validation/security checks, image pinning and no public inference endpoint.

End-to-end smoke must be runnable with a mock vLLM service in CI at zero GPU cost. Real GPU tests must be explicitly marked and opt-in.

## 11. Paper deliverables and decision checkpoints

Produce:

- `docs/NOVELTY_MATRIX.md` and related-work evidence with real links.
- Versioned open-loop traces, deterministic tenant manifests, workloads, SLO definitions.
- System diagram clearly separating gateway admission and engine scheduler.
- Algorithm pseudocode, computational complexity, implementation overhead and correctness/invariant statements.
- E0–E8 raw run manifests, tables, 95% CIs, sensitivity and negative results.
- Main figures: (F1) microprofile/bottleneck; (F2) uncertainty degradation; (F3) offered-load goodput; (F4) noisy-neighbor worst-tenant SLO; (F5) KV preemptions; (F6) OOD shifts; (F7) cross-hardware; (F8) ablation/overhead.
- Reproducibility appendix and deployment/cleanup documentation.
- `docs/PAPER_OUTLINE.md` structured around *problem → why past solutions fail → new mechanism → implementation → rigorous evaluation → limits*.
- Research integrity and AI-assistance log appropriate to the target conference's current policies.

**Go/no-go checkpoint after E0/E1/E4:** If there is no robust and novel gap against JITServe/VTC/strong heuristics, document the negative evidence and pivot method design before adding large-scale AWS cost.

## 12. Immediate execution request

**Do only Milestone 0 and Milestone 1 now.** Inspect repository first; do not invent existing files. Deliver:

1. Repo audit and reusable assets inventory.
2. Architecture diagram/ADR; exact distinction between gateway-level control and vLLM internals.
3. Literature novelty matrix with verified references.
4. Terraform design and `terraform validate`/`plan` only, with no apply and no cost incurrence.
5. Implemented zero-cost mock backend, three-tenant schema, request event accounting and unit tests.
6. Local/authorized E0 profiling harness and documented model/driver constraints. If GPU isn't available, do not fabricate GPU results: provide commands and validated mock runs.
7. Exact test commands, results, failed tests, known limitations and estimated AWS resource usage.
8. A concise `PHASE_1_NEXT_STEPS.md` for the next Claude Code turn.

Work autonomously within that scope; ask only when blocked by an approval, credentials, destructive action, unavoidable missing design fact, or paid cloud action.
