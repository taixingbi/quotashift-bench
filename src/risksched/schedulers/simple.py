"""Milestone-0 policies used to prove the control loop.

These are *infrastructure* policies, not the Milestone-2 baseline suite:
- `fcfs`: pass-through; the engine's own FCFS queue does all scheduling.
- `static_quota`: per-tenant token-reservation quotas + per-tenant in-flight
  cap with round-robin dispatch; exercises the ledger and isolation path.
"""

from __future__ import annotations

from risksched.schedulers.base import AdmitDecision, GatewayView, SchedulerPolicy
from risksched.schema import Request


class FCFSPassThrough(SchedulerPolicy):
    """Forward every request immediately in global arrival order.

    `max_inflight` (optional) caps gateway-outstanding requests; None means
    'no gateway admission', i.e. native vLLM FCFS behaviour.
    """

    name = "fcfs"

    def select(self, view: GatewayView) -> list[str]:
        cap = self.params.get("max_inflight")
        heads = sorted(
            (r for q in view.queues.values() for r in q),
            key=lambda r: (r.arrival_time_s, r.request_id),
        )
        if cap is not None:
            heads = heads[: max(0, cap - view.total_inflight)]
        return [r.request_id for r in heads]


class StaticQuota(SchedulerPolicy):
    """Per-tenant static reservation quota (ledger) + optional queue-length admission."""

    name = "static_quota"

    def admit(self, req: Request, view: GatewayView) -> AdmitDecision:
        max_q = self.params.get("max_queue_per_tenant")
        if max_q is not None and len(view.queues.get(req.tenant_id, ())) >= max_q:
            return AdmitDecision(False, "tenant_queue_full")
        if view.ledger is not None and req.reserved_tokens_upper_bound > view.ledger.quotas.get(req.tenant_id, 0) and not view.ledger.allow_borrow:
            return AdmitDecision(False, "request_exceeds_tenant_quota")
        return AdmitDecision(True)

    def select(self, view: GatewayView) -> list[str]:
        cap = self.params.get("max_inflight_per_tenant")
        out: list[str] = []
        # Round-robin over tenants, head-of-queue only (per-tenant FIFO).
        pending = {t: list(q) for t, q in view.queues.items() if q}
        planned_tokens = {t: 0 for t in view.queues}
        planned_count = {t: 0 for t in view.queues}
        progress = True
        while progress:
            progress = False
            for t in sorted(pending):
                if not pending[t]:
                    continue
                r = pending[t][0]
                if cap is not None and view.inflight_count.get(t, 0) + planned_count[t] >= cap:
                    continue
                if view.ledger is not None:
                    need = planned_tokens[t] + r.reserved_tokens_upper_bound
                    if not view.ledger.can_reserve(t, need):
                        continue
                out.append(r.request_id)
                planned_tokens[t] += r.reserved_tokens_upper_bound
                planned_count[t] += 1
                pending[t].pop(0)
                progress = True
        return out


class OracleSJF(SchedulerPolicy):
    """NON-DEPLOYABLE placeholder marker for oracle baselines (Milestone 3).

    Present only so leakage tests can assert that non-deployable policies are
    flagged; it raises if used in a deployable run.
    """

    name = "oracle_sjf"
    deployable = False

    def select(self, view: GatewayView) -> list[str]:  # pragma: no cover - guarded
        raise RuntimeError("oracle policies are not implemented in Milestone 0/1")


REGISTRY: dict[str, type[SchedulerPolicy]] = {
    FCFSPassThrough.name: FCFSPassThrough,
    StaticQuota.name: StaticQuota,
    OracleSJF.name: OracleSJF,
}


def make_policy(name: str, **params) -> SchedulerPolicy:
    if name not in REGISTRY:
        raise KeyError(f"unknown scheduler {name!r}; available: {sorted(REGISTRY)}")
    return REGISTRY[name](**params)
