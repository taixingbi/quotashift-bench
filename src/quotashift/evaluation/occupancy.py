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
                 "occ_recon_time_basis": None, "gw_inflight_max": None}
    if ts is None or not len(ts) or "gw_inflight" not in ts:
        return out
    out["gw_inflight_max"] = int(ts["gw_inflight"].max())
    if "t_gw_rel_s" in ts and ts["t_gw_rel_s"].notna().all():
        t, basis = ts["t_gw_rel_s"].to_numpy(float), "t_gw_rel_s"
    else:
        t, basis = ts["t_rel_s"].to_numpy(float) + V4_SCRAPE_OFFSET_S, f"t_rel_s+{V4_SCRAPE_OFFSET_S}"
    m = t <= (times.max() if len(times) else -np.inf)
    if m.any():
        out["occ_recon_exact_frac"] = float((k_at(times, k, t[m]) == ts["gw_inflight"].to_numpy()[m]).mean())
        out["occ_recon_time_basis"] = basis
    return out
