# X1 M1 readiness: Mistral-7B-Instruct-v0.3 on gpu-node-2 (read-only compatibility audit)

**Date:** 2026-11-24, 19:21–19:30 local.
**Scope:** read-only.
- Nothing was restarted, installed or reconfigured on either host. No workload or benchmark was run and no AWS was used.
- Requests sent to the Mistral server: only `GET /version`, `GET /v1/models`, `GET /metrics` and `GET /openapi.json`.
- Requests sent to the Qwen server on gpu-node-1: only `GET /metrics` and `GET /openapi.json`.
- Host reads covered `/proc`, the Hugging Face cache, the server logs, the installed vLLM source, `nvidia-smi` queries and `ss`. In addition, `sha256sum` read the 14.5 GB weight file from disk once, at idle I/O priority.
- Two public Hugging Face API lookups were made for the model revision's metadata. They carried no project data.

**Baseline** (Qwen, v4/v5): gpu-node-1, vLLM 0.17.1, process start 1795268683.89. Recorded in `experiments/v5/HOST_VERIFICATION.json`.

---

## 1. Model identity and licence

| Item | Finding | Evidence level |
|---|---|---|
| Repository | `mistralai/Mistral-7B-Instruct-v0.3` | argv and `/v1/models` |
| Revision requested | **`main` (unpinned)**: no `--revision`; the engine config logs `revision=main, tokenizer_revision=main` | startup log |
| Resolved snapshot | **`c170c708c41dac9275d15a8fff4eca08d52bab71`**, the only snapshot in the cache. `refs/main` was written at process start + 6 s by this server's own download | HF cache |
| Weight file | `consolidated.safetensors`, 14,496,078,512 B. **On-disk SHA-256 = `76d5729be995fb6510c7f103c5b8825d3d82f8126ac949db6be367a638694d1f`**, which equals the Hugging Face LFS checksum for that file at `c170c708` | **verified by hash** (disk read on the host vs the public HF tree API) |
| Config, params, tokenizer | `config.json` 9f913dc0…, `params.json` 00dc7d10…, `generation_config.json` b6bea264…, `tokenizer.model.v3` d8233e5b… Each local git-blob hash equals HF's object ID at `c170c708` | verified by hash |
| Format actually loaded | **Mistral-native.** The cache holds `consolidated.safetensors`, `params.json` and `tokenizer.model.v3`, and no HF-format `model-0000x` shards or `tokenizer.json`. The log says "Inferred from consolidated*.safetensors" and "Using tokenizer.model.v3", so the tokenizer is mistral-common's v3 SentencePiece | startup log, cache |
| Licence | **Apache-2.0** (`cardData.license` and the tag `license:apache-2.0` at revision `c170c708`); not gated | public HF API metadata. The model card README is not in the local cache |
| Weight mapping | No weight file is currently mapped or open by the server processes (normal after loading) | `/proc/<pid>/maps,fd` |

**Snapshot evidence level.** It is stronger than v5's "verified_by_exclusion": a single snapshot, fetched by this very
process, with its weights hash-verified against the published checksum. It is not "verified_direct" in the P1 sense,
because no mapped file was observed.

**Collector caveat.** The frozen v5 rule "the snapshot predates the process start" does **not** apply here, because the
server downloaded the weights itself during startup. The rule is not violated; it simply cannot be evaluated.

**Cache layout.** The Hugging Face cache on gpu-node-2 uses a newer, shared content store:
`blobs/76d5…` is a symlink to `hub/blobs/f4/f4f49916…`. A collector or verifier that expects `blobs/<sha256>` to be a
regular file needs to follow the symlink.

## 2. Launch command and server identity

```
CUDA_VISIBLE_DEVICES=0 ~/miniconda3/envs/vllm/bin/python ~/miniconda3/envs/vllm/bin/vllm serve \
  mistralai/Mistral-7B-Instruct-v0.3 --host 0.0.0.0 --port 8000 --dtype float16 --max-model-len 4096 \
  --gpu-memory-utilization 0.85
```

- **How it was started.** `nohup` inside a `bash -c 'conda activate vllm && …'` wrapper, logging to `~/vllm.log`.
- **Processes.** API server PID 78233, `process_start_time_seconds` **1795564665.44** (2026-11-24 18:57:45 host time). EngineCore PID 78312. A resource tracker runs as PID 78311.
- **Logged non-default args.** `{model, host, dtype: float16, max_model_len: 4096, gpu_memory_utilization: 0.85}`.
- **State at audit time.** Idle: 0 running, 0 waiting. Lifetime counters: 31 prompt tokens and 152 generated tokens from earlier owner checks. Prefix-cache hits 0, preemptions 0.
- **Collector finding.** The frozen P1 collector returned `match_count 2`. The `bash -c … vllm serve` wrapper (PID 78226) started 0.17 s before the server and its argv also mentions vllm, so the ±1 s start-time match is ambiguous. X1 needs either a launch without a shell wrapper or an X1 collector that also requires the matched executable to be Python. I did not modify the v5 collector, which is frozen.

