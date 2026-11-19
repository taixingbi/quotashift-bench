# Architecture Decision Records

Each record: context → decision → consequences for paper claims. Deviations from the master plan are
logged here.

## ADR-001 — Initial control point is gateway-level admission/dispatch (2026-11-18)
**Context.** A gateway can decide *whether* (admission), *when* and *in what order* requests are submitted to
vLLM, and can cancel them. It cannot reorder, preempt or size batches inside vLLM; once submitted, vLLM's own
scheduler (FCFS or `priority`) controls prefill/decode interleaving and KV preemption.
**Decision.** Milestones 0–3 implement a *GPU/KV-aware admission & dispatch controller*. The policy observes
only scraped engine metrics (`/metrics`), its own queue state, and request metadata.
**Consequences.** Paper must say "admission/dispatch controller", not "token-step scheduler". Claims about
per-token isolation require ADR-002 option B or C.

## ADR-002 — Options for future engine-level integration (deferred)
| Option | What | Pros | Cons / risk |
|---|---|---|---|
| A. Gateway-only (current) | Control submission + `max_inflight` + cancel | Engine-agnostic, zero fork, deployable on managed vLLM | Cannot fix intra-batch interference; limited by queue-depth control loop |
| B. vLLM `priority` hints | Gateway sets per-request `priority` with `--scheduling-policy priority` | No fork; uses engine preemption | Semantics version-dependent (verify on v0.33.0); coarse |
| C. Pinned scheduler plugin / minimal fork | Replace vLLM V1 scheduler policy hook in a pinned version | True iteration-level control | Maintenance, version lock-in, must show decisions affect engine and measure overhead |
Decision: start with A, evaluate B as a cheap ablation in M2; C only if E4 shows gateway-only cannot recover
isolation and the novelty audit leaves a gap that needs it.

## ADR-003 — Two execution drivers sharing one gateway/policy
**Decision.** (1) `runtime/sim.py`: deterministic virtual-time driver with an in-process mock engine
(`serving/engine_model.py`) — bit-identical runs for tests and CI. (2) `runtime/live.py`: asyncio real-time
driver over HTTP/SSE to any OpenAI-compatible server (local mock server or real vLLM). The same `Gateway` and
`SchedulerPolicy` objects run in both.
**Consequences.** Mock results validate *plumbing and accounting only*; mock coefficients are uncalibrated and
all mock artefacts are labelled `synthetic_backend=true` and watermarked. Never report mock numbers as findings.

## ADR-004 — Online/oracle separation in the schema
**Decision.** `Request` (online) contains only requested limits (`max_output_tokens`), never realized length.
Ground truth lives in `OracleInfo`, held by the trace and the mock engine. The gateway refuses policies with
`deployable=False`. The mock HTTP server receives realized length through a simulation-only header
(`x-mock-oracle-output-tokens`) attached by the *backend adapter* (not the policy), and only when the backend
kind is `mock*` (tested in `tests/invariants/test_no_leakage.py`).

## ADR-005 — Latency timestamps from one process clock
All request latencies are differences of `time.monotonic()` (live) or virtual time (sim) taken in the runner
process. Wall time is recorded separately for correlation. TTFT is user-facing (includes gateway queue);
`backend_ttft_ms` (sent → first token) is reported separately.

## ADR-006 — Token accounting units
Ledger reservations are planning upper bounds (`input + max_output_tokens`); they are released in full on
completion and *charged* tokens use realized output (from `usage.completion_tokens`). Borrowing (when enabled)
may only use globally free capacity — fixed after the invariant checker caught an over-commit bug (two
tenants borrowing the same idle headroom), see `tests/unit/test_ledger.py::test_borrow_only_free_capacity_regression`.

