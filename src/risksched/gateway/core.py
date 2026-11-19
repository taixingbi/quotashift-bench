"""Multi-tenant gateway: per-tenant queues, admission, dispatch, accounting.

Claim boundary (ADR-001): the gateway controls admission, waiting and the
order/time at which requests are *submitted* to the engine. It does not
control per-token scheduling inside vLLM.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from types import MappingProxyType

from risksched.gateway.ledger import TokenLedger
from risksched.instrumentation.recorder import RunRecorder
from risksched.schedulers.base import BackendObservation, GatewayView, SchedulerPolicy
from risksched.schema import EventType, Request


@dataclass
class _Inflight:
    req: Request
    t_sent: float


class Gateway:
    def __init__(
        self,
        policy: SchedulerPolicy,
        tenants: list[str],
        recorder: RunRecorder,
        ledger: TokenLedger | None = None,
        max_queue_wait_s: float | None = None,
        tenant_weights: dict[str, float] | None = None,
    ) -> None:
        if not policy.deployable:
            raise ValueError(f"policy {policy.name} is non-deployable (oracle); refuse in online gateway")
        self.policy = policy
        self.recorder = recorder
        self.ledger = ledger
        self.max_queue_wait_s = max_queue_wait_s
        self.queues: dict[str, deque[Request]] = {t: deque() for t in tenants}
        self._queued: dict[str, Request] = {}
        self.inflight: dict[str, _Inflight] = {}
        self.weights = dict(tenant_weights or {})
        self.dispatch_calls = 0

    # ------------------------------------------------------------------ view
    def view(self, now: float, backend: BackendObservation | None) -> GatewayView:
        cnt = {t: 0 for t in self.queues}
        tok = {t: 0 for t in self.queues}
        for f in self.inflight.values():
            cnt[f.req.tenant_id] += 1
            tok[f.req.tenant_id] += f.req.reserved_tokens_upper_bound
        return GatewayView(
            now_s=now,
            queues=MappingProxyType({t: tuple(q) for t, q in self.queues.items()}),
            inflight_count=MappingProxyType(cnt),
            inflight_reserved_tokens=MappingProxyType(tok),
            ledger=self.ledger,
            backend=backend,
            tenant_weights=MappingProxyType(self.weights),
        )

    # ------------------------------------------------------------------ API
    def offer(self, req: Request, now: float, backend: BackendObservation | None) -> bool:
        if req.tenant_id not in self.queues:
            raise KeyError(f"unknown tenant {req.tenant_id}")
        self.recorder.register(req)
        self.recorder.event(req.request_id, EventType.OFFERED, now)
        dec = self.policy.admit(req, self.view(now, backend))
        if not dec.accept:
            self.recorder.event(req.request_id, EventType.REJECTED, now, detail=dec.reason or "policy_reject")
            return False
        self.recorder.event(req.request_id, EventType.ACCEPTED, now)
        self.queues[req.tenant_id].append(req)
        self._queued[req.request_id] = req
        self.recorder.event(req.request_id, EventType.QUEUED, now)
        return True

    def dispatch(self, now: float, backend: BackendObservation | None, limit: int | None = None) -> list[Request]:
        """Ask the policy what to send. `limit` is a hard safety cap on how many are sent now."""
        if not self._queued or (limit is not None and limit <= 0):
            return []
        self.dispatch_calls += 1
        chosen = self.policy.select(self.view(now, backend))
        out: list[Request] = []
        seen: set[str] = set()
        for rid in chosen:
            if limit is not None and len(out) >= limit:
                break
            req = self._queued.get(rid)
            if req is None or rid in seen:
                continue  # policy cannot invent / duplicate requests
            if self.ledger is not None and not self.ledger.reserve(req.tenant_id, rid, req.reserved_tokens_upper_bound):
                continue
            seen.add(rid)
            self.queues[req.tenant_id].remove(req)
            del self._queued[rid]
            self.inflight[rid] = _Inflight(req, now)
            self.recorder.event(rid, EventType.SENT_TO_BACKEND, now)
            out.append(req)
        return out

    def on_first_token(self, rid: str, now: float) -> None:
        if rid in self.inflight:
            self.recorder.event(rid, EventType.FIRST_TOKEN, now)

    def on_terminal(
        self,
        rid: str,
        now: float,
        kind: EventType,
        output_tokens: int | None = None,
        detail: str | None = None,
    ) -> None:
        f = self.inflight.pop(rid, None)
        if f is None:
            # terminal for a queued request (timeout / cancel)
            req = self._queued.pop(rid, None)
            if req is None:
                return  # already terminal; ignore duplicate signal (recorder would flag it)
            self.queues[req.tenant_id].remove(req)
            self.recorder.event(rid, kind, now, detail=detail)
            return
        if self.ledger is not None and self.ledger.holds(rid):
            charged = None if output_tokens is None else f.req.input_token_count + output_tokens
            self.ledger.release(rid, charged)
        self.recorder.event(rid, kind, now, detail=detail, output_tokens=output_tokens)

    def expire_queued(self, now: float) -> list[str]:
        if self.max_queue_wait_s is None:
            return []
        expired = [
            r.request_id
            for r in self._queued.values()
            if now - (self.recorder.rows[r.request_id]["t_queued"] or now) > self.max_queue_wait_s
        ]
        for rid in expired:
            self.on_terminal(rid, now, EventType.TIMED_OUT, detail="gateway_queue_timeout")
        return expired

    def cancel_all(self, now: float, detail: str) -> list[str]:
        """Terminal policy at run cutoff: every non-terminal request -> cancelled."""
        rids = list(self._queued) + list(self.inflight)
        for rid in rids:
            self.on_terminal(rid, now, EventType.CANCELLED, detail=detail)
        return rids

    @property
    def queued_count(self) -> int:
        return len(self._queued)

    def queue_lengths(self) -> dict[str, int]:
        return {t: len(q) for t, q in self.queues.items()}
