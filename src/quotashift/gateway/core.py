"""Multi-tenant gateway: per-tenant queues, admission, dispatch, accounting.

Claim boundary (ADR-001): the gateway controls admission, waiting and the
order/time at which requests are *submitted* to the engine. It does not
control per-token scheduling inside vLLM.

This is the single admission/queue engine for both execution paths: the live
in-process runner (A1–A5, E-series) and the FastAPI adapter (`gateway.app`).
Optional, fixed controls (all default off => historical behaviour unchanged):
- `rate_limiter`: rolling RPM/TPM windows (tenant + global). A request reserves
  `input + requested max_output` at offer; on completion the window entry is
  reconciled to actual usage; a request that never reached the backend is refunded.
- `max_queue_per_tenant` / `max_queue_total`: queue capacity (reject when full).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from types import MappingProxyType

from quotashift.gateway.ledger import TokenLedger
from quotashift.gateway.quotas import RateLimiter
from quotashift.instrumentation.recorder import RunRecorder
from quotashift.schedulers.base import BackendObservation, GatewayView, SchedulerPolicy
from quotashift.schema import EventType, Request


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
        rate_limiter: RateLimiter | None = None,
        max_queue_per_tenant: int | None = None,
        max_queue_total: int | None = None,
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
        self.rate_limiter = rate_limiter
        self.max_queue_per_tenant = max_queue_per_tenant
        self.max_queue_total = max_queue_total
        self.reject_reasons: dict[str, str] = {}  # rid -> reason, for adapters (HTTP status mapping)

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
        reason = self._queue_full(req.tenant_id)
        if reason is None and self.rate_limiter is not None:
            v, _retry = self.rate_limiter.try_admit(now, req.tenant_id, req.request_id, req.reserved_tokens_upper_bound)
            reason = f"rate_limited:{v}" if v else None
        if reason is None:
            dec = self.policy.admit(req, self.view(now, backend))
            if not dec.accept:
                reason = dec.reason or "policy_reject"
                if self.rate_limiter is not None:
                    self.rate_limiter.refund(req.tenant_id, req.request_id)
        if reason is not None:
            self.reject_reasons[req.request_id] = reason
            self.recorder.event(req.request_id, EventType.REJECTED, now, detail=reason)
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

    def _queue_full(self, tenant: str) -> str | None:
        if self.max_queue_per_tenant is not None and len(self.queues[tenant]) >= self.max_queue_per_tenant:
            return "tenant_queue_full"
        if self.max_queue_total is not None and len(self._queued) >= self.max_queue_total:
            return "global_queue_full"
        return None

    def retry_after_s(self, tenant: str, now: float) -> float:
        if self.rate_limiter is None:
            return 0.0
        return max(self.rate_limiter.tenants[tenant].retry_after_s(now), self.rate_limiter.glob.retry_after_s(now))

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
        prompt_tokens: int | None = None,
    ) -> None:
        f = self.inflight.pop(rid, None)
        if f is None:
            # terminal for a queued request (timeout / cancel): it never reached the backend
            req = self._queued.pop(rid, None)
            if req is None:
                return  # already terminal; ignore duplicate signal (recorder would flag it)
            self.queues[req.tenant_id].remove(req)
            if self.rate_limiter is not None:
                self.rate_limiter.refund(req.tenant_id, rid)
            self.recorder.event(rid, kind, now, detail=detail)
            return
        n_in = f.req.input_token_count if prompt_tokens is None else prompt_tokens
        if self.ledger is not None and self.ledger.holds(rid):
            charged = None if output_tokens is None else f.req.input_token_count + output_tokens
            self.ledger.release(rid, charged)
        if self.rate_limiter is not None:
            if output_tokens is not None:
                self.rate_limiter.reconcile(f.req.tenant_id, rid, n_in + output_tokens)
            else:  # reached the backend but usage unknown: keep the conservative reservation
                self.rate_limiter.reserved.pop(rid, None)
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
