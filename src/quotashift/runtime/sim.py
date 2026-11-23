"""Deterministic virtual-time driver: gateway + mock engine, zero GPU cost.

Same seed + config => bit-identical event streams (no wall clock involved).
Backend observations are refreshed only every `metrics_interval_s` of virtual
time to mimic a Prometheus scrape period (policies see stale metrics, as they
would in deployment).
"""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass

from quotashift.gateway.core import Gateway
from quotashift.schedulers.base import BackendObservation
from quotashift.schema import EventType, TraceItem
from quotashift.serving.engine_model import EngineModel


@dataclass
class SimConfig:
    end_time_s: float  # hard stop-time cap; unfinished requests -> cancelled
    metrics_interval_s: float = 0.5
    request_timeout_s: float | None = None  # client-side E2E hard timeout
    idle_tick_s: float = 0.01  # re-evaluation tick when queue non-empty but nothing dispatched
    # hard cap on simultaneous backend streams, as in the live runner (None = uncapped; before 2026-11-23 the
    # simulator never applied the cap, see docs/KNOWN_LIMITATIONS.md)
    max_concurrency_cap: int | None = None


def _obs(engine: EngineModel, now: float) -> BackendObservation:
    o = engine.observe()
    return BackendObservation(
        t_obs_s=now,
        num_requests_running=o["num_requests_running"],
        num_requests_waiting=o["num_requests_waiting"],
        kv_cache_usage_perc=o["kv_cache_usage_perc"],
        num_preemptions_total=o["num_preemptions_total"],
        source="mock_engine",
    )


def run_simulation(client, gateway: Gateway, engine: EngineModel, cfg: SimConfig) -> list[dict]:
    """Run to completion or cutoff. Returns metrics time-series rows."""
    seq = itertools.count()
    heap: list[tuple[float, int, TraceItem]] = []
    for t, it in client.initial():
        heapq.heappush(heap, (t, next(seq), it))
    oracle: dict[str, int] = {}  # engine-only ground truth (never given to the gateway/policy)
    timeseries: list[dict] = []
    now = 0.0
    obs = _obs(engine, now)
    next_sample = 0.0

    def sample() -> None:
        nonlocal obs, next_sample
        obs = _obs(engine, now)
        row = {"t_rel_s": now, **engine.observe()}
        for t, n in gateway.queue_lengths().items():
            row[f"gw_queue_{t}"] = n
        row["t_gw_rel_s"] = now
        row["gw_inflight"] = len(gateway.inflight)
        timeseries.append(row)
        next_sample = now + cfg.metrics_interval_s

    def terminal(rid: str, kind: EventType, out_tokens: int | None, detail: str | None) -> None:
        gateway.on_terminal(rid, now, kind, output_tokens=out_tokens, detail=detail)
        for t, it in client.on_terminal(rid, now):
            heapq.heappush(heap, (t, next(seq), it))

    while True:
        if now >= next_sample:
            sample()
        while heap and heap[0][0] <= now:
            _, _, it = heapq.heappop(heap)
            oracle[it.request.request_id] = it.oracle.realized_output_tokens
            if not gateway.offer(it.request, now, obs):
                for t, nxt in client.on_terminal(it.request.request_id, now):
                    heapq.heappush(heap, (t, next(seq), nxt))
        for rid in gateway.expire_queued(now):
            for t, nxt in client.on_terminal(rid, now):
                heapq.heappush(heap, (t, next(seq), nxt))
        if cfg.request_timeout_s is not None:
            for rid in list(gateway.inflight):
                if now - gateway.recorder.rows[rid]["t_offered"] > cfg.request_timeout_s:
                    engine.abort(rid)
                    terminal(rid, EventType.TIMED_OUT, None, "client_e2e_timeout")
        cap_left = None if cfg.max_concurrency_cap is None else cfg.max_concurrency_cap - len(gateway.inflight)
        for req in gateway.dispatch(now, obs, limit=cap_left):
            ev = engine.add_request(
                req.request_id, req.input_token_count, req.max_output_tokens,
                oracle[req.request_id], priority=0,
            )
            if ev is not None and ev.kind == "rejected":
                terminal(req.request_id, EventType.BACKEND_ERROR, None, f"engine_rejected:{ev.detail}")
        if now >= cfg.end_time_s:
            for rid in gateway.cancel_all(now, "run_cutoff"):
                engine.abort(rid)
            sample()
            break
        if engine.has_work():
            dt, evs = engine.step()
            now += dt
            for e in evs:
                if e.kind == "first_token":
                    if e.rid in gateway.inflight:
                        gateway.on_first_token(e.rid, now)
                        gateway.recorder.annotate(e.rid, n_stream_chunks=1)
                elif e.kind == "token":
                    r = gateway.recorder.rows.get(e.rid)
                    if r is not None:
                        r["n_stream_chunks"] = (r["n_stream_chunks"] or 0) + 1
                elif e.kind == "finished":
                    gateway.recorder.annotate(e.rid, output_tokens_source="mock_engine")
                    terminal(e.rid, EventType.COMPLETED, e.generated, None)
        else:
            nxt = heap[0][0] if heap else None
            if nxt is None and gateway.queued_count == 0 and not gateway.inflight:
                sample()
                break
            if gateway.queued_count > 0:
                step_to = now + cfg.idle_tick_s if nxt is None else min(nxt, now + cfg.idle_tick_s)
            else:
                step_to = nxt if nxt is not None else now + cfg.idle_tick_s
            now = min(step_to, cfg.end_time_s) if step_to > now else now + cfg.idle_tick_s
    return timeseries
