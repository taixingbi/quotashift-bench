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
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from quotashift.gateway.quotas import RateLimits
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

# "steady" is (historically) Poisson; "poisson" is an explicit alias with identical semantics;
# "constant" is deterministic 1/rate spacing. Historical scenarios keep "steady" unchanged.
Pattern = Literal["steady", "burst_bounded", "poisson", "constant"]
RequestShape = Literal["short", "context_heavy", "decode_heavy", "mixed", "long_context"]

# What each in-process control holds fixed vs lets vary relative to the attack arm. Victim traffic
# is identical in every control. No control can match request count, rate, total tokens AND the
# input/output composition simultaneously when shapes differ — each picks a subset (reported).
CONTROL_DIMENSIONS: dict[str, dict[str, list[str]]] = {
    "shuffled_phase_order": {"controlled": ["victim_traffic", "request_count", "total_tokens", "io_composition",
                                            "request_multiset"], "varies": ["temporal_order_of_phases"]},
    "uniform_arrivals": {"controlled": ["victim_traffic", "request_count", "total_tokens", "io_composition",
                                        "request_bodies"], "varies": ["arrival_timing (burst -> uniform)"]},
    "matched_total_short": {"controlled": ["victim_traffic", "total_tokens"],
                            "varies": ["request_count", "request_rate", "io_composition"]},
    "homogeneous_mixture": {"controlled": ["victim_traffic", "request_count", "arrival_times", "total_tokens"],
                            "varies": ["per_request_size_distribution"]},
    "rate_matched_short": {"controlled": ["victim_traffic", "request_count", "arrival_times", "request_rate"],
                           "varies": ["total_tokens", "io_composition"]},
    "benign_only": {"controlled": ["victim_traffic"], "varies": ["competitor_present"]},
    # protocol v3 (A7–A9)
    "prefix_unique": {"controlled": ["victim_traffic", "request_count", "arrival_times", "request_rate",
                                     "total_tokens", "io_composition", "output_limits"],
                      "varies": ["competitor_prefix_reuse (shared within arm -> unique per request)"]},
    "identical_workload": {"controlled": ["victim_traffic", "request_count", "arrival_times", "request_rate",
                                          "total_tokens", "io_composition", "output_limits"],
                           "varies": ["nothing (A/A null; per-arm nonce only)"]},
    "lifecycle_normal": {"controlled": ["victim_traffic", "request_count", "arrival_times", "total_tokens",
                                        "io_composition", "output_limits"],
                         "varies": ["request_lifecycle (cancel/timeout/retry -> complete)", "realized_work"]},
}
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
    primary_control: Literal[
        "shuffled_phase_order",  # A5 — in-process, phases reversed
        "uniform_arrivals",      # A1 — in-process, competitor arrivals re-timed evenly
        "matched_total_short",   # A2/A3 — in-process, competitor token budget as short requests
        "homogeneous_mixture",   # A4 — in-process, equal-sized mean-shape requests (count fixed)
        "rate_matched_short",    # v2 — same competitor arrival times/count, shape -> short (tokens vary)
        "prefix_unique",         # v3 A7 — same bodies/lengths; competitor prefixes unique instead of shared
        "identical_workload",    # v3 A7-V — A/A null (identical workload, per-arm nonce)
        "lifecycle_normal",      # v3 A8 — same requests, all complete normally (+ pre-scheduled retry twins)
        "benign_only",           # B0 — victim-only reference
    ]
    matched_request_budget: bool = True
    matched_token_budget: bool = True
    repetitions: int = Field(default=5, ge=1)
    degradation_metric: Literal["ttft_p95", "e2e_p95", "gpu_energy_per_1k_authorized_tokens",
                                "engine_service_s_per_1k_authorized_tokens"] = "ttft_p95"
    # v3: direction of the pre-registered effect. "increase" (historical): ratio >= threshold.
    # "two_sided": ratio >= threshold OR ratio <= 1/threshold.
    effect_direction: Literal["increase", "two_sided"] = "increase"
    threshold_justification: str | None = None
    # Pre-registered threshold: the victim-slowdown ratio that counts as "impact".
    # Chosen before any run; never after seeing results (plan §5).
    preregistered_threshold: float = Field(default=1.5, gt=1.0)
    # Pre-registered budget tolerance: max relative difference between attack and
    # control along a matched dimension (request count / tokens). Fail-closed.
    budget_tolerance: float = Field(default=0.05, ge=0.0, lt=1.0)


