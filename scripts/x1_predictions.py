"""X1-H5 FCFS predictions (docs/PROTOCOL_X1_CROSS_PLATFORM_DRAFT.md rev 4, section 6). Written and pinned at X1 Freeze
Commit 3, BEFORE any main-stage run of the platform.

    uv run python scripts/x1_predictions.py --platform g0m0 --cal-b reports/x1/g0m0/calB --main experiments/x1/g0m0/main \
        --out experiments/x1/g0m0/FCFS_PREDICTIONS.json

Sources (and nothing else):
  hold-time pools  calibration-B runs of THIS platform (seeds 7003-7007), per (operating point, comparison, arm, class)
  schedules        the platform's main-stage YAMLs (seeds 8000-8023), drawn by the harness's own trace generator
Main-stage results are never read; the script refuses if any exist for the platform (leakage guard).

Code path: the FROZEN v5 predictor's `holds`, `pool_of`, `predict` (scripts/v5_fcfs_predictions.py, imported unchanged):
single global FCFS queue with C slots, hold times resampled per request class, MC = 200 draws, fixed RNG entropy.
Predicted cells (X1-H5): X-a (low, C = 8), X-b (low, C = 32; uses the low C = 8 pools), X-e (high, C = 8); both arms.
Tolerances: leave-one-seed-out over the calibration-B seeds of the same point/comparison/arm at C = 8:
  tau_abs = max(5 ms, q95 |err|);  rho = q95 |err| / obs over LOSO runs with obs >= 5 ms
  (fallback rho = the frozen v5 value 0.3491564644530319 if fewer than 3 such runs; recorded as such)
Seed rule / cell rule / pass rule exactly as v5 H3 (`score_fcfs`). No error direction is preregistered.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import v5_fcfs_predictions as v5p  # noqa: E402  (frozen; read-only import)

RNG_ENTROPY = 81000                     # fixed; part of the X1 frozen spec
V5_RHO_FALLBACK = 0.3491564644530319    # experiments/v5/FCFS_PREDICTIONS.json tolerances.rho_rel
PREDICTED = {"Xa": "low", "Xb": "low", "Xe": "high"}   # block -> pool operating point


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cal_b_runs(cal_b: Path, plat: str) -> dict[tuple[str, str, str], list[tuple[int, Path]]]:
    """(point, comparison, arm) -> [(seed, run dir)] from calibration-B report manifests."""
    out: dict[tuple[str, str, str], list[tuple[int, Path]]] = {}
    for rep in sorted(p for p in cal_b.iterdir() if (p / "manifest.json").exists()):
        parts = rep.name.removeprefix(f"x1_{plat}_calB_").rsplit("_", 2)       # comp, point, C8
        comp, point = parts[0], parts[1]
        man = json.loads((rep / "manifest.json").read_text())
        for arm, seeds in man["run_dirs"].items():
            out.setdefault((point, comp, arm), []).extend(
                (int(s), v5p._resolve(d)) for s, d in sorted(seeds.items()))
    return out


def loso(runs: dict[tuple[str, str, str], list[tuple[int, Path]]], rng: np.random.Generator) -> dict:
    rows = []
    for (point, comp, arm), lst in sorted(runs.items()):
        for seed, run in lst:
            r = v5p.holds(run)
            obs = float(((r.t_sent - r.t_offered)[r.workload_class == "victim"]).mean() * 1000)
            pool = v5p.pool_of(lst, exclude_seed=seed)
            pr = v5p.predict(r.t_offered.to_numpy(), (r.workload_class == "victim").to_numpy(), pool, 8, rng,
                             float(r.t_terminal.max()), draws=50)
            rows.append({"point": point, "comparison": comp, "arm": arm, "seed": seed, "obs_ms": obs,
                         "pred_ms": pr["victim_queue_mean_ms"], "err_ms": pr["victim_queue_mean_ms"] - obs})
    ae = np.array([abs(r["err_ms"]) for r in rows])
    big = [abs(r["err_ms"]) / r["obs_ms"] for r in rows if r["obs_ms"] >= 5.0]
    rho, src = (float(np.quantile(big, 0.95)), "loso") if len(big) >= 3 else (V5_RHO_FALLBACK, "v5_fallback")
    return {"n_runs": len(rows), "tau_abs_ms": max(5.0, float(np.quantile(ae, 0.95))) if len(ae) else 5.0,
            "rho_rel": rho, "rho_source": src, "n_obs_ge_5ms": len(big), "runs": rows}


def build(plat: str, cal_b: Path, main_dir: Path, results_root: Path, rng_entropy: int = RNG_ENTROPY) -> dict:
    from quotashift.local import _paired_traces_raw
    from quotashift.scenario import load_scenario

    if results_root.exists() and any(p.name.startswith(f"x1_{plat}_X") for p in results_root.iterdir()):
        raise SystemExit(f"leakage guard: main-stage results for {plat} exist; predictions must precede the main stage")
    rng = np.random.default_rng(np.random.SeedSequence(rng_entropy))
    runs = cal_b_runs(cal_b, plat)
    inputs = {str(p / f): _sha(p / f) for lst in runs.values() for _, p in lst
              for f in ("requests.parquet",) if (p / f).exists()}
    pools = {k: v5p.pool_of(v) for k, v in runs.items()}
    tol = loso(runs, rng)
    cells: dict = {}
    for y in sorted(main_dir.glob(f"x1_{plat}_X*.yaml")):
        block = y.stem.split("_")[2]
        if block not in PREDICTED:
            continue
        sc = load_scenario(y)
        point, cap = PREDICTED[block], sc.safety.max_global_inflight
        comp = "decode_vs_short"
        ent: dict = {"file": y.name, "block": block, "C": cap, "point": point, "comparison": comp, "seeds": {}}
        for seed in range(sc.seed, sc.seed + sc.comparison.repetitions):
            atk, ctl, _ = _paired_traces_raw(sc, seed)
            ent["seeds"][str(seed)] = {}
            for arm, tr in (("attack", atk), ("control", ctl)):
                arr = np.array([it.request.arrival_time_s for it in tr])
                vic = np.array([it.request.workload_class == "victim" for it in tr])
                pr = v5p.predict(arr, vic, pools[(point, comp, arm)], cap, rng, float(sc.runtime_seconds))
                pr["tolerance_ms"] = max(tol["tau_abs_ms"], tol["rho_rel"] * pr["victim_queue_mean_ms"])
                ent["seeds"][str(seed)][arm] = pr
        for arm in ("attack", "control"):
            m = float(np.mean([ent["seeds"][s][arm]["victim_queue_mean_ms"] for s in ent["seeds"]]))
            ent[f"{arm}_cell_victim_queue_mean_ms"] = m
            ent[f"{arm}_tolerance_cell_ms"] = max(5.0, tol["rho_rel"] * m)
        cells[y.stem] = ent
    return {"status": "X1-H5 predictions; pinned at X1 Freeze Commit 3 before any main-stage run",
            "platform": plat, "rng_entropy": rng_entropy, "model": {"code": "scripts/v5_fcfs_predictions.py (frozen)",
                                                                   "discipline": "single global FCFS, C slots",
                                                                   "mc_draws": v5p.MC},
            "pool_inputs_sha256": inputs, "tolerances": {k: v for k, v in tol.items() if k != "runs"},
            "loso_runs": tol["runs"], "cells": cells}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", required=True)
    ap.add_argument("--cal-b", required=True)
    ap.add_argument("--main", required=True)
    ap.add_argument("--results-root", default=str(REPO / "results"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        raise SystemExit(f"refusing to overwrite {out} (predictions are written once, before the main stage)")
    res = build(a.platform, Path(a.cal_b), Path(a.main), Path(a.results_root))
    out.write_text(json.dumps(res, indent=1, default=float) + "\n")
    print(f"{len(res['cells'])} predicted cells; tolerances {res['tolerances']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
