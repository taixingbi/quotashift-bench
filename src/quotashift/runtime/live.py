"""Real-time asyncio driver: gateway + HTTP backend (mock server or real vLLM).

All latency timestamps come from this single process's monotonic clock
(`time.monotonic() - t0`); wall time is recorded separately for correlation.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
import time
from dataclasses import dataclass

from quotashift.gateway.core import Gateway
from quotashift.instrumentation.gpu import GpuSampler
from quotashift.schedulers.base import BackendObservation
from quotashift.schema import EventType, TraceItem
from quotashift.serving.openai_backend import OpenAICompatBackend


@dataclass
class LiveConfig:
    end_time_s: float
    metrics_interval_s: float = 1.0
    request_timeout_s: float | None = None
    max_concurrency_cap: int = 512  # hard safety cap on simultaneous backend streams
    dispatch_tick_s: float = 0.01


async def run_live(client, gateway: Gateway, backend: OpenAICompatBackend, cfg: LiveConfig,
                   gpu: GpuSampler | None = None) -> list[dict]:
    t0 = time.monotonic()

    def now() -> float:
        return time.monotonic() - t0

    seq = itertools.count()
    heap: list[tuple[float, int, TraceItem]] = [(t, next(seq), it) for t, it in client.initial()]
    heapq.heapify(heap)
    oracle: dict[str, int] = {}
    tasks: dict[str, asyncio.Task] = {}
    wake = asyncio.Event()
    obs: BackendObservation | None = None
    timeseries: list[dict] = []
    stop = asyncio.Event()

    def push(items) -> None:
        for t, it in items:
            heapq.heappush(heap, (t, next(seq), it))
        wake.set()

    async def serve(rid: str) -> None:
        req = gateway.inflight[rid].req
        try:
            coro = backend.stream(req, on_first_token=lambda: gateway.on_first_token(rid, now()),
                                  oracle_output_tokens=oracle.get(rid))
            if cfg.request_timeout_s is not None:
                remaining = cfg.request_timeout_s - (now() - gateway.recorder.rows[rid]["t_offered"])
                res = await asyncio.wait_for(coro, timeout=max(0.001, remaining))
            else:
                res = await coro
        except TimeoutError:
            gateway.on_terminal(rid, now(), EventType.TIMED_OUT, detail="client_e2e_timeout")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - every failure becomes an explicit row
            gateway.on_terminal(rid, now(), EventType.BACKEND_ERROR, detail=f"{type(e).__name__}:{e}"[:300])
        else:
            gateway.recorder.annotate(rid, output_tokens_source=res.output_tokens_source,
                                      prompt_tokens_reported=res.prompt_tokens, n_stream_chunks=res.n_chunks,
                                      max_itl_s=res.max_itl_s)
            if res.ok:
                gateway.on_terminal(rid, now(), EventType.COMPLETED, output_tokens=res.output_tokens,
                                    detail=res.finish_reason)
            else:
                gateway.on_terminal(rid, now(), EventType.BACKEND_ERROR, detail=res.error)
        finally:
            tasks.pop(rid, None)
        push(client.on_terminal(rid, now()))

    async def metrics_loop() -> None:
        nonlocal obs
        while not stop.is_set():
            t = now()
            snap = await backend.scrape_metrics()
            g = gpu.sample() if gpu else {}
            if snap is not None:
                v = snap.values
                obs = BackendObservation(
                    t_obs_s=t,
                    num_requests_running=v.get("num_requests_running"),
                    num_requests_waiting=v.get("num_requests_waiting"),
                    kv_cache_usage_perc=v.get("kv_cache_usage_perc"),
                    num_preemptions_total=v.get("num_preemptions_total"),
                    gpu_util_perc=g.get("gpu_util_perc"),
                    missing=snap.missing,
                    source="prometheus_scrape",
                )
                row = {"t_rel_s": t, "scrape_ok": True, **{k: val for k, val in v.items()}}
            else:
                row = {"t_rel_s": t, "scrape_ok": False}  # stream interruption is recorded, not hidden
            row.update({f"gpu_{k}": val for k, val in g.items()})
            for tn, n in gateway.queue_lengths().items():
                row[f"gw_queue_{tn}"] = n
            row["gw_inflight"] = len(gateway.inflight)
            timeseries.append(row)
            try:
                await asyncio.wait_for(stop.wait(), timeout=cfg.metrics_interval_s)
            except TimeoutError:
                pass

    mtask = asyncio.create_task(metrics_loop())
    try:
        while True:
            t = now()
            while heap and heap[0][0] <= t:
                _, _, it = heapq.heappop(heap)
                oracle[it.request.request_id] = it.oracle.realized_output_tokens
                if not gateway.offer(it.request, t, obs):
                    push(client.on_terminal(it.request.request_id, t))
            for rid in gateway.expire_queued(t):
                push(client.on_terminal(rid, t))
            for req in gateway.dispatch(t, obs, limit=cfg.max_concurrency_cap - len(gateway.inflight)):
                tasks[req.request_id] = asyncio.create_task(serve(req.request_id))
            if t >= cfg.end_time_s:
                break
            if not heap and gateway.queued_count == 0 and not gateway.inflight:
                break
            wake.clear()
            timeout = cfg.dispatch_tick_s if gateway.queued_count else None
            if heap:
                dt = max(0.0, heap[0][0] - now())
                timeout = dt if timeout is None else min(timeout, dt)
            if timeout is None:
                timeout = 0.25
            try:
                await asyncio.wait_for(wake.wait(), timeout=min(timeout, max(0.0, cfg.end_time_s - now())) or 0.0001)
            except TimeoutError:
                pass
    finally:
        for task in list(tasks.values()):
            task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)
        gateway.cancel_all(now(), "run_cutoff")
        stop.set()
        await asyncio.gather(mtask, return_exceptions=True)
    return timeseries