## 3. vLLM 0.34.0 vs the 0.17.1 baseline

`GET /version` confirms **0.34.0**. The installed package is `vllm-0.34.0.dist-info`, under Python 3.12.

| Setting | Qwen / 0.17.1 (gpu-node-1) | Mistral / 0.34.0 (gpu-node-2) | Same? |
|---|---|---|---|
| Launch flags beyond the model | `--dtype float16 --max-model-len 4096 --gpu-memory-utilization 0.80 --enable-prefix-caching --enable-prompt-tokens-details` | `--dtype float16 --max-model-len 4096 --gpu-memory-utilization **0.85**` (**no** `--enable-prompt-tokens-details`) | **no** |
| `VLLM_SERVER_DEV_MODE` | **1** | **unset** | **no** |
| Scheduler policy | `fcfs` (default) | `fcfs` (default) | yes |
| Async scheduling | on (logged "Asynchronous scheduling is enabled") | on by default unless incompatible; no incompatibility logged. Inferred from 0.34.0 source, not logged | yes (inferred) |
| Chunked prefill | on; `max_num_batched_tokens` 2048 **logged** | on (`enable_chunked_prefill=True`); 2048 is **not logged**, but inferred from source and consistent with compile range (1, 2048) | yes (inferred) |
| `max_num_seqs` | 256, inferred from source defaults (owner-accepted rule) | 256, inferred the same way: on a 24 GB device the 0.34.0 small-device tier gives OPENAI_API_SERVER 2048 / 256; no override in argv or logged args | yes (inferred) |
| Partial-prefill controls | `max_num_partial_prefills`=1, `max_long_partial_prefills`=1 | fields removed in 0.34.0 | n/a |
| **Admission rule** | admits on the first chunk fitting in KV | **`scheduler_reserve_full_isl=True` (new default):** the full prompt length must fit in KV before admission. New wait reason `deferred` and counter `vllm:admission_rejections` | **no** |
| Prefix caching | on, block size **16**, sha256 hash | on, block size **64**, sha256 hash | partly |
| KV cache | 3.98 GiB → 4,662 blocks × 16 = **74,592 tokens**; max concurrency at 4,096 tokens 18.2× | 6.18 GiB → 720 blocks × 64 = **46,080 tokens**; 11.25×. **"Extensible KV cache" (new) enabled** | **no** |
| KV bytes per token (model-intrinsic) | about 56 KiB (28 layers × 4 KV heads × 128 × 2 × fp16) | about 128 KiB (32 layers × 8 KV heads × 128 × 2 × fp16) | no (model) |
| Attention backend | FLASH_ATTN, FlashAttention 2 | FLASH_ATTN, FlashAttention 2 | yes |
| CUDA graphs / compile | FULL_AND_PIECEWISE, max capture size 512; inductor | FULL_AND_PIECEWISE, 512; inductor (AOT compile cache) | yes |
| dtype | bf16 → fp16 cast (one global warning) | bf16 → fp16 cast, plus **131 per-weight warnings** (o_proj, down_proj, both layernorms in all 32 layers) | partly |
| Seed | 0 | 0 | yes |
| Stack | torch 2.10.0, transformers 4.57.6, mistral_common 1.10.0, Python 3.11 | torch 2.14.0, transformers 5.22.2, mistral_common 1.13.1, Python 3.12 | **no** |
| FlashInfer | available | **disabled** (no cubin or nvcc); the sampler falls back to the default | no |

## 4. Instrumentation compatibility (tested offline on the captured `/metrics` text, using the harness's own parser)

