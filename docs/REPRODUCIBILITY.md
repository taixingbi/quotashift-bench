# Reproducibility

## Pinned stack (as of 2026-11-19)
| Component | Pin | Verified how |
|---|---|---|
| Python | 3.12 (`.python-version`; resolved 3.12.13 by uv) | local |
| Python deps | `uv.lock` (numpy, pandas, pyarrow, pydantic 2.14.3, httpx, starlette 1.10.0, fastapi 0.165.0, matplotlib, …) | local, tests pass |
| uv | 0.11.3; image `ghcr.io/astral-sh/uv:0.11.3@sha256:90bbb3c1…2823` | registry digest |
| Container base image | `python:3.12-slim-bookworm@sha256:935c3c5b…03df` | Docker Hub index digest; **image not built yet** |
| vLLM | `vllm/vllm-openai:v0.33.0@sha256:d825baf9…c6e` | Docker Hub digest; **not run on a GPU yet** |
| DCGM exporter | `nvidia/dcgm-exporter:4.7.0-4.9.0@sha256:2490e1df…eea9` | Docker Hub digest; **not run** |
| Model | `Qwen/Qwen2.5-7B-Instruct@a09a35458c702b33eeacc393d103063234e8bc28` (Apache-2.0) | HF API SHA (2026-11-19) |
| Terraform | CLI 1.15.6 (local); AWS provider `= 6.73.0` with lock hashes | `validate` + mocked `test` |
| ECS GPU AMI | SSM `/aws/service/ecs/optimized-ami/amazon-linux-2023/gpu/recommended/image_id` → pin the resolved ID | **unresolved** (needs AWS read) |
| NVIDIA driver / CUDA | from the AMI / local host | **unknown** — record via `nvidia-smi` in manifest |

## Zero-cost reproduction (any laptop)
```bash
uv sync
uv run pytest -q                                   # unit + mock integration
uv run ruff check src tests scripts
uv run mypy src/quotashift
uv run quotashift validate   experiments/smoke.yaml
uv run quotashift dry-run    experiments/stateful_sequences.yaml   # stable schedule SHA-256
uv run quotashift run-local  experiments/smoke.yaml --mock
make tf-fmt tf-validate tf-test                    # offline; mock AWS provider
docker compose -f docker/compose.yaml up --build   # mock vLLM + gateway; needs Docker daemon
```
Schedules are deterministic in `(scenario, seed)`: two `dry-run` calls print the same `schedule_sha256`, and the
shuffled-phase control (`--control`) is a different, deterministic permutation.

## Real-GPU path (requires approval; not executed)
Local NVIDIA GPU (A10G/RTX-class), loopback only:
```bash
docker compose -f docker/compose.yaml --profile gpu up vllm   # Qwen2.5-7B-Instruct, prefix caching off
QUOTASHIFT_GPU_TESTS=1 QUOTASHIFT_VLLM_URL=http://127.0.0.1:8000 \
  QUOTASHIFT_VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct uv run pytest -m gpu
```
Keep the gateway's `vllm_max_model_len` equal to the server's `--max-model-len`. Record the vLLM startup log's KV
cache size in the run manifest.

ECS (after approved deploy): `scripts/aws_ops.sh start-gpu research` → run a generator as a one-shot task →
`scripts/aws_ops.sh collect research` → `scripts/aws_ops.sh stop-gpu research`.

## Results layout
`results/<scenario_id>/<UTC timestamp>_fcfs_<seed>/` with `manifest.json`, `config.resolved.yaml`, `trace.jsonl`,
`requests.parquet`, `events.parquet`, `metrics_timeseries.parquet`, `metrics_summary.json`. `results/` is
gitignored. Every mock manifest carries `synthetic_backend: true`.
