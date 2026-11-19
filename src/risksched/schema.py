"""Versioned request / tenant / event schemas.

Design rule (see docs/DECISIONS.md ADR-004): the *online* request object
(`Request`) never carries realized output length. Simulation-only ground
truth lives in `OracleInfo`, which is held by the trace / mock engine and is
never passed to deployable scheduling policies.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0.0"


class SLOType(StrEnum):
    INTERACTIVE = "interactive"  # TTFT + TPOT bound
    DEADLINE = "deadline"  # E2E bound (plus TTFT bound)
    THROUGHPUT = "throughput"  # loose / best-effort with E2E bound


class EventType(StrEnum):
    OFFERED = "offered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    QUEUED = "queued"
    SENT_TO_BACKEND = "sent_to_vllm"
    FIRST_TOKEN = "first_token"
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    BACKEND_ERROR = "backend_error"
    CANCELLED = "cancelled"


TERMINAL_EVENTS = frozenset(
    {
        EventType.COMPLETED,
        EventType.REJECTED,
        EventType.TIMED_OUT,
        EventType.BACKEND_ERROR,
        EventType.CANCELLED,
    }
)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------- workload config


class LengthDist(_Frozen):
    """Token-length distribution. All values are token counts."""

    dist: Literal["fixed", "lognormal", "uniform"] = "lognormal"
    value: int | None = None  # fixed
    median: float | None = None  # lognormal
    sigma: float | None = None  # lognormal (log-space std)
    low: int | None = None  # uniform
    high: int | None = None  # uniform
    min: int = 1
    max: int = 32768

    @model_validator(mode="after")
    def _check(self) -> LengthDist:
        if self.dist == "fixed" and self.value is None:
            raise ValueError("fixed dist requires value")
        if self.dist == "lognormal" and (self.median is None or self.sigma is None):
            raise ValueError("lognormal dist requires median and sigma")
        if self.dist == "uniform" and (self.low is None or self.high is None):
            raise ValueError("uniform dist requires low and high")
        if self.min < 0 or self.max < self.min:
            raise ValueError("invalid min/max")
        return self


class ArrivalProcess(_Frozen):
    process: Literal["poisson", "gamma", "onoff"] = "poisson"
    rate_rps: float = Field(gt=0)  # mean rate (poisson/gamma) or OFF-state rate (onoff)
    cv: float = 1.0  # gamma renewal coefficient of variation
    burst_rate_rps: float | None = None  # onoff ON-state rate
    mean_on_s: float | None = None
    mean_off_s: float | None = None

    @model_validator(mode="after")
    def _check(self) -> ArrivalProcess:
        if self.process == "gamma" and self.cv <= 0:
            raise ValueError("gamma cv must be > 0")
        if self.process == "onoff" and (
            self.burst_rate_rps is None or self.mean_on_s is None or self.mean_off_s is None
        ):
            raise ValueError("onoff requires burst_rate_rps, mean_on_s, mean_off_s")
        return self


class SLOSpec(_Frozen):
    slo_type: SLOType
    ttft_deadline_ms: float = Field(gt=0)
    tpot_target_ms: float | None = Field(default=None, gt=0)
    e2e_deadline_ms: float | None = Field(default=None, gt=0)


class TenantProfile(_Frozen):
    tenant_id: str = Field(pattern=r"^[A-Za-z0-9_\-]+$")
    workload_class: str
    arrival: ArrivalProcess
    prompt_tokens: LengthDist
    max_output_tokens: int = Field(gt=0)  # *requested* cap sent as max_tokens
    # Simulation-only ground truth for realized output length (mock backends).
    # Never visible to deployable policies; a real vLLM decides this itself.
    sim_output_tokens: LengthDist
    slo: SLOSpec
    priority_weight: float = Field(default=1.0, gt=0)


class WorkloadConfig(_Frozen):
    workload_id: str
    schema_version: str = SCHEMA_VERSION
    duration_s: float = Field(gt=0)
    max_requests: int | None = Field(default=None, gt=0)
    max_model_len: int = Field(default=8192, gt=0)
    prompt_mode: Literal["synthetic_text", "token_ids"] = "synthetic_text"
    tenants: list[TenantProfile]

    @field_validator("tenants")
    @classmethod
    def _unique(cls, v: list[TenantProfile]) -> list[TenantProfile]:
        ids = [t.tenant_id for t in v]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate tenant_id")
        if not v:
            raise ValueError("at least one tenant required")
        return v


# ---------------------------------------------------------------- requests


class Request(_Frozen):
    """Online-visible request. Contains *requested* limits only."""

    schema_version: str = SCHEMA_VERSION
    request_id: str
    tenant_id: str
    arrival_time_s: float = Field(ge=0)  # offset from run start (trace time)
    prompt_text: str | None = None
    prompt_token_ids: tuple[int, ...] | None = None
    input_token_count: int = Field(ge=0)  # planned / pre-tokenized count
    max_output_tokens: int = Field(gt=0)
    workload_class: str
    slo_type: SLOType
    ttft_deadline_ms: float
    tpot_target_ms: float | None = None
    e2e_deadline_ms: float | None = None
    priority_weight: float = 1.0
    seed: int
    trace_id: str

    @model_validator(mode="after")
    def _prompt_present(self) -> Request:
        if self.prompt_text is None and self.prompt_token_ids is None:
            raise ValueError("request needs prompt_text or prompt_token_ids")
        if self.prompt_token_ids is not None and len(self.prompt_token_ids) != self.input_token_count:
            raise ValueError("input_token_count must equal len(prompt_token_ids)")
        return self

    @property
    def reserved_tokens_upper_bound(self) -> int:
        """Planning upper bound (input + requested cap). NOT realized usage."""
        return self.input_token_count + self.max_output_tokens


class OracleInfo(_Frozen):
    """Simulation / offline-analysis ground truth. NON-DEPLOYABLE."""

    request_id: str
    realized_output_tokens: int = Field(ge=0)  # what the mock engine will generate (<= max_output_tokens)


class TraceItem(_Frozen):
    request: Request
    oracle: OracleInfo


class RequestEvent(_Frozen):
    experiment_id: str
    run_id: str
    request_id: str
    tenant_id: str
    event: EventType
    t_rel_s: float  # seconds since run start on the *runner's* monotonic (or virtual) clock
    t_wall_ns: int | None = None  # synchronized wall time for cross-process correlation only
    clock: Literal["monotonic", "virtual"] = "monotonic"
    detail: str | None = None
    output_tokens: int | None = None
