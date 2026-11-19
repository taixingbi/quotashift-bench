# Architecture (Milestone 0/1)

## Control boundary

```
 ┌───────────────────────── runner process (single monotonic clock) ─────────────────────────┐
 │  Workload client                    Gateway (gateway/core.py)                              │
 │  - OpenLoopClient (trace replay)    - per-tenant FIFO queues                               │
 │  - ClosedLoopClient (E0 grid)  ───► - admission  ──► policy.admit(req, view)               │
 │  trace = Request + OracleInfo       - dispatch   ──► policy.select(view) -> request ids    │
 │        │ (oracle kept here,         - TokenLedger (reservations, refunds, borrowing)       │
 │        │  never in the view)        - RunRecorder (event state machine, request rows)      │
 │        │                                   │ submit / cancel           ▲ scraped metrics   │
 └────────┼───────────────────────────────────┼───────────────────────────┼───────────────────┘
          │ sim-only ground truth             │ HTTP /v1/completions (SSE) │ GET /metrics
          ▼                                   ▼                           │
   ┌──────────────── engine (NOT controlled by the gateway) ──────────────┴──────────────────┐
   │ vLLM (real, pinned) or mock: continuous batching, chunked prefill, paged KV blocks,       │
   │ FCFS/priority waiting queue, recompute preemption, per-iteration token budget             │
   └───────────────────────────────────────────────────────────────────────────────────────────┘
```

**Gateway decides:** accept/reject, how long a request waits in the gateway, submission order and time,
per-tenant in-flight and token-reservation caps, cancellation on timeout/cutoff.
**Engine decides (not us):** which submitted requests are in each iteration's batch, prefill chunking,
decode interleaving, which running request is preempted when KV blocks run out.
The gateway influences the engine only indirectly through *how many and which* requests are in flight.

## Drivers (ADR-003)

| Driver | Clock | Backend | Use |
|---|---|---|---|
| `runtime/sim.py` | virtual | in-process `EngineModel` | deterministic tests, CI, fast E0 harness validation |
| `runtime/live.py` | `time.monotonic()` | `OpenAICompatBackend` → mock server or vLLM | HTTP/SSE path, real GPU E0, later E2–E8 |

In both, backend metrics reach the policy only as a periodically refreshed `BackendObservation` (sim:
every `metrics_interval_s` of virtual time; live: Prometheus scrape), so policies see realistically stale data.

## Request lifecycle (enforced by `instrumentation/recorder.py`)

```
offered ─► accepted ─► queued ─► sent_to_vllm ─► first_token ─► completed
   └─► rejected          ├─► timed_out (gateway_queue_timeout)   ├─► timed_out (client_e2e_timeout)
                         └─► cancelled (run_cutoff)              ├─► backend_error
                                                                 └─► cancelled (run_cutoff)
```
Exactly one terminal event per offered request; illegal transitions raise in strict mode; events are
re-validated offline by `risksched.cli report`.

## Module map

| Path | Role |
|---|---|
| `schema.py` | Versioned `Request`, `OracleInfo`, tenant/workload config, `RequestEvent` |
| `workload/generator.py` | Per-tenant independent seeded arrivals (Poisson / Gamma / ON-OFF), lengths, synthetic prompts, trace hash |
| `gateway/core.py`, `gateway/ledger.py` | Queues, admission/dispatch plumbing, token ledger |
| `schedulers/base.py`, `schedulers/simple.py` | Policy interface; `fcfs` (pass-through), `static_quota` (M0 infrastructure policy) |
| `serving/engine_model.py` | Deterministic mock engine (uncalibrated) |
| `serving/mock_server.py` | Mock vLLM HTTP server (OpenAI completions + SSE, `/metrics`, `/tokenize`) |
| `serving/openai_backend.py` | Streaming adapter for vLLM / mock; usage-based token counts |
| `instrumentation/prom.py` | Prometheus parsing; vLLM metric-name candidates resolved at runtime |
| `instrumentation/gpu.py` | Optional `nvidia-smi` sampler (no values fabricated when absent) |
| `instrumentation/provenance.py` | Manifest: git, packages, platform, GPU, config hash, trace hash |
| `evaluation/metrics.py` | TTFT/TPOT/E2E, SLO accounting, goodput, Jain, histogram quantiles |
| `evaluation/plots.py` | Figures from saved results, captions, mock watermark |
| `profiling/e0.py` | E0 grid + rate sweep harness |
| `runtime/runner.py` | Experiment orchestration and results layout |
| `cli.py` | `doctor`, `validate-env`, `generate-workload`, `run`, `profile`, `report`, `compare`, `mock-server` |

## AWS deployment shape (proposed, not deployed)

```
VPC (1 AZ) ── public subnet (default mode; zero-ingress SGs)
  ├── ECS cluster
  │    ├── ASG (min 0 / max 1 / desired 0): g6.xlarge (1x L4 24 GB), ECS GPU AMI (AL2023), IMDSv2, encrypted gp3
  │    │     ├── service vllm  (host net, GPU=1, desired 0)  :8000 ◄── runner SG only
  │    │     └── daemon  dcgm-exporter (host net)            :9400 ◄── runner SG only
  │    └── task def runner (Fargate, one-shot run-task; created only when a digest-pinned image is given)
  ├── S3 gateway endpoint (free) ── S3 results bucket (SSE-S3, versioned, TLS-only, public access blocked)
  ├── ECR runner repo (immutable tags, scan on push)
  └── CloudWatch log groups (14-day retention)
Optional: NAT mode or interface-endpoint mode; AWS Budgets alert (alerts only).
```
