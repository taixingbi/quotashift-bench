"""Scheduler-policy interface (gateway-level admission + dispatch).

A policy sees only a `GatewayView`: online request metadata (requested
limits, deadlines, weights), gateway queue state, in-flight counts, the token
ledger, and the most recent *scraped* backend observation (which may be stale
or missing). It never receives `OracleInfo`. Policies that need oracle data
must set `deployable = False` and are excluded from deployable comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from quotashift.gateway.ledger import TokenLedger
from quotashift.schema import Request


@dataclass(frozen=True)
class BackendObservation:
    """Online engine/GPU metrics as scraped (values may be None if unavailable)."""

    t_obs_s: float
    num_requests_running: float | None = None
    num_requests_waiting: float | None = None
    kv_cache_usage_perc: float | None = None
    num_preemptions_total: float | None = None
    gpu_util_perc: float | None = None
    missing: tuple[str, ...] = ()
    source: str = "unknown"


@dataclass(frozen=True)
class GatewayView:
    now_s: float
    queues: MappingProxyType  # tenant -> tuple[Request, ...] in arrival order
    inflight_count: MappingProxyType  # tenant -> int
    inflight_reserved_tokens: MappingProxyType  # tenant -> int (planning upper bounds)
    ledger: TokenLedger | None
    backend: BackendObservation | None
    tenant_weights: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))

    @property
    def total_inflight(self) -> int:
        return sum(self.inflight_count.values())


@dataclass(frozen=True)
class AdmitDecision:
    accept: bool
    reason: str | None = None


class SchedulerPolicy:
    name: str = "base"
    deployable: bool = True
    uses_backend_metrics: bool = False

    def __init__(self, **params: Any) -> None:
        self.params = params

    def admit(self, req: Request, view: GatewayView) -> AdmitDecision:
        return AdmitDecision(True)

    def select(self, view: GatewayView) -> list[str]:
        """Return request ids to dispatch now, in order. Must be queued ids."""
        raise NotImplementedError

    def describe(self) -> dict:
        return {"name": self.name, "deployable": self.deployable, "params": self.params}