## ADR-007 — E0 prompts are random token IDs; prefix caching off by default
Exact prompt lengths with no tokenizer dependency, unique per request ⇒ no accidental prefix-cache hits
(equivalent in spirit to vLLM's `random` benchmark dataset). The vLLM launch adds `--no-enable-prefix-caching`.
Random-ID prompts are **not** semantic workloads; M2 needs public prompt datasets (licenses to audit).
`ignore_eos=true` in E0 grid so realized == requested; verified per cell (`realized_eq_requested_frac`).

## ADR-008 — Saturation throughput measured inside the arrival window
The first E0 mock run exposed that counting completions during the drain period makes "completed req/s" track
offered load even past saturation. `completed_rps` now counts completions with terminal time ≤ window end;
`completed_eventually_rps` is kept separately. The knee rule is provisional and stated in `summary.json`.

## ADR-009 — Infrastructure: ECS on EC2 (GPU) with host networking for vLLM; Fargate one-shot runner
- vLLM and DCGM exporter use `network_mode=host` on the GPU instance: awsvpc task ENIs on EC2 cannot have
  public IPs, which would break model download in the cheapest network mode. Ingress to 8000/9400 is limited
  to the runner security group; no internet CIDR ingress anywhere (asserted in `tests/plan_mock.tftest.hcl`).
- Default `network_mode=public_egress_only` (public subnet + zero-ingress SGs) is the cheapest secure option;
  `nat` and `endpoints` are selectable, with `endpoints` requiring S3-staged weights.
- Launch type EC2 with an ASG (min 0 / max 1 / desired 0) instead of a managed-scaling capacity provider, so
  no GPU starts implicitly. Start/stop via approval-gated scripts; Terraform ignores desired-count drift.
- No Cloud Map / Container Insights / always-on Prometheus (cost). Runner scrapes `/metrics` itself.
- Deviation from plan: no managed capacity provider; no dedicated ECR mirror of the vLLM image (Docker Hub
  pull by digest). Revisit if Docker Hub rate limits bite.

## ADR-010 — Pins chosen on 2026-11-18
vLLM image `v0.33.0` (released 2026-11-02, ≥2 weeks old) by digest, not the 2-day-old v0.34.0. Python 3.11,
Terraform AWS provider 6.73.0 (exact). Qwen3 revisions = HF `main` SHAs on that date. **None verified on a
GPU yet**; CUDA/driver compatibility of the v0.33.0 image with the ECS GPU AMI driver is an open item.

## ADR-011 — Research pivot: security (resource-exhaustion defense), infrastructure unchanged (2026-11-18)
**Context.** The SLO-risk-scheduling framing overlaps heavily with JITServe, FairInference, Equinox, DRO-KV
(NOVELTY_MATRIX §3). The owner asked to move to a security framing while keeping the multi-tenant infrastructure.
Prior art shows **attacks** on serving resources are established (Engorgio, OverThink, *Rethinking Latency DoS*
"Fill & Squeeze"), while evaluated **defenses** for a shared engine are thin (overprovisioning; prefix-cache-only
accounting in PrefixShield; practitioner KV-threshold admission; OWASP-style quotas).
**Decision.** Primary topic: *tenant-isolating defense against resource-exhaustion (latency-DoS and
denial-of-wallet) attacks on a shared, unmodified vLLM engine*, evaluated against adaptive attackers.
Threat model: `docs/THREAT_MODEL.md`. All M0/M1 infrastructure (gateway, ledger, event accounting, mock/live
drivers, E0 harness, Terraform) is reused unchanged; E0 is still required (capacity, knee, KV limits).
**Consequences.** New work items: attack workload generators (T1–T6), defense policies via `SchedulerPolicy`,
security metrics (amplification factor, false-positive throttling). Baselines become: no defense (vLLM FCFS),
static token/rate quotas (OWASP), per-request caps, KV-utilization admission threshold, VTC-style fairness,
overprovisioning reference. Target venue to decide: MLSys (systems defense) vs a security venue
(USENIX Security / CCS / NDSS) — changes evaluation emphasis (adaptive attacks, threat model rigor).
