"""X1 tokenization preflight probe (draft rev 4, section 9.1). Sends ONLY `POST /tokenize` (CPU-side; no generation,
no GPU work) to a private target, in two separate modes:

  isolated(...)  sequential requests, one in flight at a time -> per-request latency without any queueing
  burst(...)     open-loop Poisson-free fixed-interval arrivals at `rate_rps` for `seconds` -> achieved rate and
                 latency under load, i.e. queueing at the API server

The two are evaluated separately by `quotashift.x1.preflight.tokenization_check`. Runs only inside an approved X1
stage; the target must be private (the harness's endpoint allowlist applies).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence

import httpx

from quotashift.scenario import endpoint_is_private


async def _one(c: httpx.AsyncClient, url: str, model: str, prompt: str) -> float:
    t0 = time.perf_counter()
    r = await c.post(url, json={"model": model, "prompt": prompt})
    r.raise_for_status()
    if "count" not in r.json():
        raise ValueError("tokenize response has no 'count'")
    return (time.perf_counter() - t0) * 1000.0


async def isolated(base_url: str, model: str, prompts: Sequence[str], *, repeats: int = 200) -> list[float]:
    url = base_url.rstrip("/") + "/tokenize"
    out: list[float] = []
    async with httpx.AsyncClient(timeout=30) as c:
        await _one(c, url, model, prompts[0])                      # warm-up, discarded
        for i in range(repeats):
            out.append(await _one(c, url, model, prompts[i % len(prompts)]))
    return out


async def burst(base_url: str, model: str, prompts: Sequence[str], *, rate_rps: float,
                seconds: float = 30.0) -> dict:
    url = base_url.rstrip("/") + "/tokenize"
    n = max(1, int(rate_rps * seconds))
    lat: list[float] = []
    errors = 0
    limits = httpx.Limits(max_connections=256, max_keepalive_connections=256)
    async with httpx.AsyncClient(timeout=30, limits=limits) as c:
        await _one(c, url, model, prompts[0])

        async def fire(i: int, at: float) -> None:
            nonlocal errors
            await asyncio.sleep(max(0.0, at - time.perf_counter()))
            try:
                lat.append(await _one(c, url, model, prompts[i % len(prompts)]))
            except (httpx.HTTPError, ValueError):
                errors += 1
        t0 = time.perf_counter()
        await asyncio.gather(*(fire(i, t0 + i / rate_rps) for i in range(n)))
        wall = time.perf_counter() - t0
    return {"offered_rps": rate_rps, "sent": n, "completed": len(lat), "errors": errors,
            "achieved_rps": len(lat) / wall if wall > 0 else 0.0, "latencies_ms": lat, "wall_s": wall}


def clock_offset_probe(base_url: str, n: int = 20) -> dict:
    """GPU-host clock minus local clock from the server's HTTP `Date` header (1 s resolution) on GET /health.
    Each sample bounds the offset to [date - t_send - 1, date - t_recv + 1); the estimate is the centre of the
    intersection of all intervals, the bound its half-width. Read-only; no generation."""
    import email.utils

    ok, why = endpoint_is_private(base_url)
    if not ok:
        raise ValueError(f"refusing non-private target {base_url}: {why}")
    lo, hi = -1e18, 1e18
    with httpx.Client(timeout=10) as c:
        for _ in range(n):
            t0 = time.time()
            r = c.get(base_url.rstrip("/") + "/health")
            t1 = time.time()
            d = r.headers.get("date")
            if not d:
                return {"offset_s": None, "bound_s": None, "reason": "server sent no Date header"}
            srv = email.utils.parsedate_to_datetime(d).timestamp()
            lo, hi = max(lo, srv - t1), min(hi, srv + 1.0 - t0)
            time.sleep(0.137)                       # spread samples across second boundaries
    if lo > hi:
        return {"offset_s": None, "bound_s": None, "reason": "inconsistent Date headers"}
    return {"offset_s": (lo + hi) / 2, "bound_s": (hi - lo) / 2, "samples": n}


def run_probe(base_url: str, model: str, prompts: Sequence[str], *, peak_request_rps: float | None,
              repeats: int = 200, burst_seconds: float = 30.0, burst_mult: float = 10.0) -> dict:
    """Phase 1: peak_request_rps=None -> isolated only. Phase 2: also the burst at burst_mult x peak."""
    ok, why = endpoint_is_private(base_url)
    if not ok:
        raise ValueError(f"refusing non-private target {base_url}: {why}")
    out: dict = {"isolated_ms": asyncio.run(isolated(base_url, model, prompts, repeats=repeats))}
    if peak_request_rps:
        out["burst"] = asyncio.run(burst(base_url, model, prompts, rate_rps=burst_mult * peak_request_rps,
                                         seconds=burst_seconds))
    return out
