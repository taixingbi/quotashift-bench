"""Gateway slot occupancy rebuilt from per-request timestamps (ported from scripts/v4_posthoc_slot_time.py for the
Protocol v5 `cap_configured` and `occupancy_reconstruction` gates; docs/PROTOCOL_V5_DRAFT.md §5.1).

A gateway slot is held over [t_sent, t_terminal). k(t) is the piecewise-constant in-flight count; releases sort
before admissions at equal times. The sampled check compares k(t) with the gateway's own `gw_inflight` count at the
time of the gateway read: `t_gw_rel_s` when recorded (v5 runs), otherwise `t_rel_s` + the frozen 0.15 s scraper offset
measured in v4 (the scraper stamped t_rel_s before fetching vLLM and GPU metrics).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

V4_SCRAPE_OFFSET_S = 0.15
MIN_RECON_EXACT_FRACTION = 0.90
# timestamp-alignment validation (v5): agreement is scanned over lags around the gateway-read time; the alignment is
# validated when the best lag is within +-MAX_ALIGNMENT_LAG_S of 0 (ties resolved toward 0)
ALIGNMENT_LAGS_S = tuple(round(-0.30 + 0.025 * i, 3) for i in range(25))
MAX_ALIGNMENT_LAG_S = 0.05


def occupancy_steps(req: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    r = req[req["t_sent"].notna() & req["t_terminal"].notna()]
    ev = np.concatenate([np.stack([r["t_sent"].to_numpy(float), np.ones(len(r))], 1),
                         np.stack([r["t_terminal"].to_numpy(float), -np.ones(len(r))], 1)])
    ev = ev[np.lexsort((ev[:, 1], ev[:, 0]))]
    return ev[:, 0], np.cumsum(ev[:, 1])


def k_at(times: np.ndarray, k: np.ndarray, t: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(times, t, side="right") - 1
    return np.where(idx >= 0, k[np.clip(idx, 0, None)], 0) if len(times) else np.zeros(len(t))


def reconstruction(req: pd.DataFrame, ts: pd.DataFrame | None) -> dict:
    """Rebuilt max in-flight, and agreement of rebuilt k(t) with the sampled gateway count (samples up to the last
    terminal event)."""
    times, k = occupancy_steps(req)
    out: dict = {"occ_recon_max": int(k.max()) if len(k) else 0, "occ_recon_exact_frac": None,
                 "occ_recon_time_basis": None, "gw_inflight_max": None, "scrape_gw_offset_median_s": None,
                 "occ_recon_best_lag_s": None}
    if ts is None or not len(ts) or "gw_inflight" not in ts:
        return out
    out["gw_inflight_max"] = int(ts["gw_inflight"].max())
    if "t_gw_rel_s" in ts and ts["t_gw_rel_s"].notna().all():
        t, basis = ts["t_gw_rel_s"].to_numpy(float), "t_gw_rel_s"
    else:
        t, basis = ts["t_rel_s"].to_numpy(float) + V4_SCRAPE_OFFSET_S, f"t_rel_s+{V4_SCRAPE_OFFSET_S}"
    g = ts["gw_inflight"].to_numpy()
    tmax = times.max() if len(times) else -np.inf

    def agree(tt: np.ndarray) -> float | None:
        m = tt <= tmax
        return float((k_at(times, k, tt[m]) == g[m]).mean()) if m.any() else None

    out["occ_recon_exact_frac"] = agree(t)
    out["occ_recon_time_basis"] = basis if out["occ_recon_exact_frac"] is not None else None
    if basis == "t_gw_rel_s":
        out["scrape_gw_offset_median_s"] = float(np.median(ts["t_gw_rel_s"] - ts["t_rel_s"]))
        scan: dict[float, float] = {}
        for lag in ALIGNMENT_LAGS_S:
            v = agree(t + lag)
            if v is not None:
                scan[lag] = v
        if scan:
            best = max(scan.values())
            out["occ_recon_best_lag_s"] = min((lag for lag, v in scan.items() if v == best), key=abs)
    return out
