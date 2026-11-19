# Known Limitations (Milestone 0/1)

## Evidence limits
- **No real GPU measurement exists.** This machine is an Apple M4 without NVIDIA hardware. Every E0/smoke number
  in `results/` comes from the uncalibrated mock engine (`synthetic_backend: true`, watermarked figures). The
  mock's saturation knee (~4 req/s for 1024/256) and the FCFS vs static_quota differences are artefacts of
  placeholder coefficients and **must not be cited**.
- The mock engine is qualitative: no attention-kernel, CUDA-graph, sampling, tokenizer, or scheduler-version
  fidelity; preemption victim choice and chunked-prefill details approximate vLLM V1 docs, not its source.
- Two seeds × two schedulers in the smoke are not inferential evidence.

## Measurement limits
- Client-side `backend_ttft_ms` lumps vLLM waiting + prefill + network; the internal split depends on vLLM's
  histograms (names resolved at runtime; not yet confirmed on v0.33.0).
- SSE chunks can carry >1 token, so client ITL is chunk-level. Realized tokens come from `usage`; the
  `chunks_lower_bound` fallback is flagged when usage is missing.
- GPU telemetry: `nvidia-smi` sampling only (DCGM exporter scraping is in Terraform but no client code yet).
  vLLM `/metrics` and GPU samples are taken at 0.5–1 s granularity.
- Live-mode runs use the asyncio loop of a single process; at very high concurrency the runner itself could add
  latency. Runner overhead is not yet measured (planned E8).

## Workload limits
- Prompts are synthetic templates (three-tenant runs) or random token IDs (E0) ⇒ token-trace simulation, not
  semantic replay. Realized output length under a real model will differ from `sim_output_tokens`.
- Tenant parameters are placeholders until calibrated from E0.
- Three virtual tenants are logical identities on one engine; not security-isolated customers.

## Policy / accounting limits
- `static_quota` with borrowing is non-preemptive: an owner may wait until borrowed tokens drain.
- Gateway policies cannot affect per-iteration batching inside vLLM (ADR-001).
- The RISK-Sched method, predictors (M3) and the M2 baseline suite are **not implemented**.

## Infrastructure limits
- Terraform validated offline only (mocked plan). Not verified: AMI availability, GPU quota, AZ offering,
  NVIDIA driver ↔ vLLM-image CUDA compatibility, DCGM exporter working with `NVIDIA_VISIBLE_DEVICES=all` on the
  ECS GPU AMI without reserving the GPU, `vllm serve` entrypoint and `curl` presence in the v0.33.0 image.
- Docker image not built locally (Docker daemon was not running); `docker compose config` validated only.
- No `tflint`/`checkov` scan (tools not installed); security properties covered by tftest assertions only.
- Not a git commit yet ⇒ manifests have `git.sha = null`; results are not tied to a commit.

## Novelty
- See `docs/NOVELTY_MATRIX.md` §3: several 2025–2026 papers overlap substantially; none read in full yet.
