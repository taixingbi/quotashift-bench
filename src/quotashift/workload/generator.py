"""Deterministic multi-tenant open-loop workload generation.

Each tenant gets independent RNG streams derived from (global seed, tenant id,
stream name) via numpy SeedSequence, so adding/removing a tenant or changing
one tenant's length distribution does not perturb other tenants' arrivals.

Prompt text is a *synthetic template* (seeded pseudo-words). Results driven by
these prompts are a token-trace simulation, not semantic inference replay; see
docs/KNOWN_LIMITATIONS.md.
"""

from __future__ import annotations

import hashlib
import json
import zlib
from collections.abc import Iterable
from pathlib import Path

import numpy as np

from quotashift.schema import (
    ArrivalProcess,
    LengthDist,
    OracleInfo,
    Request,
    TenantProfile,
    TraceItem,
    WorkloadConfig,
)

_STREAMS = {"arrivals": 1, "prompt": 2, "oracle_output": 3, "text": 4}


def tenant_rng(seed: int, tenant_id: str, stream: str) -> np.random.Generator:
    key = (zlib.crc32(tenant_id.encode()), _STREAMS[stream])
    return np.random.default_rng(np.random.SeedSequence(entropy=seed, spawn_key=key))


def sample_lengths(dist: LengthDist, n: int, rng: np.random.Generator) -> np.ndarray:
    if dist.dist == "fixed":
        x = np.full(n, float(dist.value))
    elif dist.dist == "lognormal":
        x = rng.lognormal(mean=np.log(dist.median), sigma=dist.sigma, size=n)
    else:
        x = rng.integers(dist.low, dist.high + 1, size=n).astype(float)
    return np.clip(np.rint(x), dist.min, dist.max).astype(int)


def sample_arrivals(proc: ArrivalProcess, duration_s: float, rng: np.random.Generator) -> np.ndarray:
    """Arrival times in [0, duration_s)."""
    times: list[float] = []
    if proc.process == "poisson":
        t = 0.0
        while True:
            t += rng.exponential(1.0 / proc.rate_rps)
            if t >= duration_s:
                break
            times.append(t)
    elif proc.process == "constant":
        # deterministic spacing 1/rate with one seeded phase offset (no inter-arrival jitter)
        gap = 1.0 / proc.rate_rps
        t = float(rng.uniform(0.0, gap))
        while t < duration_s:
            times.append(t)
            t += gap
    elif proc.process == "gamma":
        shape = 1.0 / proc.cv**2
        scale = 1.0 / (proc.rate_rps * shape)
        t = 0.0
        while True:
            t += rng.gamma(shape, scale)
            if t >= duration_s:
                break
            times.append(t)
    else:  # onoff (2-state MMPP), starts in OFF state
        t, on = 0.0, False
        while t < duration_s:
            period = rng.exponential(proc.mean_on_s if on else proc.mean_off_s)
            end = min(t + period, duration_s)
            rate = proc.burst_rate_rps if on else proc.rate_rps
            u = t
            while rate > 0:
                u += rng.exponential(1.0 / rate)
                if u >= end:
                    break
                times.append(u)
            t, on = end, not on
    return np.asarray(times, dtype=float)


def synthetic_prompt(n_tokens: int, rng: np.random.Generator) -> str:
    # Pseudo-words; mock backends count whitespace-separated words as tokens.
    syll = ["ka", "lo", "mi", "ten", "ra", "so", "vel", "dun", "pi", "or", "ex", "qua"]
    idx = rng.integers(0, len(syll), size=(n_tokens, 2))
    return " ".join(syll[a] + syll[b] for a, b in idx)


def _tenant_items(cfg: WorkloadConfig, t: TenantProfile, seed: int) -> list[TraceItem]:
    arr = sample_arrivals(t.arrival, cfg.duration_s, tenant_rng(seed, t.tenant_id, "arrivals"))
    n = len(arr)
    prompt_rng = tenant_rng(seed, t.tenant_id, "prompt")
    p_len = sample_lengths(t.prompt_tokens, n, prompt_rng)
    # Requested max_tokens is capped so prompt + max_tokens fits the context window.
    max_out = np.minimum(t.max_output_tokens, np.maximum(1, cfg.max_model_len - p_len))
    true_out = sample_lengths(t.sim_output_tokens, n, tenant_rng(seed, t.tenant_id, "oracle_output"))
    true_out = np.minimum(true_out, max_out)
    text_rng = tenant_rng(seed, t.tenant_id, "text")
    items = []
    for i in range(n):
        rid = f"{t.tenant_id}-{seed}-{i:06d}"
        nonce = f"[req {rid}]"  # unique prefix => no accidental cross-request prefix-cache hits
        if cfg.prompt_mode == "synthetic_text":
            text = nonce + " " + synthetic_prompt(int(p_len[i]) - 2 if p_len[i] > 2 else 1, text_rng)
            ids = None
        else:
            text = None
            ids = tuple(int(x) for x in text_rng.integers(1000, 30000, size=int(p_len[i])))
        req = Request(
            request_id=rid,
            tenant_id=t.tenant_id,
            arrival_time_s=float(arr[i]),
            prompt_text=text,
            prompt_token_ids=ids,
            input_token_count=int(p_len[i]),
            max_output_tokens=int(max_out[i]),
            workload_class=t.workload_class,
            slo_type=t.slo.slo_type,
            ttft_deadline_ms=t.slo.ttft_deadline_ms,
            tpot_target_ms=t.slo.tpot_target_ms,
            e2e_deadline_ms=t.slo.e2e_deadline_ms,
            priority_weight=t.priority_weight,
            seed=seed,
            trace_id=f"{cfg.workload_id}-s{seed}",
        )
        items.append(TraceItem(request=req, oracle=OracleInfo(request_id=rid, realized_output_tokens=int(true_out[i]))))
    return items


def generate_trace(cfg: WorkloadConfig, seed: int) -> list[TraceItem]:
    items: list[TraceItem] = []
    for t in cfg.tenants:
        items.extend(_tenant_items(cfg, t, seed))
    items.sort(key=lambda it: (it.request.arrival_time_s, it.request.request_id))
    if cfg.max_requests is not None:
        items = items[: cfg.max_requests]
    return items


def trace_to_rows(items: Iterable[TraceItem]) -> list[dict]:
    rows = []
    for it in items:
        d = it.request.model_dump(mode="json")
        d["oracle_realized_output_tokens"] = it.oracle.realized_output_tokens
        rows.append(d)
    return rows


def trace_hash(items: Iterable[TraceItem]) -> str:
    h = hashlib.sha256()
    for row in trace_to_rows(items):
        h.update(json.dumps(row, sort_keys=True).encode())
    return h.hexdigest()


def write_trace_jsonl(items: list[TraceItem], path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in trace_to_rows(items):
            f.write(json.dumps(row, sort_keys=True) + "\n")
    return trace_hash(items)


def read_trace_jsonl(path: Path) -> list[TraceItem]:
    items = []
    for line in path.read_text().splitlines():
        d = json.loads(line)
        oracle = d.pop("oracle_realized_output_tokens")
        if d.get("prompt_token_ids") is not None:
            d["prompt_token_ids"] = tuple(d["prompt_token_ids"])
        req = Request.model_validate(d)
        items.append(TraceItem(request=req, oracle=OracleInfo(request_id=req.request_id, realized_output_tokens=oracle)))
    return items