class PrefixCacheSpec(_Frozen):
    """v3 (A7/A9) controlled prefix reuse. Prefixes are arm-salted: reuse happens only within an arm."""

    victim_prefix_tokens: int = Field(default=0, ge=0)  # per-victim-tenant shared system prefix
    competitor_prefix_tokens: int = Field(default=0, ge=0)
    attack_competitor_mode: Literal["shared", "unique"] = "shared"
    control_competitor_mode: Literal["shared", "unique", "none"] = "unique"  # none: leave control competitor as-is


class LifecycleSpec(_Frozen):
    """v3 (A8) bounded per-request lifecycle plans for competing tenants (attack arm only)."""

    cancel_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    cancel_after_chunks: int = Field(default=16, ge=1)
    timeout_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    timeout_after_s: float = Field(default=1.0, gt=0.0, le=60.0)
    retry_on: list[Literal["cancel", "timeout"]] = Field(default_factory=list)
    max_retries: int = Field(default=0, ge=0, le=2)  # hard bound; no unbounded retry loops
    retry_backoff_s: float = Field(default=0.5, ge=0.0, le=30.0)
    control_preschedule_retries: bool = False  # control gets equal-shaped twins at planned retry times

    @model_validator(mode="after")
    def _check(self) -> LifecycleSpec:
        if self.cancel_fraction + self.timeout_fraction > 1.0:
            raise ValueError("cancel_fraction + timeout_fraction must be <= 1")
        if self.max_retries and not self.retry_on:
            raise ValueError("max_retries > 0 needs retry_on")
        if self.control_preschedule_retries and (self.retry_on != ["timeout"] or self.max_retries != 1):
            raise ValueError("control_preschedule_retries supports exactly retry_on=[timeout], max_retries=1")
        return self