| Harness dependency | 0.34.0 status |
|---|---|
| Metric aliases used by `quotashift.instrumentation.prom` (running, waiting, KV usage, preemptions, token counters, prefix-cache queries and hits, prompt tokens by source, sleep state, process start) | **all resolve**; no missing aliases |
| Engine histograms (queue, prefill, decode, TTFT, ITL, e2e) | **all present**. The queue, prefill and TTFT bucket edges are **identical** to 0.17.1 (queue/prefill 0.3 … 7680 s; TTFT 0.001 … 2560 s), so the v5 §5.2 engine-queue rule (mean ≤ 10 ms and every observation ≤ 0.3 s) carries over unchanged |
| `num_requests_waiting` | same gauge. 0.34.0 adds `num_requests_waiting_by_reason{capacity,deferred}`, which is more informative |
| `cache_config_info` (prefix-caching gate) | present; `enable_prefix_caching="True"` → `check_prefix_caching` passes |
| **`POST /reset_prefix_cache`** (v5 driver: verified pre-block reset; a block **fails** if the reset isn't verified) | **absent**: development-mode routes are disabled. **Every X1 block would fail closed** |
| **`GET /server_info`** (target snapshot and revision capture) | **absent**, for the same reason → the revision is recorded as "unverified" |
| `usage.prompt_tokens_details.cached_tokens` (per-request cache-hit telemetry) | **not emitted** without `--enable-prompt-tokens-details`. The harness treats it as missing (None, not 0) |
| GPU exporter (`nvidia_gpu_exporter`, port 9835; energy and GPU info) | **not running** on gpu-node-2. No validity gate depends on it, but GPU energy per token and the GPU block of the target snapshot would be missing |
| `/tokenize` (P2 trace freeze) | route present. Not exercised, to keep the audit read-only. Tokenizer-exact traces must be re-frozen with the Mistral tokenizer anyway |
| Target profile | none exists for gpu-node-2. One would be needed (private address only) |

## 5. Can Mistral be served on vLLM 0.17.1?

**Yes.** Checked in the installed 0.17.1 source on gpu-node-1:
- `MistralForCausalLM` is in the model registry (`models/mistral.py`).
- `--tokenizer-mode mistral` is supported, via mistral_common 1.10.0.
- `--config-format mistral` is supported, via `MistralConfigParser`.
- `--load-format mistral` is supported, as are `consolidated*.safetensors` patterns in the default loader.
- Mistral-7B-v0.3 is a standard dense Llama-style architecture with no features newer than 0.17.1.

Compatibility is therefore not a reason to use 0.34.0.

Two things are **unverified** until a smoke test, which needs approval:
- that 0.17.1 loads this exact snapshot cleanly in fp16;
- that its v3 tokenizer counts match mistral-common 1.13.1.

## 6. Host differences (same GPU model, different machine)

| | gpu-node-1 (Qwen) | gpu-node-2 (Mistral) |
|---|---|---|
| CPU | Intel i7-12700K, 20 threads | AMD Ryzen 7 7800X3D, 16 threads |
| RAM | 31 GiB | 30 GiB |
| Kernel | 7.0.0-42 | 7.0.0-31 |
| NVIDIA driver / CUDA | 595.71.05 / 13.2 | 595.99.02 / 13.2 |
| GPU | RTX 3090 24 GB, PCIe gen 4 x16, 350 W limit, max SM 2130 MHz, vBIOS 94.02.42.00.2F | RTX 3090 24 GB, PCIe gen 4 x16, 350 W limit, max SM 2130 MHz, vBIOS 94.02.26.40.97 |
| GPU memory in use | 20,184 MiB | 20,512 MiB |

## 7. Differences and their impact on causal interpretation

X1's cross-model contrast (P1 = M1 on G0) is meant to change **only the model**. As launched, Mistral on gpu-node-2
differs from the Qwen baseline in five more ways besides the model.

| # | Difference | Which way it could bias X1 | Severity |
|---|---|---|---|
| D1 | **vLLM 0.34.0 vs 0.17.1.** Scheduler code, the new full-prompt KV reservation at admission, extensible KV cache, torch/transformers versions, kernels | Any change in engine batching or admission changes slot hold times, and so gateway queueing. This is exactly the mechanism under study. A difference in K1 or K3 could not be attributed to the model | **critical** |
| D2 | Dev mode off → no verified prefix-cache reset, no `/server_info` | The v5 driver refuses to run, which is safe. If the reset were bypassed, cache state between blocks would be uncontrolled | **blocking** |
| D3 | `--gpu-memory-utilization` 0.85 vs 0.80; KV 46k vs 75k tokens | Smaller KV relative to load, combined with full-prompt reservation, makes KV-driven admission deferral more likely on the direct path and at C = 32. That would be engine queueing appearing for configuration reasons, not model reasons. Part of the KV gap is model-intrinsic (128 vs 56 KiB per token) and belongs to the cross-model contrast. The memory-fraction part does not | high |
| D4 | No `--enable-prompt-tokens-details` | Per-request cache-hit telemetry is lost. Engine counters remain. Isolation evidence is weaker than in v5 | medium |
| D5 | **Different host:** CPU, driver, vBIOS, kernel | Host CPU speed affects tokenization and API-server overhead, which shift TTFT. "G0" is the same GPU model, not the same machine | medium |
| D6 | Unpinned revision (`main`) | A restart could silently fetch a newer revision | medium (provenance) |
| D7 | No GPU exporter | The energy secondary metric is missing. No gate is affected | low |
| D8 | Prefix-cache block 64 vs 16 | Accidental hits need ≥ 64 shared tokens. With isolation salts, both should give 0 hits, but the probe must still verify this | low |
| D9 | fp16 cast with per-weight warnings (0.34.0 loader) | Content only. With `ignore_eos`, output lengths are fixed, so timing is unaffected unless NaNs alter the kernel path. Check at smoke | low |
| D10 | P1 collector ambiguity (shell wrapper) | Provenance tooling only | low |

## 8. Recommended normalization plan (for X1 review; every step that touches a host needs separate owner approval)

**Principle.** For the cross-model cell, change only the model. Version, flags, memory fraction, development mode,
host and tooling must match the anchor.

1. **Pin the serving stack to the v5 baseline (recommended).**
   - On gpu-node-2, create a separate environment reproducing gpu-node-1's stack exactly: vLLM 0.17.1, torch 2.10.0, transformers 4.57.6, mistral_common 1.10.0, Python 3.11.
   - Verify that `engine/arg_utils.py`, `config/vllm.py` and `entrypoints/cli/serve.py` match the v5-pinned SHA-256 values (846fe5ad…, 40507472…, 64b4427d…).
   - Keep the 0.34.0 environment untouched for reference.
2. **Use an identical launch template on every X1 server, both models.** Make the batch limits explicit so they become argv-level evidence instead of an inference:

   ```
   VLLM_SERVER_DEV_MODE=1 CUDA_VISIBLE_DEVICES=0 <env>/bin/python <env>/bin/vllm serve <model> --revision <pinned sha> \
     --host 0.0.0.0 --port 8000 --dtype float16 --max-model-len 4096 --gpu-memory-utilization 0.80 \
     --enable-prefix-caching --enable-prompt-tokens-details --max-num-seqs 256 --max-num-batched-tokens 2048
   ```

   For Mistral, add `--tokenizer-mode mistral --config-format mistral --load-format mistral`, with `--revision c170c708c41dac9275d15a8fff4eca08d52bab71`.
   - Launch the server directly with `exec` and no `bash -c` parent, or have the X1 collector match on a Python executable.
   - Bind only to the private interface if possible.
3. **Separate the model contrast from the host contrast.** Serve **both** models on gpu-node-2, one after the other, with the same environment and template.
   - X1-P1 (cross-model) then becomes Qwen vs Mistral on one machine.
   - Qwen on gpu-node-1 vs Qwen on gpu-node-2 becomes a small host-only check, using the X1 calibration seeds only.
   - Without this, D5 is confounded with the model.
4. **Install the same GPU exporter** (`nvidia_gpu_exporter` v2.0.0, as on gpu-node-1) on gpu-node-2. Add a private-only target profile for it.
5. **Pre-smoke checks, needing no workload:**
   - After launch, re-run this audit. Expect the version 0.17.1 and `/reset_prefix_cache` and `/server_info` to be listed.
   - `cache_config_info` should show block size 16 and memory utilisation 0.80.
   - Record KV tokens: they will differ from Qwen's, and that difference is model-intrinsic.
6. **Smoke checks** (need approval; minimal traffic):
   - a verified prefix-cache reset probe;
   - `/tokenize` parity against offline mistral-common for the frozen prompt templates;
   - one short fixed-length generation per shape, checking that output tokens equal `max_tokens` and that no NaN or empty output appears.
7. **If step 1 fails** (0.17.1 cannot load the snapshot cleanly), fall back to Option B:
   - Run **both** models on 0.34.0 with the same template, plus `VLLM_SERVER_DEV_MODE=1` and `--enable-prompt-tokens-details`.
   - Pre-register "vLLM version" as a platform attribute, and add a Qwen-on-0.34.0 anchor so the version effect is measured rather than confounded.
   - Disclose in X1 that the scheduler differs from v5 (full-prompt KV reservation).
8. **Record the decisions** in an X1 ADR, and copy this audit's evidence into the X1 P1 record before Freeze Commit 1.

## 9. Open items for the owner
- Approve step 1: a new environment on gpu-node-2. This is an install, so it was not done in this audit.
- Approve a restart of the Mistral server under the normalized template, and when.
- Decide whether the Qwen anchor for X1 moves to gpu-node-2 (step 3) or stays on gpu-node-1. If it stays, record host as a confound.
- Confirm the licence position for publication (Apache-2.0 per the HF metadata at the pinned revision).
