# quotashift gateway / mock-vLLM image (CPU only).
# Base pinned by digest (python:3.12-slim-bookworm multi-arch index, resolved 2026-11-19 from Docker Hub).
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# uv binary pinned to the version used to create uv.lock
COPY --from=ghcr.io/astral-sh/uv:0.11.3@sha256:90bbb3c16635e9627f49eec6539f956d70746c409209041800a0280b93152823 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY configs ./configs
# X1 runner: the stage driver, frozen analysis/generator scripts and the frozen scenario files travel with the image
# (their SHA-256 are re-checked by scripts/pin_x1.py --check inside the runner before any live block).
COPY scripts ./scripts
COPY experiments ./experiments
# Every file pinned by X1 (Freeze 1 + Amendment A1), X2 (Freeze 1) and the v5 dependencies they verify must be present,
# because the frozen drivers re-check those pins in the runner. Copied SELECTIVELY: raw evidence (reports/x1/g0m0,
# reports/x2/<platform>, results) never enters the image (also excluded in .dockerignore). Checked by
# tests/unit/test_x2_aws_orchestration.py::test_image_contains_every_pinned_file_and_no_raw_evidence.
COPY docs ./docs
# X2-A3: pin_x2_a3 --check runs the FULL v5 check (the frozen counter tokenize.py is a v5 pin), which includes these four
# v5-pinned test files; only they are copied (no other tests, no fixtures, no evidence).
COPY tests/unit/test_export_v5_raw.py tests/unit/test_p1_host.py tests/unit/test_v5_protocol.py tests/unit/test_v5_rev3_consistency.py ./tests/unit/
COPY reports/x1/AMENDMENT_A1_POWER.json ./reports/x1/
COPY reports/x2/Q1_POWER.json reports/x2/VERDICT_POWER.json ./reports/x2/
COPY infra/terraform/envs/research.x2.tfvars ./infra/terraform/envs/
# X2: the frozen qualification driver calls `git status` (outside a repository it prints nothing); runner only.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --no-dev && useradd -m -u 10001 quotashift && mkdir -p /app/results /app/reports /app/inputs \
    && chown -R quotashift /app/results /app/reports /app/experiments   # X2 drivers write per-phase records under experiments/x2/<p>/
USER quotashift
# Build provenance for the in-VPC runner (no .git in the image); set ONLY by scripts/build_runner_image.sh.
ARG GIT_SHA=""
ARG GIT_DIRTY=""
ENV QUOTASHIFT_BUILD_GIT_SHA=$GIT_SHA QUOTASHIFT_BUILD_GIT_DIRTY=$GIT_DIRTY
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["python", "-m", "quotashift.cli"]
CMD ["doctor"]
