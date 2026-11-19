# Architecture — QuotaShift

One shared vLLM engine on one GPU serves all synthetic tenants, behind an internal gateway, in an owned isolated
VPC. Load generators replay a deterministic, pre-compiled schedule. Everything is private; nothing listens publicly.

```
 isolated VPC (private subnets; NAT or interface endpoints)
 ┌───────────────────────────────────────────────────────────────────┐
 │ Fargate generators (run-task)        Fargate gateway (service)      │
 │  benign-runner  ─┐                    FastAPI                       │
 │  scenario-runner ┴─ :8080 ─────────▶  - synthetic tenant auth       │
 │                                       - fixed budgets (fail-closed) │
 │                                       - per-tenant accounting       │
 │                                       - private-only egress         │
 │                                              │ :8000                │
 │                                              ▼                       │
 │                               ECS EC2 GPU: vLLM (host net, GPU=1)    │
 │                               Qwen2.5-7B-Instruct, pinned revision   │
 │                                              │                       │
 │                               DCGM + vLLM /metrics (scraped)         │
 │                                              ▼                       │
 │                                             S3 (results, encrypted)  │
 └───────────────────────────────────────────────────────────────────┘
```

## Request lifecycle (local and deployed)
1. `ScenarioConfig` → `build_trace` compiles a deterministic, phase-aware schedule (SHA-256 stable in `(scenario,
   seed)`), persisted before execution.
2. A generator replays each request at its planned time to the gateway, tagged with a synthetic tenant key.
3. The gateway authenticates the tenant, enforces fixed caps (fail-closed), reserves tokens (isolation), and
   forwards only `/v1/chat/completions` to the private vLLM backend.
4. The backend streams/returns a completion; the gateway records realized `usage` once per `request_id` and
   attributes it to the tenant.
5. Per-request rows + the event stream are summarized into per-tenant TTFT/E2E/goodput for victim-degradation
   analysis.

## Control boundary
The gateway controls **admission, budgets, and attribution**; it does **not** schedule tokens inside vLLM and is
not a defense. vLLM runs a fixed config (prefix caching off; FCFS is vLLM's default). The experimental variable is
the scenario, which only shapes generator traffic.

## Code map
- `scenario.py` — spec + schedule compilation + private-endpoint allowlist.
- `gateway/{identity,accounting,forwarder,app}.py` — the internal gateway.
- `serving/{mock_server,engine_model,openai_backend}.py` — mock vLLM + OpenAI-compatible client.
- `workload/generator.py` — seeded multi-tenant trace generation (reused; deterministic hash).
- `runtime/runner.py`, `local.py` — orchestration and local zero-GPU execution.
- `evaluation/metrics.py` — per-tenant latency / goodput summaries.
- `infra/terraform/` — the VPC, GPU backend, gateway, generators, storage, cost gates.