class ScenarioGateway(_Frozen):
    """Optional fixed gateway controls for a scenario (identical in attack and control arms)."""

    rate_limits: RateLimits | None = None
    max_queue_per_tenant: int | None = Field(default=None, gt=0)
    max_queue_total: int | None = Field(default=None, gt=0)
    max_queue_wait_s: float | None = Field(default=60.0, gt=0)


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
    # Paired control scenario (A1–A4): a sibling YAML providing the matched comparison.
    # Resolved relative to this scenario's file. Required unless the control is
    # generated in-process (shuffled_phase_order) or the scenario has no competitors.
    control_scenario: str | None = None
    # ---- protocol v2 (prefix-cache isolation). v1 (default) == historical A1–A5 semantics.
    # v2: per-arm salted-hash prompt nonce at the very start of every prompt (replacing filler of
    # equal length, so planned token budgets are unchanged) + counterbalanced arm order across
    # paired seeds + per-arm prefix-cache counter snapshots (see workload/isolation.py, ADR-Q13).
    protocol_version: Literal[1, 2, 3] = 1
    # ---- protocol v3 (A7–A9; docs/A7_A9_EXPERIMENT_DESIGN.md)
    prefix_cache: PrefixCacheSpec | None = None
    lifecycle: LifecycleSpec | None = None
    metrics_interval_s: float | None = Field(default=None, gt=0.0, le=5.0)  # engine scrape interval override
    cache_reset: Literal["none", "vllm_endpoint"] = "none"  # verified reset before each arm (fail closed)
    isolation_salt: str = ""  # change per replication: the server cache persists across experiments
    expect_prefix_caching: Literal["any", "on", "off"] = "any"  # fail closed if the server differs
    gateway: ScenarioGateway | None = None  # fixed rate limits / queue caps (None = historical)

    # Directory of the file this scenario was loaded from (for resolving
    # `control_scenario`); set by `load_scenario`, None for in-memory configs.
    _source_dir: Path | None = PrivateAttr(default=None)

    # ---------------------------------------------------------------- validation

    @field_validator("expect_prefix_caching", mode="before")
    @classmethod
    def _yaml_bool(cls, v: object) -> object:
        # YAML 1.1 parses bare on/off as booleans
        return {True: "on", False: "off"}.get(v, v) if isinstance(v, bool) else v

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

        # Control-pairing contract. The shuffled-phase control is generated in-process
        # from this scenario's phases; a homogeneous-mixture control needs a sibling
        # YAML; the benign-only reference may use either an explicit B0 file or this
        # scenario's own victim traffic.
        ctrl = self.comparison.primary_control
        _in_process = ("shuffled_phase_order", "uniform_arrivals", "matched_total_short", "homogeneous_mixture",
                       "rate_matched_short", "prefix_unique", "identical_workload", "lifecycle_normal")
        dims = CONTROL_DIMENSIONS[ctrl]["controlled"]
        if ctrl != "benign_only":
            if self.comparison.matched_token_budget and "total_tokens" not in dims:
                raise ValueError(f"{ctrl} does not control total tokens; set comparison.matched_token_budget: false")
            if self.comparison.matched_request_budget and "request_count" not in dims:
                raise ValueError(f"{ctrl} does not control request count; set comparison.matched_request_budget: false")
        if ctrl in _in_process:
            if self.control_scenario is not None:
                raise ValueError(f"{ctrl} control is generated in-process; drop control_scenario")
            if ctrl != "shuffled_phase_order" and not self.competing_tenants:
                raise ValueError(f"{ctrl} control needs competing_tenants")

        # Planned-budget check: expected requests under the declared rates must not
        # exceed the per-tenant / total caps (mean of the arrival process).
        est_victim = round(self.benign.rate_rps * self.runtime_seconds)
        if est_victim > s.max_requests_per_tenant:
            raise ValueError(
                f"benign rate*runtime ~= {est_victim} req/tenant exceeds max_requests_per_tenant={s.max_requests_per_tenant}"
            )
        est_comp = round(sum((p.rate_rps or self.competitor_rate_rps) * p.duration_seconds for p in self.phases))
        if self.lifecycle is not None:  # bounded retries count against the hard caps
            est_comp = round(est_comp * (1 + self.lifecycle.max_retries))
        v3_only = {"prefix_cache": self.prefix_cache, "lifecycle": self.lifecycle}
        for name, val in v3_only.items():
            if val is not None and self.protocol_version != 3:
                raise ValueError(f"{name} requires protocol_version: 3")
        if ctrl == "prefix_unique" and (self.prefix_cache is None or not self.prefix_cache.competitor_prefix_tokens):
            raise ValueError("prefix_unique control needs prefix_cache.competitor_prefix_tokens > 0")
        if ctrl == "lifecycle_normal" and self.lifecycle is None:
            raise ValueError("lifecycle_normal control needs a lifecycle block")
        if self.cache_reset != "none" and self.protocol_version != 3:
            raise ValueError("cache_reset requires protocol_version: 3")
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
        elif shape == "long_context":  # long input AND moderate output (KV-cache pressure)
            p_med, max_out, o_med = in_cap, min(256, out_cap), min(256, out_cap)
        else:  # mixed
            p_med, max_out, o_med = min(256, in_cap), min(128, out_cap), min(96, out_cap)
        prompt = LengthDist(dist="lognormal", median=float(max(2, p_med)), sigma=0.3, min=1, max=in_cap)
        realized = LengthDist(dist="lognormal", median=float(max(1, o_med)), sigma=0.3, min=1, max=max_out)
        return prompt, max_out, realized

    def _arrival(self, pattern: Pattern, rate: float) -> ArrivalProcess:
        if pattern in ("steady", "poisson"):
            return ArrivalProcess(process="poisson", rate_rps=rate)
        if pattern == "constant":
            return ArrivalProcess(process="constant", rate_rps=rate)
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

    # ---------------------------------------------------------------- control pairing

    def canonical_control_order(self) -> list[str]:
        """Deterministic phase permutation for the shuffled-phase control (reversed)."""
        return [p.name for p in reversed(self.phases)]

    def load_control(self) -> ScenarioConfig:
        """Load the paired control scenario named by `control_scenario` (B0 only)."""
        if not self.control_scenario:
            raise ValueError(f"{self.scenario_id}: no control_scenario declared")
        base = self._source_dir or Path.cwd()
        return load_scenario(base / self.control_scenario)

    def control_trace(self, seed: int | None = None) -> tuple[list[TraceItem], str]:
        """The control trace and a label, per `comparison.primary_control`.

        All non-B0 controls are generated in-process from this scenario and are
        matched to the attack by construction on every seed (victim traffic is
        always identical):

        - shuffled_phase_order (A5): phases reversed — exact match, all dimensions.
        - uniform_arrivals (A1): competitor arrivals re-timed evenly — exact match.
        - matched_total_short (A2/A3): the competitor token budget re-expressed as
          short requests (request count free, total tokens matched within one
          request per tenant).
        - homogeneous_mixture (A4): each competitor request resized to the mean
          competitor shape — request count identical, total tokens matched to
          rounding.
        - benign_only (B0): the paired B0 file if given, else this scenario's
          victim-only traffic (a reference, not a budget-matched control).
        """
        ctrl = self.comparison.primary_control
        if ctrl == "shuffled_phase_order":
            return self.build_trace(seed, phase_order=self.canonical_control_order()), "shuffled_phase_order"
        if ctrl == "uniform_arrivals":
            return self._uniform_arrivals_control(seed), "uniform_arrivals"
        if ctrl == "matched_total_short":
            return self._matched_total_short_control(seed), "matched_total_short"
        if ctrl == "homogeneous_mixture":
            return self._homogeneous_mixture_control(seed), "homogeneous_mixture"
        if ctrl == "rate_matched_short":
            return self._rate_matched_short_control(seed), "rate_matched_short"
        if ctrl in ("prefix_unique", "identical_workload"):
            # bodies identical; the arm difference is applied by workload.prefix_cache / isolation (paired_traces)
            return self.build_trace(seed), ctrl
        if ctrl == "lifecycle_normal":
            from quotashift.workload.lifecycle import control_with_retry_twins

            sd = self.seed if seed is None else seed
            return control_with_retry_twins(self, self.build_trace(sd), sd), "lifecycle_normal"
        # benign_only
        if self.control_scenario:
            return self.load_control().build_trace(seed), f"control:{self.control_scenario}"
        victims = [it for it in self.build_trace(seed) if it.request.workload_class == "victim"]
        return victims, "benign_only(self victims)"

    def _uniform_arrivals_control(self, seed: int | None) -> list[TraceItem]:
        """A1 control: the attack trace with competitor arrivals re-timed uniformly.

        Request bodies and ids are preserved, so the request count and the input /
        output token budgets are identical to the attack by construction; only the
        competitors' temporal concentration changes (burst -> uniform). Victim
        traffic is untouched. Re-timing is deterministic (no RNG), spacing each
        competitor's requests evenly across [0, runtime).
        """
        trace = self.build_trace(seed)
        by_tenant: dict[str, list[TraceItem]] = {}
        for it in trace:
            if it.request.workload_class == "competitor":
                by_tenant.setdefault(it.request.tenant_id, []).append(it)
        out: list[TraceItem] = [it for it in trace if it.request.workload_class != "competitor"]
        for items in by_tenant.values():
            items.sort(key=lambda it: (it.request.arrival_time_s, it.request.request_id))
            n = len(items)
            for i, it in enumerate(items):
                t = (i + 0.5) * self.runtime_seconds / n if n else 0.0
                out.append(TraceItem(request=it.request.model_copy(update={"arrival_time_s": t}), oracle=it.oracle))
        out.sort(key=lambda it: (it.request.arrival_time_s, it.request.request_id))
        return out

    def _competitor_items(self, trace: list[TraceItem]) -> dict[str, list[TraceItem]]:
        """Competitor TraceItems grouped by tenant, each sorted by arrival."""
        by_tenant: dict[str, list[TraceItem]] = {}
        for it in trace:
            if it.request.workload_class == "competitor":
                by_tenant.setdefault(it.request.tenant_id, []).append(it)
        for items in by_tenant.values():
            items.sort(key=lambda it: (it.request.arrival_time_s, it.request.request_id))
        return by_tenant

    def _fixed_shape_pool(
        self, tenant: str, *, in_tokens: int, out_tokens: int, realized_tokens: int, rate: float,
        seed: int, label: str,
    ) -> list[TraceItem]:
        """A deterministic competitor pool of fixed-size requests (dist='fixed').

        Every request has exactly `in_tokens` prompt tokens and requests `out_tokens`
        output; prompt bodies are generated so the backend counts the intended length.
        """
        s = self.safety
        in_tok = max(1, min(in_tokens, s.max_input_tokens_per_request))
        out_tok = max(1, min(out_tokens, s.max_output_tokens_per_request))
        real_tok = max(1, min(realized_tokens, out_tok))
        tp = TenantProfile(
            tenant_id=tenant,
            workload_class="competitor",
            arrival=self._arrival("steady", max(rate, 0.1)),
            prompt_tokens=LengthDist(dist="fixed", value=in_tok, min=1, max=s.max_input_tokens_per_request),
            max_output_tokens=out_tok,
            sim_output_tokens=LengthDist(dist="fixed", value=real_tok, min=1, max=out_tok),
            slo=self._slo("short"),
            priority_weight=1.0,
        )
        return self._segment_items(tp, t_offset=0.0, duration=self.runtime_seconds, seed=seed, phase=label)

    def _matched_total_short_control(self, seed: int | None) -> list[TraceItem]:
        """A2/A3 control: competitor token budget delivered as short requests.

        Per tenant, generates fixed short requests (input=output=`_SHORT`) and selects
        the prefix whose cumulative total tokens best matches that tenant's attack
        competitor total. Request count is free; the matched total token budget holds
        within one request per tenant on every seed. Victim traffic is untouched.
        """
        seed = self.seed if seed is None else seed
        trace = self.build_trace(seed)
        out = [it for it in trace if it.request.workload_class != "competitor"]
        short = min(64, self.safety.max_input_tokens_per_request), min(64, self.safety.max_output_tokens_per_request)
        per_req = short[0] + short[1]
        for tenant, atk in self._competitor_items(trace).items():
            target = sum(it.request.input_token_count + it.request.max_output_tokens for it in atk)
            rate = 2.0 * (target / per_req) / self.runtime_seconds
            pool = self._fixed_shape_pool(
                tenant, in_tokens=short[0], out_tokens=short[1], realized_tokens=min(48, short[1]),
                rate=rate, seed=seed, label="ctl_short",
            )
            pool.sort(key=lambda it: (it.request.arrival_time_s, it.request.request_id))
            cum = 0
            for it in pool:
                t = it.request.input_token_count + it.request.max_output_tokens
                if cum and abs(cum - target) <= abs(cum + t - target):
                    break  # stopping now is at least as close as adding this request
                out.append(it)
                cum += t
        out.sort(key=lambda it: (it.request.arrival_time_s, it.request.request_id))
        return out

    def _rate_matched_short_control(self, seed: int | None) -> list[TraceItem]:
        """Rate-matched control: identical competitor arrival times and count, every competitor
        request resized to the short shape (64/64). Request count and rate are matched exactly;
        total tokens and input/output composition vary (reported, not gated)."""
        seed = self.seed if seed is None else seed
        trace = self.build_trace(seed)
        out = [it for it in trace if it.request.workload_class != "competitor"]
        short = min(64, self.safety.max_input_tokens_per_request), min(64, self.safety.max_output_tokens_per_request)
        for tenant, atk in self._competitor_items(trace).items():
            pool = self._fixed_shape_pool(
                tenant, in_tokens=short[0], out_tokens=short[1], realized_tokens=min(48, short[1]),
                rate=3.0 * len(atk) / self.runtime_seconds, seed=seed, label="ctl_rate_short")
            pool.sort(key=lambda it: (it.request.arrival_time_s, it.request.request_id))
            if len(pool) < len(atk):
                raise ValueError(f"rate_matched_short pool too small for {tenant} ({len(pool)} < {len(atk)})")
            for atk_it, pool_it in zip(atk, pool[: len(atk)], strict=True):
                out.append(TraceItem(
                    request=pool_it.request.model_copy(update={"arrival_time_s": atk_it.request.arrival_time_s}),
                    oracle=pool_it.oracle))
        out.sort(key=lambda it: (it.request.arrival_time_s, it.request.request_id))
        return out

    def _homogeneous_mixture_control(self, seed: int | None) -> list[TraceItem]:
        """A4 control: equal-sized homogeneous competitor workload.

        Per tenant, replaces the mixed-shape requests with the same *count* of
        fixed-size requests sized at the tenant's mean competitor shape, keeping the
        attack arrival times. Request count is identical and the total token budget is
        matched to rounding on every seed. Victim traffic is untouched.
        """
        seed = self.seed if seed is None else seed
        trace = self.build_trace(seed)
        out = [it for it in trace if it.request.workload_class != "competitor"]
        for tenant, atk in self._competitor_items(trace).items():
            n = len(atk)
            if not n:
                continue
            mean_in = round(sum(it.request.input_token_count for it in atk) / n)
            mean_out = round(sum(it.request.max_output_tokens for it in atk) / n)
            mean_real = round(sum(it.oracle.realized_output_tokens for it in atk) / n)
            pool = self._fixed_shape_pool(
                tenant, in_tokens=mean_in, out_tokens=mean_out, realized_tokens=mean_real,
                rate=2.0 * n / self.runtime_seconds, seed=seed, label="ctl_homog",
            )
            pool.sort(key=lambda it: (it.request.arrival_time_s, it.request.request_id))
            # keep attack arrival times; equal count (pool has ~2n items, so never short)
            for atk_it, pool_it in zip(atk, pool[:n], strict=False):
                out.append(TraceItem(
                    request=pool_it.request.model_copy(update={"arrival_time_s": atk_it.request.arrival_time_s}),
                    oracle=pool_it.oracle,
                ))
        out.sort(key=lambda it: (it.request.arrival_time_s, it.request.request_id))
        return out


_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def load_scenario(path: str | Path) -> ScenarioConfig:
    p = Path(path)
    sc = ScenarioConfig.model_validate(yaml.safe_load(p.read_text()))
    sc._source_dir = p.resolve().parent
    return sc
