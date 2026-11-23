"""POST-HOC EXPLORATORY (not pre-registered): concurrency-slot occupancy analysis of the Protocol v4 R1–R3 raw runs.

    uv run python scripts/v4_posthoc_slot_time.py [--out reports/v4/posthoc_slot_time]

Read-only on results/ and reports/v4/; writes only under --out. Pre-registered v4 results and classifications are not
touched. Every output column is tagged in COLUMN_KIND as
  measured  - directly from per-request harness timestamps (monotonic clock) or engine/gateway scrapes
  derived   - deterministic function of measured timestamps (e.g. occupancy reconstructed from send/terminal times)
  estimate  - model-based counterfactual (FCFS replay of measured hold times at other caps); assumptions stated
Gateway slot = the interval [t_sent, t_terminal) of a request admitted by the gateway (the gateway dispatches on t_sent and
releases on the terminal event). On the direct path there is no gateway; the same interval is backend concurrency, and the
cap-8 threshold is used only as a reference.
"""

from __future__ import annotations

import argparse
import heapq
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

REPO = Path(__file__).resolve().parents[1]
REF_CAP = 8
COUNTERFACTUAL_CAPS = (8, 16, 32)

COLUMN_KIND = {
    "hold_*": "measured", "competitor_slot_s": "measured", "victim_slot_s": "measured",
    "slot_s_per_1k_auth_tokens": "measured", "occ_*": "derived", "frac_time_at_ref_cap": "derived",
    "sat_episode_*": "derived", "victim_arrivals_during_saturation": "derived", "victim_queue_*": "measured",
    "spearman_queue_vs_occupancy": "derived", "recon_vs_scrape_*": "derived (validation)",
    "slot_demand_fraction": "derived", "fcfs_cap*": "estimate", "engine_waiting_*": "measured (sampled ~0.7 s)",
}


def intervals(req: pd.DataFrame) -> pd.DataFrame:
    r = req[req.t_sent.notna() & req.t_terminal.notna()].copy()
    r["hold_s"] = r.t_terminal - r.t_sent
    return r


