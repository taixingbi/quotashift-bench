"""Run manifest / provenance collection."""

from __future__ import annotations

import hashlib
import importlib.metadata as md
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

from quotashift.instrumentation.gpu import GpuSampler
from quotashift.schema import SCHEMA_VERSION

_PKGS = ("quotashift", "numpy", "pandas", "pyarrow", "pydantic", "httpx", "starlette", "uvicorn", "matplotlib")


def git_info(repo: Path) -> dict:
    def run(*args: str) -> str | None:
        try:
            return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=5, check=True).stdout.strip()
        except (subprocess.SubprocessError, OSError):
            return None

    sha = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {"sha": sha, "dirty": bool(status) if status is not None else None,
            "note": None if sha else "no commit yet / not a git repo: results are not tied to a commit"}


def package_versions() -> dict:
    out = {}
    for p in _PKGS:
        try:
            out[p] = md.version(p)
        except md.PackageNotFoundError:
            out[p] = None
    return out


def config_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def build_manifest(*, repo: Path, experiment_id: str, run_id: str, scheduler: dict, seed: int,
                   config_resolved: dict, backend_kind: str, backend_info: dict | None,
                   trace_sha256: str | None, clock: str, gpu_info: dict | None = None) -> dict:
    synthetic = backend_kind in ("mock", "mock_http")
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "run_id": run_id,
        "created_wall_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seed": seed,
        "scheduler": scheduler,
        "backend_kind": backend_kind,
        "synthetic_backend": synthetic,
        "integrity_note": ("MOCK BACKEND: timings come from an uncalibrated simulator; NOT GPU measurements"
                           if synthetic else "real backend"),
        "clock": clock,
        "backend_info": backend_info,
        "trace_sha256": trace_sha256,
        "config_sha256": config_hash(config_resolved),
        "git": git_info(repo),
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "packages": package_versions(),
        "gpu": gpu_info if gpu_info is not None else GpuSampler().static_info(),
    }
