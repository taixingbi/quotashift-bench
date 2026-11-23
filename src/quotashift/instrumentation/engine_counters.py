"""Per-run (per-arm) engine counter deltas from before/after vLLM `/metrics` snapshots.

Scope: ENGINE-GLOBAL — vLLM counters aggregate every client of the server, not one tenant.
Per-tenant numbers come from the gateway/request rows and are never mixed with these.

- Counter deltas (prompt/generation tokens, preemptions, prefix-cache queries/hits) and
  histogram sum/count deltas (TTFT, ITL, E2E, queue, prefill, decode) -> engine-side means.
- **Reset detection:** a counter that decreases between snapshots (server restart) is
  reported as `"reset"`, never as a negative or silently-wrong delta.
- **Unrelated-traffic detection:** the engine's prompt-token delta is compared with the sum of
  prompt tokens the run itself reported; excess beyond a tolerance, or requests already
  running/waiting at the start, flags the deltas as not attributable to this run.
- `prefix_cache_hit_ratio` = hits / queries over the run window (None if unavailable).
"""

from __future__ import annotations

from typing import Any

from quotashift.instrumentation.prom import MetricSnapshot

COUNTERS = ("prompt_tokens_total", "generation_tokens_total", "num_preemptions_total",
            "prefix_cache_queries_total", "prefix_cache_hits_total",
            "prompt_tokens_local_compute_total", "prompt_tokens_local_cache_hit_total")
HISTS = ("ttft_seconds", "itl_seconds", "e2e_seconds", "queue_time_seconds", "prefill_time_seconds",
         "decode_time_seconds")


def engine_state(snap: MetricSnapshot | None) -> dict[str, Any]:
    if snap is None:
        return {"available": False}
    v = snap.values
    cc = snap.info.get("vllm:cache_config_info", {})
    pc = cc.get("enable_prefix_caching")
    return {"available": True, "num_requests_running": v.get("num_requests_running"),
            "num_requests_waiting": v.get("num_requests_waiting"),
            "kv_cache_usage_perc": v.get("kv_cache_usage_perc"),
            "engine_awake": v.get("engine_awake"),  # None = metric not exposed by this vLLM
            "process_start_time_seconds": v.get("process_start_time_seconds"),
            "prefix_caching_enabled": None if pc is None else pc.lower() == "true",
            "cache_config_info": cc or None}


def counter_deltas(before: MetricSnapshot | None, after: MetricSnapshot | None, *,
                   client_prompt_tokens: int | None = None, client_generation_tokens: int | None = None,
                   tolerance: float = 0.02, abs_tolerance: int = 64,
                   noncompleted_prompt_upper: float | None = 0.0,
                   noncompleted_generation_upper: float | None = 0.0) -> dict[str, Any]:
    """`client_*` are usage-reported totals of completed requests. Requests that reached the engine but did not
    complete (client cancel/timeout) report no usage; their engine work is bounded by `noncompleted_*_upper`
    (None = unknown -> the check is reported as unverifiable for that dimension, never silently passed)."""
    if before is None or after is None:
        return {"available": False, "reason": "missing before/after /metrics snapshot"}
    out: dict[str, Any] = {"available": True, "scope": "engine_global", "resets": []}
    for k in COUNTERS:
        b, a = before.values.get(k), after.values.get(k)
        if a is None or b is None:
            out[k] = None
        elif a < b:
            out[k] = "reset"
            out["resets"].append(k)
        else:
            out[k] = a - b
    for k in HISTS:
        b2, a2 = before.histogram_sums.get(k), after.histogram_sums.get(k)
        if a2 is None or b2 is None:
            out[f"{k}_count"] = out[f"{k}_mean"] = None
        elif a2[1] < b2[1]:
            out[f"{k}_count"], out[f"{k}_mean"] = "reset", None
            out["resets"].append(k)
        else:
            n = a2[1] - b2[1]
            out[f"{k}_count"] = n
            out[f"{k}_sum"] = a2[0] - b2[0]
            out[f"{k}_mean"] = (a2[0] - b2[0]) / n if n > 0 else None
            # v5: cumulative bucket-count deltas [(le, count)] over the arm window (engine-global, finish-time
            # observations; vLLM 0.17.1 request-latency buckets start at le = 0.3 s — PROTOCOL_V5_DRAFT §5.2)
            hb, ha = before.histograms.get(k), after.histograms.get(k)
            if hb is not None and ha is not None:
                bd = dict(hb)
                out[f"{k}_buckets"] = [("+Inf" if le == float("inf") else le, c - bd.get(le, 0.0)) for le, c in ha]
    q, h = out.get("prefix_cache_queries_total"), out.get("prefix_cache_hits_total")
    out["prefix_cache_hit_ratio"] = (h / q) if isinstance(q, float) and isinstance(h, float) and q > 0 else None
    p = out.get("prompt_tokens_total")
    # prompt tokens that had to be prefilled (not served from the prefix cache); engine-global estimate
    out["prefill_computed_tokens_est"] = (p - h) if isinstance(p, float) and isinstance(h, float) else None
    # measured directly by the engine (vllm:prompt_tokens_by_source_total{source=local_compute}); reported beside
    # the pre-registered estimate above, never replacing it
    lc = out.get("prompt_tokens_local_compute_total")
    out["prefill_computed_tokens_measured"] = lc if isinstance(lc, float) else None
    est = out["prefill_computed_tokens_est"]
    out["prefill_est_minus_measured"] = (est - lc) if isinstance(est, float) and isinstance(lc, float) else None
    ps_b, ps_a = before.values.get("process_start_time_seconds"), after.values.get("process_start_time_seconds")
    out["server_restarted"] = (ps_b is not None and ps_a is not None and ps_a != ps_b)
    if out["server_restarted"]:
        out["resets"].append("process_start_time_seconds")

    start = engine_state(before)
    reasons = []
    if start.get("num_requests_running") or start.get("num_requests_waiting"):
        reasons.append(f"engine busy at start (running={start.get('num_requests_running')}, "
                       f"waiting={start.get('num_requests_waiting')})")
    if out["resets"]:
        reasons.append(f"counter reset: {out['resets']}")
    out["attribution_mode"] = "exact" if not (noncompleted_prompt_upper or noncompleted_generation_upper) else "bounded"
    for name, eng_key, client, upper in (
            ("prompt", "prompt_tokens_total", client_prompt_tokens, noncompleted_prompt_upper),
            ("generation", "generation_tokens_total", client_generation_tokens, noncompleted_generation_upper)):
        eng = out.get(eng_key)
        if client is None or not isinstance(eng, float):
            continue
        out[f"client_{name}_tokens"] = client
        excess = eng - client
        out[f"engine_minus_client_{name}_tokens"] = excess
        if upper is None:
            out["attribution_mode"] = "unverifiable"
            reasons.append(f"{name}: non-completed requests present and their engine work cannot be bounded")
            continue
        out[f"noncompleted_{name}_upper"] = upper
        if excess > max(abs_tolerance, tolerance * max(client, 1)) + upper:
            reasons.append(f"engine {name} tokens exceed this run's (incl. bound {upper:.0f} for non-completed) "
                           f"by {excess - upper:.0f}")
    out["unrelated_traffic_suspected"] = bool(reasons)
    out["attribution_notes"] = reasons
    out["engine_state_at_start"] = start
    out["engine_state_at_end"] = engine_state(after)
    return out


