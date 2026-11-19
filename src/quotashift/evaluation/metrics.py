"""Request-level metrics, SLO accounting and fairness (see docs/METRIC_DEFINITIONS.md).

All latencies are differences of timestamps taken by ONE process (the
runner/gateway) on ONE clock (monotonic or virtual). Never subtract clocks
from different processes.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

TERMINAL = ("completed", "rejected", "timed_out", "backend_error", "cancelled")


def percentile(values, q: float) -> float | None:
    """Linear-interpolated percentile (numpy 'linear'); None for empty input."""
    arr = np.asarray([v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))], dtype=float)
    if arr.size == 0:
        return None
    return float(np.percentile(arr, q, method="linear"))


def derive_request_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Adds latency and SLO columns. Input: requests table from RunRecorder."""
    d = df.copy()
    nan = np.nan
    t_off = d["t_offered"].astype(float)
    t_sent = d["t_sent"].astype(float)
    t_ft = d["t_first_token"].astype(float)
    t_end = d["t_terminal"].astype(float)
    done = d["terminal_status"] == "completed"
    out = d["output_tokens"].astype(float)
    d["gateway_queue_ms"] = (t_sent - t_off) * 1e3
    d["ttft_ms"] = (t_ft - t_off) * 1e3  # user-facing: includes gateway queue
    d["backend_ttft_ms"] = (t_ft - t_sent) * 1e3  # engine waiting + prefill (+ network)
    d["e2e_ms"] = np.where(done, (t_end - t_off) * 1e3, nan)
    # TPOT = decode time / (n_out - 1); undefined for n_out <= 1.
    d["tpot_ms"] = np.where(done & (out > 1), (t_end - t_ft) * 1e3 / (out - 1), nan)

    ttft_ok = d["ttft_ms"] <= d["ttft_deadline_ms"]
    tpot_tgt = d["tpot_target_ms"].astype(float)
    tpot_ok = tpot_tgt.isna() | d["tpot_ms"].isna() | (d["tpot_ms"] <= tpot_tgt)
    e2e_tgt = d["e2e_deadline_ms"].astype(float)
    e2e_ok = e2e_tgt.isna() | (d["e2e_ms"] <= e2e_tgt)
    d["slo_met"] = done & ttft_ok & tpot_ok & e2e_ok
    return d


def jain_index(x) -> float | None:
    a = np.asarray(list(x), dtype=float)
    if a.size == 0 or np.all(a == 0):
        return None
    return float(a.sum() ** 2 / (a.size * (a**2).sum()))


def summarize(
    df: pd.DataFrame,
    window_s: float,
    warmup_s: float = 0.0,
) -> dict:
    """Summary over requests whose trace arrival is in [warmup_s, window_s).

    Denominator = ALL offered requests in the window (rejected, timed out,
    errored, cancelled count as unsuccessful). Warm-up exclusions are counted
    and reported, never silent.
    """
    d = derive_request_metrics(df)
    in_win = (d["trace_arrival_s"] >= warmup_s) & (d["trace_arrival_s"] < window_s)
    excluded = int((~in_win).sum())
    d = d[in_win]
    meas_s = max(window_s - warmup_s, 1e-9)
    n = len(d)
    status_counts = {s: int((d["terminal_status"] == s).sum()) for s in TERMINAL}
    non_terminal = int(d["terminal_status"].isna().sum())
    comp = d[d["terminal_status"] == "completed"]

    def lat(col: str) -> dict:
        return {f"p{q}": percentile(comp[col].tolist(), q) for q in (50, 90, 95, 99)} | {"n": int(comp[col].notna().sum())}

    out_tokens = comp["output_tokens"].fillna(0).sum()
    summary = {
        "window_s": meas_s,
        "warmup_s": warmup_s,
        "excluded_outside_window": excluded,
        "offered": n,
        "status_counts": status_counts,
        "non_terminal": non_terminal,
        "accounting_conserved": (sum(status_counts.values()) + non_terminal) == n and non_terminal == 0,
        "slo_met": int(d["slo_met"].sum()),
        "slo_goodput_rps": float(d["slo_met"].sum() / meas_s),
        "offered_rps": n / meas_s,
        "offered_success_fraction": float(d["slo_met"].mean()) if n else None,
        "completed_rps": status_counts["completed"] / meas_s,
        "output_tokens_total": int(out_tokens),
        "output_tokens_per_s": float(out_tokens / meas_s),
        "input_tokens_completed": int(comp["input_token_count"].sum()),
        "ttft_ms": lat("ttft_ms"),
        "backend_ttft_ms": lat("backend_ttft_ms"),
        "gateway_queue_ms": lat("gateway_queue_ms"),
        "tpot_ms": lat("tpot_ms"),
        "e2e_ms": lat("e2e_ms"),
    }
    per_t = {}
    for t, g in d.groupby("tenant_id"):
        offered = len(g)
        met = int(g["slo_met"].sum())
        gc = g[g["terminal_status"] == "completed"]
        per_t[t] = {
            "offered": offered,
            "slo_met": met,
            "slo_attainment": met / offered if offered else None,
            "goodput_rps": met / meas_s,
            "weight": float(g["priority_weight"].iloc[0]),
            "status_counts": {s: int((g["terminal_status"] == s).sum()) for s in TERMINAL},
            "service_tokens": int((gc["input_token_count"] + gc["output_tokens"].fillna(0)).sum()),
            "ttft_p95_ms": percentile(gc["ttft_ms"].tolist(), 95),
            "tpot_p95_ms": percentile(gc["tpot_ms"].tolist(), 95),
        }
    summary["per_tenant"] = per_t
    att = [v["slo_attainment"] for v in per_t.values() if v["slo_attainment"] is not None]
    summary["worst_tenant_slo_attainment"] = min(att) if att else None
    # Jain over normalized satisfaction s_i = SLO attainment in [0,1] (comparable across tenants).
    summary["jain_slo_attainment"] = jain_index(att)
    wsum = sum(v["weight"] for v in per_t.values()) or 1.0
    summary["weighted_tenant_goodput_rps"] = sum(v["weight"] / wsum * v["goodput_rps"] for v in per_t.values())
    return summary


# ---------------------------------------------------------------- Prometheus histograms


def histogram_quantile(q: float, buckets: list[tuple[float, float]]) -> float | None:
    """Prometheus-style quantile from cumulative buckets [(le, count), ...] incl. +Inf.

    Linear interpolation within the bucket, lower bound 0 for the first bucket;
    returns the highest finite bound if the quantile lands in +Inf bucket.
    """
    if not buckets:
        return None
    b = sorted(buckets, key=lambda x: x[0])
    total = b[-1][1]
    if total <= 0:
        return None
    rank = q * total
    prev_le, prev_c = 0.0, 0.0
    for le, c in b:
        if c >= rank:
            if math.isinf(le):
                return prev_le
            if c == prev_c:
                return le
            return prev_le + (le - prev_le) * (rank - prev_c) / (c - prev_c)
        prev_le, prev_c = le, c
    return prev_le
