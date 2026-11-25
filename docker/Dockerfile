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
COPY docs/PROTOCOL_X1_CROSS_PLATFORM_DRAFT.md ./docs/
RUN uv sync --frozen --no-dev && useradd -m -u 10001 quotashift && mkdir -p /app/results && chown -R quotashift /app/results
USER quotashift
# Build provenance for the in-VPC runner (no .git in the image); set ONLY by scripts/build_runner_image.sh.
ARG GIT_SHA=""
ARG GIT_DIRTY=""
ENV QUOTASHIFT_BUILD_GIT_SHA=$GIT_SHA QUOTASHIFT_BUILD_GIT_DIRTY=$GIT_DIRTY
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["python", "-m", "quotashift.cli"]
CMD ["doctor"]
