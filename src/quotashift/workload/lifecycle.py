"""Protocol v3 request-lifecycle plans (A8). docs/A7_A9_EXPERIMENT_DESIGN.md.

Plans are deterministic in (scenario, seed, request id) and kept beside the trace (the Request schema and
historical trace hashes are unchanged). Only competing tenants get non-trivial plans, only in the attack arm.

Actions use the documented client mechanisms only:
- `cancel_after_chunks`: the client closes the stream after N content chunks;
- `timeout_after_s`: the client gives up after T seconds (closes the connection);
- `complete`: normal completion.
Retries: at most `max_retries` (schema-bounded <= 2) per original request, only after a planned cancel/timeout,
after `retry_backoff_s`; a retry re-sends the same request body and completes normally. No unbounded loops:
the client also enforces a global retry budget equal to the planned maximum.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from quotashift.schema import EventType, TraceItem

_RETRY_KIND = {"cancel": "cancel_after_chunks", "timeout": "timeout_after_s"}


@dataclass(frozen=True)
class Plan:
    action: str  # complete | cancel_after_chunks | timeout_after_s
    param: float | None = None
    retries: int = 0
    backoff_s: float = 0.0


def _u(*parts: object) -> float:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:13], 16) / float(16 ** 13)


def lifecycle_plans(sc, items: list[TraceItem], seed: int) -> dict[str, Plan]:  # noqa: ANN001
    spec = sc.lifecycle
    if spec is None:
        return {}
    plans: dict[str, Plan] = {}
    for it in items:
        r = it.request
        if r.workload_class != "competitor":
            continue
        u = _u(sc.scenario_id, seed, r.request_id, "lifecycle")
        if u < spec.cancel_fraction:
            action, param = "cancel_after_chunks", float(spec.cancel_after_chunks)
        elif u < spec.cancel_fraction + spec.timeout_fraction:
            action, param = "timeout_after_s", float(spec.timeout_after_s)
        else:
            action, param = "complete", None
        retries = spec.max_retries if any(_RETRY_KIND[k] == action for k in spec.retry_on) else 0
        plans[r.request_id] = Plan(action, param, retries, spec.retry_backoff_s)
    return plans


def control_with_retry_twins(sc, items: list[TraceItem], seed: int) -> list[TraceItem]:  # noqa: ANN001
    """lifecycle_normal control: same requests (all complete) + an equal-shaped twin at each planned retry time."""
    spec = sc.lifecycle
    if spec is None or not spec.control_preschedule_retries:
        return list(items)
    plans = lifecycle_plans(sc, items, seed)
    out = list(items)
    for it in items:
        p = plans.get(it.request.request_id)
        if p and p.retries and p.action == "timeout_after_s":
            rid = f"{it.request.request_id}-r1"
            t = it.request.arrival_time_s + (p.param or 0.0) + p.backoff_s
            out.append(TraceItem(request=it.request.model_copy(update={"request_id": rid, "arrival_time_s": t}),
                                 oracle=it.oracle.model_copy(update={"request_id": rid})))
    out.sort(key=lambda x: (x.request.arrival_time_s, x.request.request_id))
    return out


@dataclass
class LifecycleClient:
    """Open-loop replay with per-request lifecycle plans and bounded, planned retries."""

    items: list[TraceItem]
    plans: dict[str, Plan]
    state_of: object  # callable rid -> EventType | None (the run recorder's state)
    kind: str = "open_loop_lifecycle"
    retries_fired: int = 0
    retries_not_needed: int = 0  # planned retry whose original completed before its cancel/timeout
    _by_id: dict[str, TraceItem] = field(default_factory=dict)
    _attempts: dict[str, int] = field(default_factory=dict)
    _retry_ids: set[str] = field(default_factory=set)
    _budget: int = 0

    def __post_init__(self) -> None:
        self._by_id = {it.request.request_id: it for it in self.items}
        self._budget = sum(p.retries for p in self.plans.values())

    def initial(self) -> list[tuple[float, TraceItem]]:
        return [(it.request.arrival_time_s, it) for it in self.items]

    def plan_for(self, rid: str) -> Plan | None:
        return self.plans.get(rid)

    def on_terminal(self, rid: str, now: float) -> list[tuple[float, TraceItem]]:
        if rid in self._retry_ids:
            return []  # retries themselves complete normally and never retry again
        origin = rid
        p = self.plans.get(origin)
        if p is None or p.retries == 0:
            return []
        st = self.state_of(rid)  # type: ignore[operator]
        if st not in (EventType.CANCELLED, EventType.TIMED_OUT):
            self.retries_not_needed += 1
            return []
        n = self._attempts.get(origin, 0)
        if n >= p.retries or self.retries_fired >= self._budget:
            return []
        self._attempts[origin] = n + 1
        self.retries_fired += 1
        it = self._by_id[origin]
        new_id = f"{origin}-r{n + 1}"
        self._retry_ids.add(new_id)
        r = it.request.model_copy(update={"request_id": new_id, "arrival_time_s": now + p.backoff_s})
        return [(now + p.backoff_s, TraceItem(request=r, oracle=it.oracle.model_copy(update={"request_id": new_id})))]
