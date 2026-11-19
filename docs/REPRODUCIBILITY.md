# Reproducibility

## Pinned stack (as of 2026-11-18)
| Component | Pin | Verified how |
|---|---|---|
| Python | 3.11 (`.python-version`; resolved 3.11.15 by uv) | local |
| Python deps | `uv.lock` (numpy 2.4.6, pandas 2.3.3, pyarrow 26.0.1, pydantic 2.14.3, httpx 0.28.1, starlette 1.10.0, matplotlib 3.11.2, …) | local, tests pass |
| uv | 0.11.3; image `ghcr.io/astral-sh/uv:0.11.3@sha256:90bbb3c1…2823` | registry digest |
| Runner base image | `python:3.11-slim-bookworm@sha256:a83ba18a…3b39` | Docker Hub digest; **image not built yet** |
| vLLM | `vllm/vllm-openai:v0.33.0@sha256:d825baf9…c6e` (amd64 9.7 GB, arm64 10.9 GB compressed) | Docker Hub digest; **not run on a GPU yet** |
| DCGM exporter | `nvidia/dcgm-exporter:4.7.0-4.9.0@sha256:2490e1df…eea9` | Docker Hub digest; **not run** |
| Models | `Qwen/Qwen3-1.7B@70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`, `Qwen/Qwen3-4B@1cfa9a7208912126459214e8b04321603b3df60c` (Apache-2.0) | HF API SHA |
| Terraform | CLI 1.15.6 (local); AWS provider `= 6.73.0` with lock hashes | `validate` + mocked `test` |
| ECS GPU AMI | SSM `/aws/service/ecs/optimized-ami/amazon-linux-2023/gpu/recommended/image_id` → pin the resolved ID | **unresolved** (needs AWS read) |
| NVIDIA driver / CUDA | from the AMI / local host | **unknown** — record via `nvidia-smi` in manifest |

## Zero-cost reproduction (any laptop)
```bash
uv sync
uv run pytest -q                                   # 87 passed, 1 skipped (GPU opt-in)
uv run ruff check src tests scripts
make smoke smoke-http e0-mock                      # mock backends only
uv run python -m risksched.cli compare --experiment smoke
make tf-fmt tf-validate tf-test                    # offline; mock AWS provider
docker compose -f docker/compose.yaml up --build --abort-on-container-exit runner   # needs Docker daemon
```
Virtual-time mock runs are bit-reproducible: e.g. `smoke`, seed 11, `fcfs` gives `slo_goodput_rps = 1.8916666…`
in two separate processes (scratchpad run and `results/smoke/20261119T004933Z_fcfs_11`).

## Real-GPU E0 (requires approval; not executed)
Local NVIDIA GPU (e.g. RTX 3090), loopback only:
```bash
docker compose -f docker/compose.yaml --profile gpu up vllm          # Qwen3-1.7B, prefix caching off
uv run python -m risksched.cli validate-env --backend-url http://127.0.0.1:8000 --model Qwen/Qwen3-1.7B
RISKSCHED_GPU_TESTS=1 RISKSCHED_VLLM_URL=http://127.0.0.1:8000 RISKSCHED_VLLM_MODEL=Qwen/Qwen3-1.7B uv run pytest -m gpu
uv run python -m risksched.cli profile --config configs/experiments/e0.yaml --backend vllm \
    --backend-url http://127.0.0.1:8000 --i-understand-gpu-costs
```
Edit `configs/experiments/e0.yaml` `backend.model`/`model_revision` to match the served model and keep
`profile.max_model_len` equal to the server's `--max-model-len`. Check the vLLM startup log for the reported KV
cache size and record it.

ECS (after approved deploy): `scripts/aws_ops.sh start-gpu research` → run the runner as a one-shot task (or
port-forward via SSM) → `scripts/aws_ops.sh collect research` → `scripts/aws_ops.sh stop-gpu research`.

## Results layout
`results/<experiment>/<UTC timestamp>_<scheduler|profile_backend>_<seed>/` with `manifest.json`,
`config.resolved.yaml`, `trace.jsonl`, `requests.parquet`, `events.parquet`, `metrics_timeseries.parquet`,
`metrics_summary.json` (runs) or `cells.parquet/csv`, `rate_sweep.parquet/csv`, `summary.json` (E0), and
`figures/*.png` + `*.caption.json`. `results/` is gitignored; figures are always rebuilt by `risksched.cli report`.
Note: no git commit exists yet, so manifests currently record `git.sha = null` (see KNOWN_LIMITATIONS).
