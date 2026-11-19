"""Request event log + request-level row builder with lifecycle validation."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from quotashift.schema import TERMINAL_EVENTS, EventType, Request, RequestEvent

# Allowed predecessor sets for each event (lifecycle state machine).
_ALLOWED_PREV: dict[EventType, set[EventType | None]] = {
    EventType.OFFERED: {None},
    EventType.ACCEPTED: {EventType.OFFERED},
    EventType.REJECTED: {EventType.OFFERED},
    EventType.QUEUED: {EventType.ACCEPTED},
    EventType.SENT_TO_BACKEND: {EventType.QUEUED},
    EventType.FIRST_TOKEN: {EventType.SENT_TO_BACKEND},
    EventType.COMPLETED: {EventType.FIRST_TOKEN, EventType.SENT_TO_BACKEND},
    EventType.TIMED_OUT: {EventType.QUEUED, EventType.SENT_TO_BACKEND, EventType.FIRST_TOKEN},
    EventType.BACKEND_ERROR: {EventType.SENT_TO_BACKEND, EventType.FIRST_TOKEN},
    EventType.CANCELLED: {EventType.QUEUED, EventType.SENT_TO_BACKEND, EventType.FIRST_TOKEN},
}

_TIME_COL = {
    EventType.OFFERED: "t_offered",
    EventType.ACCEPTED: "t_accepted",
    EventType.QUEUED: "t_queued",
    EventType.SENT_TO_BACKEND: "t_sent",
    EventType.FIRST_TOKEN: "t_first_token",
}


class LifecycleError(RuntimeError):
    pass


@dataclass
class RunRecorder:
    experiment_id: str
    run_id: str
    clock: Literal["monotonic", "virtual"] = "monotonic"
    strict: bool = True
    events: list[RequestEvent] = field(default_factory=list)
    rows: dict[str, dict] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)
    _last: dict[str, EventType] = field(default_factory=dict)

    def register(self, req: Request) -> None:
        if req.request_id in self.rows:
            raise LifecycleError(f"duplicate request id {req.request_id}")
        self.rows[req.request_id] = {
            "request_id": req.request_id,
            "tenant_id": req.tenant_id,
            "workload_class": req.workload_class,
            "slo_type": str(req.slo_type),
            "ttft_deadline_ms": req.ttft_deadline_ms,
            "tpot_target_ms": req.tpot_target_ms,
            "e2e_deadline_ms": req.e2e_deadline_ms,
            "priority_weight": req.priority_weight,
            "input_token_count": req.input_token_count,
            "max_output_tokens": req.max_output_tokens,
            "trace_arrival_s": req.arrival_time_s,
            "t_offered": None,
            "t_accepted": None,
            "t_queued": None,
            "t_sent": None,
            "t_first_token": None,
            "t_terminal": None,
            "terminal_status": None,
            "terminal_detail": None,
            "output_tokens": None,  # realized, from backend usage / engine
            "output_tokens_source": None,
            "prompt_tokens_reported": None,
            "n_stream_chunks": None,
            "max_itl_s": None,
        }

    def event(
        self,
        rid: str,
        kind: EventType,
        t_rel_s: float,
        detail: str | None = None,
        output_tokens: int | None = None,
    ) -> None:
        row = self.rows.get(rid)
        if row is None:
            raise LifecycleError(f"event for unregistered request {rid}")
        prev = self._last.get(rid)
        if prev in TERMINAL_EVENTS:
            msg = f"{rid}: event {kind} after terminal {prev} (duplicate completion?)"
            self.violations.append(msg)
            if self.strict:
                raise LifecycleError(msg)
            return
        if prev not in _ALLOWED_PREV[kind]:
            msg = f"{rid}: illegal transition {prev} -> {kind}"
            self.violations.append(msg)
            if self.strict:
                raise LifecycleError(msg)
        self._last[rid] = kind
        wall = time.time_ns() if self.clock == "monotonic" else None
        self.events.append(
            RequestEvent(
                experiment_id=self.experiment_id,
                run_id=self.run_id,
                request_id=rid,
                tenant_id=row["tenant_id"],
                event=kind,
                t_rel_s=t_rel_s,
                t_wall_ns=wall,
                clock=self.clock,
                detail=detail,
                output_tokens=output_tokens,
            )
        )
        if kind in _TIME_COL:
            row[_TIME_COL[kind]] = t_rel_s
        if kind in TERMINAL_EVENTS:
            row["t_terminal"] = t_rel_s
            row["terminal_status"] = str(kind)
            row["terminal_detail"] = detail
            if output_tokens is not None:
                row["output_tokens"] = output_tokens

    def state(self, rid: str) -> EventType | None:
        return self._last.get(rid)

    def non_terminal(self) -> list[str]:
        return [r for r in self.rows if self._last.get(r) not in TERMINAL_EVENTS]

    def annotate(self, rid: str, **kw) -> None:
        self.rows[rid].update(kw)


def validate_events(events: list[RequestEvent], registered: set[str]) -> list[str]:
    """Offline re-validation of an event stream (used by tests and `report`)."""
    errs: list[str] = []
    last: dict[str, EventType] = {}
    last_t: dict[str, float] = {}
    terminals: dict[str, int] = {}
    for e in events:
        prev = last.get(e.request_id)
        if prev in TERMINAL_EVENTS:
            errs.append(f"{e.request_id}: event after terminal")
        elif prev not in _ALLOWED_PREV[e.event]:
            errs.append(f"{e.request_id}: illegal {prev}->{e.event}")
        if e.request_id in last_t and e.t_rel_s < last_t[e.request_id] - 1e-12:
            errs.append(f"{e.request_id}: non-monotonic timestamps")
        last[e.request_id] = e.event
        last_t[e.request_id] = e.t_rel_s
        if e.event in TERMINAL_EVENTS:
            terminals[e.request_id] = terminals.get(e.request_id, 0) + 1
    for rid in registered:
        n = terminals.get(rid, 0)
        if n != 1:
            errs.append(f"{rid}: {n} terminal events (expected exactly 1)")
    return errs
