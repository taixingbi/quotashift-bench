"""QuotaShift scenario specification and deterministic schedule compilation.

A *scenario* is the attack-side experimental unit (see QUOTASHIFT_CLAUDE_CODE_PLAN.md
§2, §5). It declares victim and competing tenants, fixed authorized request/token
budgets (`safety`), a comparison/control contract, and a phase program that shapes
competing-tenant traffic over time. Scenarios are **attack-only workload synthesis**:
there is no defense, no scheduler contribution, and no external target.

Compilation reuses the existing trace machinery:
`scenario -> (WorkloadConfig, list[TraceItem])` where the planned schedule is the
seeded trace produced by `workload.generator`. The schedule is deterministic in
`(scenario, seed)` and its SHA-256 (`workload.generator.trace_hash`) covers only
planned fields, so wall-clock data never changes the hash.

Safety is fail-closed: a scenario that cannot express or enforce its caps fails
validation. Endpoints are restricted to private hosts; no external URL is accepted.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from quotashift.schema import (
    ArrivalProcess,
    LengthDist,
    OracleInfo,
    SLOSpec,
    SLOType,
    TenantProfile,
    TraceItem,
    WorkloadConfig,
)
from quotashift.workload import generator as gen

SCENARIO_SCHEMA_VERSION = 1

Pattern = Literal["steady", "burst_bounded"]
RequestShape = Literal["short", "context_heavy", "decode_heavy", "mixed"]
BudgetClass = Literal["total_requests", "input_tokens", "output_tokens", "wall_clock"]

# Private-only endpoint allowlist (QUOTASHIFT_CLAUDE_CODE_PLAN.md §0.9, §1 Phase 1).
# A scenario may only target loopback, RFC1918 / link-local / ULA space, or an
# internal service-discovery name. No DNS resolution happens at validation time.
_PRIVATE_SUFFIXES = (".quotashift.internal", ".internal", ".local")


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def endpoint_is_private(url: str) -> tuple[bool, str]:
    """Return (ok, reason). Rejects public hosts and bare IP literals that route."""
    try:
        parsed = urlparse(url)
    except ValueError as e:  # pragma: no cover - defensive
        return False, f"unparseable endpoint: {e}"
    if parsed.scheme not in ("http", "https"):
        return False, f"endpoint scheme must be http/https, got {parsed.scheme!r}"
    host = parsed.hostname
    if not host:
        return False, "endpoint has no host"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if ip.is_loopback or ip.is_private or ip.is_link_local:
            return True, "private-ip"
        return False, f"endpoint IP {host} is not private (loopback/RFC1918/link-local only)"
    low = host.lower()
    if low in ("localhost",) or low.endswith(_PRIVATE_SUFFIXES):
        return True, "private-name"
    return False, (
        f"endpoint host {host!r} is not a private/internal name; "
        "only localhost, *.internal, *.quotashift.internal, *.local are allowed"
    )


class Safety(_Frozen):
    """Fixed authorized budgets. All comparisons run under identical caps."""

    require_private_endpoint: Literal[True] = True  # cannot be disabled
    allow_external_target: Literal[False] = False  # cannot be enabled
    max_total_requests: int = Field(gt=0)
    max_global_inflight: int = Field(ge=1)
    max_requests_per_tenant: int = Field(gt=0)
    max_input_tokens_per_request: int = Field(gt=0)
    max_output_tokens_per_request: int = Field(gt=0)
    max_runtime_seconds: float = Field(gt=0)
    per_request_timeout_seconds: float = Field(default=120.0, gt=0)
    abort_on_budget_exhaustion: Literal[True] = True


class Comparison(_Frozen):
    primary_control: Literal["shuffled_phase_order", "benign_only", "homogeneous_mixture"]
    matched_request_budget: bool = True
    matched_token_budget: bool = True
    repetitions: int = Field(default=5, ge=1)
    degradation_metric: Literal["ttft_p95", "e2e_p95"] = "ttft_p95"
    # Pre-registered threshold: the victim-slowdown ratio that counts as "impact".
    # Chosen before any run; never after seeing results (plan §5).
    preregistered_threshold: float = Field(default=1.5, gt=1.0)


class Phase(_Frozen):
    name: str = Field(pattern=r"^[A-Za-z0-9_\-]+$")
    duration_seconds: float = Field(gt=0)
    pattern: Pattern = "steady"
    request_shape: RequestShape = "short"
    rate_rps: float | None = Field(default=None, gt=0)  # competitor offered rate in this phase


class BenignProfile(_Frozen):
    """Victim-tenant workload, held fixed across a scenario and its control."""

    rate_rps: float = Field(gt=0)
    request_shape: RequestShape = "short"
    ttft_deadline_ms: float = Field(default=2000.0, gt=0)
    e2e_deadline_ms: float = Field(default=30000.0, gt=0)


class ScenarioConfig(_Frozen):
    schema_version: int = SCENARIO_SCHEMA_VERSION
    scenario_id: str = Field(pattern=r"^[A-Za-z0-9_\-]+$")
    seed: int = Field(ge=0)
    model: str
    model_max_len: int = Field(default=4096, gt=0)
    runtime_seconds: float = Field(gt=0)
    endpoint: str = "http://localhost:8080"  # gateway; must be private
    victim_tenants: list[str] = Field(min_length=1)
    competing_tenants: list[str] = Field(default_factory=list)
    budget_class: BudgetClass = "total_requests"
    safety: Safety
    comparison: Comparison
    benign: BenignProfile
    phases: list[Phase] = Field(default_factory=list)
    competitor_rate_rps: float = Field(default=4.0, gt=0)  # default phase rate when a phase omits it

    # ---------------------------------------------------------------- validation

    @model_validator(mode="after")
    def _check(self) -> ScenarioConfig:
        ok, reason = endpoint_is_private(self.endpoint)
        if not ok:
            raise ValueError(f"endpoint rejected: {reason}")

        tids = [*self.victim_tenants, *self.competing_tenants]
        overlap = set(self.victim_tenants) & set(self.competing_tenants)
        if overlap:
            raise ValueError(f"tenants cannot be both victim and competitor: {sorted(overlap)}")
        if len(set(tids)) != len(tids):
            raise ValueError("tenant ids must be unique across victim_tenants and competing_tenants")
        for t in tids:
            if not t or any(c not in _ID_CHARS for c in t):
                raise ValueError(f"invalid tenant id {t!r} (allowed: A-Za-z0-9_-)")

        s = self.safety
        if self.runtime_seconds > s.max_runtime_seconds:
            raise ValueError(
                f"runtime_seconds={self.runtime_seconds} exceeds safety.max_runtime_seconds={s.max_runtime_seconds}"
            )
        if s.max_input_tokens_per_request + s.max_output_tokens_per_request > self.model_max_len:
            raise ValueError(
                f"max_input+max_output ({s.max_input_tokens_per_request}+{s.max_output_tokens_per_request}) "
                f"exceeds model_max_len={self.model_max_len}"
            )

        if self.competing_tenants and not self.phases:
            raise ValueError("competing_tenants present but no phases declared")
        if self.phases:
            if not self.competing_tenants:
                raise ValueError("phases declared but no competing_tenants to drive them")
            total = sum(p.duration_seconds for p in self.phases)
            if abs(total - self.runtime_seconds) > 1e-6:
                raise ValueError(
                    f"phase durations sum to {total}, must equal runtime_seconds={self.runtime_seconds}"
                )
            names = [p.name for p in self.phases]
            if len(set(names)) != len(names):
                raise ValueError("phase names must be unique")

        # Planned-budget check: expected requests under the declared rates must not
        # exceed the per-tenant / total caps (mean of the arrival process).
        est_victim = round(self.benign.rate_rps * self.runtime_seconds)
        if est_victim > s.max_requests_per_tenant:
            raise ValueError(
                f"benign rate*runtime ~= {est_victim} req/tenant exceeds max_requests_per_tenant={s.max_requests_per_tenant}"
            )
        est_comp = round(sum((p.rate_rps or self.competitor_rate_rps) * p.duration_seconds for p in self.phases))
        if self.competing_tenants and est_comp > s.max_requests_per_tenant:
            raise ValueError(
                f"competitor expected ~{est_comp} req/tenant exceeds max_requests_per_tenant={s.max_requests_per_tenant}"
            )
        est_total = est_victim * len(self.victim_tenants) + est_comp * len(self.competing_tenants)
        if est_total > s.max_total_requests:
            raise ValueError(
                f"expected total ~{est_total} requests exceeds safety.max_total_requests={s.max_total_requests}"
            )
        return self

    # ---------------------------------------------------------------- compilation

    def _shape_dists(self, shape: RequestShape) -> tuple[LengthDist, int, LengthDist]:
        """(prompt_len_dist, requested_max_output, realized_output_dist) for a shape.

        Bounded strictly by safety caps. Realized output (sim ground truth) is only
        used by the mock engine and is always <= requested max_output.
        """
        s = self.safety
        in_cap = s.max_input_tokens_per_request
        out_cap = s.max_output_tokens_per_request
        if shape == "short":
            p_med, max_out, o_med = min(64, in_cap), min(64, out_cap), min(48, out_cap)
        elif shape == "context_heavy":  # prefill-heavy: long input, short output
            p_med, max_out, o_med = in_cap, min(32, out_cap), min(24, out_cap)
        elif shape == "decode_heavy":  # long output, short input
            p_med, max_out, o_med = min(48, in_cap), out_cap, out_cap
        else:  # mixed
            p_med, max_out, o_med = min(256, in_cap), min(128, out_cap), min(96, out_cap)
        prompt = LengthDist(dist="lognormal", median=float(max(2, p_med)), sigma=0.3, min=1, max=in_cap)
        realized = LengthDist(dist="lognormal", median=float(max(1, o_med)), sigma=0.3, min=1, max=max_out)
        return prompt, max_out, realized

    def _arrival(self, pattern: Pattern, rate: float) -> ArrivalProcess:
        if pattern == "steady":
            return ArrivalProcess(process="poisson", rate_rps=rate)
        # burst_bounded: on/off MMPP with a bounded burst multiplier, base is low.
        return ArrivalProcess(
            process="onoff",
            rate_rps=max(rate * 0.25, 0.1),
            burst_rate_rps=rate * 2.0,
            mean_on_s=5.0,
            mean_off_s=10.0,
        )

    def _slo(self, shape: RequestShape) -> SLOSpec:
        return SLOSpec(
            slo_type=SLOType.INTERACTIVE,
            ttft_deadline_ms=self.benign.ttft_deadline_ms,
            e2e_deadline_ms=self.benign.e2e_deadline_ms,
        )

    def _tenant_profile(self, tenant: str, shape: RequestShape, arrival: ArrivalProcess, cls: str) -> TenantProfile:
        prompt, max_out, realized = self._shape_dists(shape)
        return TenantProfile(
            tenant_id=tenant,
            workload_class=cls,
            arrival=arrival,
            prompt_tokens=prompt,
            max_output_tokens=max_out,
            sim_output_tokens=realized,
            slo=self._slo(shape),
            priority_weight=1.0,
        )

    def workload_config(self) -> WorkloadConfig:
        """A WorkloadConfig describing tenants (metadata/weights/duration).

        For competing tenants the first phase's shape is used as the representative
        profile; the *actual* multi-phase arrivals come from `build_trace`. This
        config is never passed to `generate_trace` directly for phased scenarios.
        """
        tps: list[TenantProfile] = []
        for t in self.victim_tenants:
            tps.append(self._tenant_profile(t, self.benign.request_shape, self._arrival("steady", self.benign.rate_rps), "victim"))
        for t in self.competing_tenants:
            p0 = self.phases[0]
            tps.append(
                self._tenant_profile(
                    t, p0.request_shape, self._arrival(p0.pattern, p0.rate_rps or self.competitor_rate_rps), "competitor"
                )
            )
        return WorkloadConfig(
            workload_id=self.scenario_id,
            duration_s=self.runtime_seconds,
            max_requests=self.safety.max_total_requests,
            max_model_len=self.model_max_len,
            tenants=tps,
        )

    def build_trace(self, seed: int | None = None, *, phase_order: list[str] | None = None) -> list[TraceItem]:
        """Deterministic planned schedule for (scenario, seed).

        `phase_order` (a permutation of phase names) produces the shuffled-phase
        control; None uses the declared order. Victim traffic is identical in both.
        """
        seed = self.seed if seed is None else seed
        items: list[TraceItem] = []

        # Victims: one steady benign segment for the whole runtime.
        for t in self.victim_tenants:
            tp = self._tenant_profile(t, self.benign.request_shape, self._arrival("steady", self.benign.rate_rps), "victim")
            items.extend(self._segment_items(tp, t_offset=0.0, duration=self.runtime_seconds, seed=seed, phase="benign"))

        # Competitors: concatenated phase segments with offset arrival times.
        phases = self.phases
        if phase_order is not None:
            by_name = {p.name: p for p in self.phases}
            missing = set(by_name) ^ set(phase_order)
            if missing:
                raise ValueError(f"phase_order must be a permutation of phase names; mismatch: {sorted(missing)}")
            phases = [by_name[n] for n in phase_order]
        for t in self.competing_tenants:
            offset = 0.0
            for ph in phases:
                tp = self._tenant_profile(
                    t, ph.request_shape, self._arrival(ph.pattern, ph.rate_rps or self.competitor_rate_rps), "competitor"
                )
                items.extend(self._segment_items(tp, t_offset=offset, duration=ph.duration_seconds, seed=seed, phase=ph.name))
                offset += ph.duration_seconds

        items.sort(key=lambda it: (it.request.arrival_time_s, it.request.request_id))
        # Enforce the hard total-request cap deterministically (fail-closed truncation).
        if len(items) > self.safety.max_total_requests:
            items = items[: self.safety.max_total_requests]
        return items

    def _segment_items(
        self, tp: TenantProfile, *, t_offset: float, duration: float, seed: int, phase: str
    ) -> list[TraceItem]:
        """Generate one tenant's arrivals within a phase window, then offset them."""
        seg = WorkloadConfig(
            workload_id=f"{self.scenario_id}:{tp.tenant_id}:{phase}",
            duration_s=duration,
            max_model_len=self.model_max_len,
            tenants=[tp],
        )
        raw = gen.generate_trace(seg, seed)
        out: list[TraceItem] = []
        for i, it in enumerate(raw):
            r = it.request
            rid = f"{tp.tenant_id}-{phase}-{seed}-{i:06d}"
            req = r.model_copy(update={
                "request_id": rid,
                "arrival_time_s": r.arrival_time_s + t_offset,
                "trace_id": f"{self.scenario_id}-s{seed}",
            })
            out.append(TraceItem(request=req, oracle=OracleInfo(request_id=rid, realized_output_tokens=it.oracle.realized_output_tokens)))
        return out

    def schedule_hash(self, seed: int | None = None, *, phase_order: list[str] | None = None) -> str:
        return gen.trace_hash(self.build_trace(seed, phase_order=phase_order))


_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def load_scenario(path: str | Path) -> ScenarioConfig:
    return ScenarioConfig.model_validate(yaml.safe_load(Path(path).read_text()))