def cost_accounting(timeseries: list[dict], *, idle_power_w: float | None, authorized_tokens: int,
                    competitor_authorized_tokens: int) -> dict[str, Any]:
    """Time-series-derived cost/pressure measures for one arm (engine-global).

    - engine_busy_s: time with >= 1 running request (scrape resolution; coarse).
    - KV usage max/mean, waiting max, GPU util mean (reported, never used alone as cost).
    - GPU energy: trapezoidal integral of sampled board power (J); dynamic energy subtracts the idle power
      measured right before the arm. None when no power samples exist (never estimated otherwise).
    """
    rows = [r for r in timeseries if r.get("scrape_ok", True)]
    out: dict[str, Any] = {"scope": "engine_global", "authorized_tokens": authorized_tokens,
                           "competitor_authorized_tokens": competitor_authorized_tokens}
    busy = 0.0
    for a, b in zip(rows, rows[1:], strict=False):
        if (a.get("num_requests_running") or 0) > 0:
            busy += max(0.0, b["t_rel_s"] - a["t_rel_s"])
    out["engine_busy_s"] = busy if rows else None
    kv = [r["kv_cache_usage_perc"] for r in rows if r.get("kv_cache_usage_perc") is not None]
    wt = [r["num_requests_waiting"] for r in rows if r.get("num_requests_waiting") is not None]
    out["kv_cache_usage_max"] = max(kv) if kv else None
    out["kv_cache_usage_mean"] = sum(kv) / len(kv) if kv else None
    out["num_requests_waiting_max"] = max(wt) if wt else None
    util = [r["gpu_gpu_util_perc"] for r in timeseries if r.get("gpu_gpu_util_perc") is not None]
    out["gpu_util_mean"] = sum(util) / len(util) if util else None
    pw = [(r["t_rel_s"], r["gpu_power_w"]) for r in timeseries if r.get("gpu_power_w") is not None]
    out["gpu_power_samples"] = len(pw)
    out["gpu_idle_power_w"] = idle_power_w
    if len(pw) >= 2:
        e = sum((t2 - t1) * (p1 + p2) / 2 for (t1, p1), (t2, p2) in zip(pw, pw[1:], strict=False))
        span = pw[-1][0] - pw[0][0]
        out["gpu_energy_j"] = e
        out["gpu_dynamic_energy_j"] = (e - idle_power_w * span) if idle_power_w is not None else None
        out["gpu_energy_method"] = "trapezoid over sampled board power; dynamic = minus pre-arm idle power x span"
    else:
        out["gpu_energy_j"] = out["gpu_dynamic_energy_j"] = None
        out["gpu_energy_method"] = "unavailable: no GPU power samples (run the GPU exporter on the host)"
    return out
