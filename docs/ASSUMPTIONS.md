# Assumptions (each to be validated or replaced by measurement)

| # | Assumption | Status | How it will be checked |
|---|---|---|---|
| A1 | One L4 24 GB can serve Qwen3-4B (bf16) at `max_model_len=10240` with useful concurrency | unverified | vLLM startup log KV size; E0 grid statuses |
| A2 | vLLM v0.33.0 exposes `vllm:num_requests_running/waiting`, `vllm:kv_cache_usage_perc`, `vllm:num_preemptions_total` | unverified (names from v0.12 docs) | `validate-env --backend-url`; opt-in GPU test |
| A3 | vLLM `/v1/completions` accepts token-ID prompts, `stream_options.include_usage`, `ignore_eos`, per-request `seed` | believed true; unverified on v0.33.0 | first E0 smoke cell |
| A4 | Tenant classes (chat / RAG / agent) and their parameters | placeholder | calibrated from E0 (protocol §3) |
| A5 | Random-token-ID prompts are adequate for **resource** profiling (not semantics) | design choice | compare one cell against natural-text prompts in E0 |
| A6 | Gateway-level control can create measurable isolation differences | hypothesis (RQ2) | M2 E4 noisy-neighbor |
| A7 | Public-subnet, zero-ingress SGs are an acceptable security posture for a personal research account | decision (ADR-009) | your review; switch to `nat` if not acceptable |
| A8 | Docker Hub pulls of the 9.7 GB vLLM image by digest are reliable from EC2 | unverified | first start-gpu |
| A9 | Python 3.11 is acceptable for the runner (vLLM itself runs in its own image) | ok | — |