def occupancy_steps(r: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Piecewise-constant in-flight count k(t): returns (times, k after each time)."""
    ev = np.concatenate([np.stack([r.t_sent.values, np.ones(len(r))], 1), np.stack([r.t_terminal.values, -np.ones(len(r))], 1)])
    ev = ev[np.lexsort((ev[:, 1], ev[:, 0]))]  # releases before admissions at equal times
    return ev[:, 0], np.cumsum(ev[:, 1])


def k_at(times: np.ndarray, k: np.ndarray, t: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(times, t, side="right") - 1
    return np.where(idx >= 0, k[np.clip(idx, 0, None)], 0)


def time_weighted(times: np.ndarray, k: np.ndarray, t0: float, t1: float) -> dict[int, float]:
    edges = np.concatenate([[t0], times[(times > t0) & (times < t1)], [t1]])
    mids = (edges[:-1] + edges[1:]) / 2
    dur = np.diff(edges)
    kv = k_at(times, k, mids)
    out: dict[int, float] = {}
    for kk, d in zip(kv, dur, strict=True):
        out[int(kk)] = out.get(int(kk), 0.0) + float(d)
    tot = sum(out.values())
    return {kk: v / tot for kk, v in sorted(out.items())}


def episodes(times: np.ndarray, k: np.ndarray, thr: int) -> list[tuple[float, float]]:
    eps, start = [], None
    for t, kk in zip(times, k, strict=True):
        if kk >= thr and start is None:
            start = t
        elif kk < thr and start is not None:
            eps.append((start, t))
            start = None
    return eps


def fcfs_replay(r: pd.DataFrame, cap: int) -> np.ndarray:
    """ESTIMATE: global FCFS with `cap` slots, arrivals = t_offered, service = measured hold time (assumed cap-invariant)."""
    order = np.argsort(r.t_offered.values, kind="stable")
    free = [0.0] * cap
    heapq.heapify(free)
    q = np.zeros(len(r))
    for i in order:
        a, s = r.t_offered.values[i], r.hold_s.values[i]
        f = heapq.heappop(free)
        start = max(a, f)
        q[i] = start - a
        heapq.heappush(free, start + s)
    return q


def spearman(x, y) -> float:  # noqa: ANN001
    """Spearman rank correlation (Pearson on average ranks); no scipy dependency."""
    x, y = pd.Series(np.asarray(x, float)), pd.Series(np.asarray(y, float))
    if len(x) < 3 or x.nunique() < 2 or y.nunique() < 2:
        return float("nan")
    return float(x.rank().corr(y.rank()))


def q95(x) -> float:  # noqa: ANN001
    x = np.asarray(x, float)
    return float(np.percentile(x, 95)) if len(x) else float("nan")


def analyse_run(run_dir: Path, block: str, arm: str, seed: int) -> tuple[dict, pd.DataFrame, pd.DataFrame, dict]:
    cfg = yaml.safe_load((run_dir / "config.resolved.yaml").read_text())
    cap = int(cfg.get("run", {}).get("max_concurrency_cap") or REF_CAP)
    T = float(cfg.get("runtime_seconds") or 120)
    req = pd.read_parquet(run_dir / "requests.parquet")
    ts = pd.read_parquet(run_dir / "metrics_timeseries.parquet")
    r = intervals(req)
    times, k = occupancy_steps(r)
    horizon = float(r.t_terminal.max())
    comp, vic = r[r.workload_class == "competitor"], r[r.workload_class == "victim"]
    occ = time_weighted(times, k, 0.0, T)
    eps = episodes(times, k, REF_CAP)
    dur = np.array([b - a for a, b in eps]) if eps else np.zeros(0)
    # victim arrival state: in-flight count just before the victim's own offer (it is not yet admitted)
    k_arr = k_at(times, k, vic.t_offered.values - 1e-9)
    comp_k = k_at(*occupancy_steps(comp), vic.t_offered.values - 1e-9) if len(comp) else np.zeros(len(vic))
    sat = k_arr >= REF_CAP
    vq = (vic.t_sent - vic.t_offered).values * 1000
    # validation: reconstruction vs sampled gateway in-flight
    sk = k_at(times, k, ts.t_rel_s.values)
    m = ts.t_rel_s.values <= horizon
    err = np.abs(sk[m] - ts.gw_inflight.values[m])
    auth = float((comp.input_token_count + comp.max_output_tokens).sum())
    row = {
        "block": block, "arm": arm, "seed": seed, "path": cfg.get("path", "gateway"), "configured_cap": cap,
        "window_s": T, "horizon_s": horizon,
        "competitor_n": len(comp), "victim_n": len(vic),
        "hold_comp_mean_s": comp.hold_s.mean(), "hold_comp_p50_s": comp.hold_s.median(), "hold_comp_p95_s": q95(comp.hold_s),
        "hold_victim_mean_s": vic.hold_s.mean(), "hold_victim_p95_s": q95(vic.hold_s),
        "competitor_slot_s": comp.hold_s.sum(), "victim_slot_s": vic.hold_s.sum(),
        "slot_s_per_1k_auth_tokens": comp.hold_s.sum() / (auth / 1000) if auth else float("nan"),
        "slot_demand_fraction": (comp.hold_s.sum() + vic.hold_s.sum()) / (REF_CAP * T),
        "occ_mean": sum(kk * p for kk, p in occ.items()), "occ_max": int(k.max()) if len(k) else 0,
        "frac_time_at_ref_cap": sum(p for kk, p in occ.items() if kk >= REF_CAP),
        "sat_episode_n": len(eps), "sat_episode_mean_s": float(dur.mean()) if len(dur) else 0.0,
        "sat_episode_p95_s": q95(dur) if len(dur) else 0.0, "sat_episode_max_s": float(dur.max()) if len(dur) else 0.0,
        "sat_episode_total_s": float(dur.sum()),
        "victim_arrivals_during_saturation": float(sat.mean()) if len(sat) else float("nan"),
        "victim_queue_p95_ms": q95(vq), "victim_queue_mean_ms": float(vq.mean()),
        "victim_queue_mean_ms_if_saturated": float(vq[sat].mean()) if sat.any() else float("nan"),
        "victim_queue_mean_ms_if_not": float(vq[~sat].mean()) if (~sat).any() else float("nan"),
        "victim_queue_gt_500ms_n": int((vq > 500).sum()),
        "victim_user_ttft_p95_ms": q95((vic.t_first_token - vic.t_offered) * 1000),
        "victim_backend_ttft_p95_ms": q95((vic.t_first_token - vic.t_sent) * 1000),
        "spearman_queue_vs_occupancy": spearman(vq, k_arr),
        "spearman_queue_vs_comp_inflight": spearman(vq, comp_k),
        "recon_vs_scrape_mean_abs_err": float(err.mean()) if len(err) else float("nan"),
        "recon_vs_scrape_exact_frac": float((err == 0).mean()) if len(err) else float("nan"),
        "engine_waiting_max": float(ts.num_requests_waiting.max()), "engine_waiting_mean": float(ts.num_requests_waiting.mean()),
        "engine_running_max": float(ts.num_requests_running.max()),
    }
    if row["path"] == "gateway":
        for c in COUNTERFACTUAL_CAPS:
            qc = fcfs_replay(r, c)
            vmask = (r.workload_class == "victim").values
            row[f"fcfs_cap{c}_victim_queue_p95_ms"] = q95(qc[vmask] * 1000)
            row[f"fcfs_cap{c}_victim_queue_mean_ms"] = float(qc[vmask].mean() * 1000)
    vrows = pd.DataFrame({"block": block, "arm": arm, "seed": seed, "t_offered": vic.t_offered.values,
                          "queue_ms": vq, "user_ttft_ms": ((vic.t_first_token - vic.t_offered) * 1000).values,
                          "backend_ttft_ms": ((vic.t_first_token - vic.t_sent) * 1000).values,
                          "inflight_at_arrival": k_arr, "comp_inflight_at_arrival": comp_k, "saturated_at_arrival": sat})
    erows = pd.DataFrame([{"block": block, "arm": arm, "seed": seed, "start_s": a, "end_s": b, "dur_s": b - a} for a, b in eps])
    return row, vrows, erows, {"block": block, "arm": arm, "seed": seed, **{f"k{kk}": p for kk, p in occ.items()}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "reports" / "v4" / "posthoc_slot_time"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows, vic, eps, hist = [], [], [], []
    for stage in ("r1", "r2", "r3"):
        for rep in sorted((REPO / "reports" / "v4" / stage).iterdir()):
            if not (rep / "manifest.json").exists():
                continue
            man = json.loads((rep / "manifest.json").read_text())
            for arm, by_seed in man["run_dirs"].items():
                for seed, d in by_seed.items():
                    run = REPO / Path(d).relative_to(Path(d).parents[2]) if not Path(d).exists() else Path(d)
                    row, v, e, h = analyse_run(run, rep.name, arm, int(seed))
                    row["stage"] = stage
                    rows.append(row), vic.append(v), eps.append(e), hist.append(h)
    per_run = pd.DataFrame(rows)
    per_run.to_csv(out / "per_run.csv", index=False)
    pd.concat(vic).to_csv(out / "victim_requests.csv", index=False)
    pd.concat([e for e in eps if len(e)]).to_csv(out / "saturation_episodes.csv", index=False)
    pd.DataFrame(hist).fillna(0.0).to_csv(out / "occupancy_distribution.csv", index=False)
    (out / "column_kinds.json").write_text(json.dumps(COLUMN_KIND, indent=1) + "\n")
    print(f"{len(per_run)} runs -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
