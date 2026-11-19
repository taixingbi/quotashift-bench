# risksched runner / gateway / mock-vLLM image (CPU only).
# Base pinned by digest (python:3.11-slim-bookworm, resolved 2026-11-18 from Docker Hub).
FROM python:3.11-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# uv binary pinned to the version used to create uv.lock
COPY --from=ghcr.io/astral-sh/uv:0.11.3@sha256:90bbb3c16635e9627f49eec6539f956d70746c409209041800a0280b93152823 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY configs ./configs
RUN uv sync --frozen --no-dev && useradd -m -u 10001 risksched && mkdir -p /app/results && chown -R risksched /app/results
USER risksched
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["python", "-m", "risksched.cli"]
CMD ["doctor"]
