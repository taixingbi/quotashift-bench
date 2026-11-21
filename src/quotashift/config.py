"""Experiment configuration models + YAML loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from quotashift.gateway.quotas import RateLimits
from quotashift.schema import WorkloadConfig
from quotashift.serving.engine_model import EngineParams


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BackendConfig(_M):
    kind: Literal["mock", "mock_http", "vllm"] = "mock"
    base_url: str | None = None  # vllm / external mock_http
    model: str = "mock-model"
    model_revision: str | None = None  # provenance; must match the server's --revision
    engine: EngineParams = Field(default_factory=EngineParams)  # mock / mock_http only
    time_scale: float = 1.0  # mock_http only (wall seconds per simulated second)
    sampling: dict[str, Any] = Field(default_factory=lambda: {"temperature": 0.0})
    ignore_eos: bool = False
    # GPU telemetry (engine-global). Default = local nvidia-smi (historical behaviour).
    gpu_source: Literal["nvidia-smi", "exporter", "none"] = "nvidia-smi"
    gpu_exporter_url: str | None = None  # private only; exporter runs ON the GPU host
    gpu_smi_prefix: list[str] = Field(default_factory=list)  # e.g. ["ssh", "user@gpu-host"]
    gpu_type: str | None = None  # provenance, e.g. "NVIDIA GeForce RTX 3090" (from the target profile)

    @model_validator(mode="after")
    def _check(self) -> BackendConfig:
        if self.kind == "vllm" and not self.base_url:
            raise ValueError("vllm backend requires base_url")
        return self

    @property
    def is_mock(self) -> bool:
        return self.kind in ("mock", "mock_http")


class LedgerConfig(_M):
    quotas: dict[str, int]
    allow_borrow: bool = False


class GatewayConfig(_M):
    max_queue_wait_s: float | None = 60.0
    ledger: LedgerConfig | None = None
    # Fixed, optional controls (absent = historical behaviour). Not experimental variables
    # within an attack/control pair: identical in both arms.
    rate_limits: RateLimits | None = None
    max_queue_per_tenant: int | None = Field(default=None, gt=0)
    max_queue_total: int | None = Field(default=None, gt=0)


class RunControl(_M):
    drain_s: float = Field(default=30.0, ge=0)  # after the arrival window; then hard cutoff
    warmup_s: float = 0.0
    metrics_interval_s: float = 0.5
    request_timeout_s: float | None = 120.0
    max_requests_cap: int = 20000  # safety: refuse to run larger traces
    max_concurrency_cap: int = 512
    max_experiment_seconds: float = 3600.0  # hard wall-clock budget (live runs)


class ExperimentConfig(_M):
    experiment_id: str
    description: str = ""
    workload: WorkloadConfig | str  # inline or path to tenants YAML
    backend: BackendConfig = Field(default_factory=BackendConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    run: RunControl = Field(default_factory=RunControl)
    schedulers: dict[str, dict[str, Any]] = Field(default_factory=lambda: {"fcfs": {}})
    # Execution path (recorded in the manifest). "gateway": admission/quota/queueing in front of
    # vLLM (historical default). "direct": pass-through FCFS, no ledger/limits/queue caps —
    # measures inference-engine interference without gateway effects.
    path: Literal["gateway", "direct"] = "gateway"

    def resolved_workload(self, base: Path) -> WorkloadConfig:
        if isinstance(self.workload, WorkloadConfig):
            return self.workload
        return load_workload(_resolve_path(self.workload, base))


def _resolve_path(p: str, base: Path) -> Path:
    path = Path(p)
    if path.is_absolute() or path.exists():
        return path
    return (base / path).resolve()


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text())


def load_workload(path: Path) -> WorkloadConfig:
    return WorkloadConfig.model_validate(load_yaml(path))


def load_experiment(path: Path) -> ExperimentConfig:
    return ExperimentConfig.model_validate(load_yaml(path))
