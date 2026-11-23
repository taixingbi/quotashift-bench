"""Protocol v5 H3: FROZEN quantitative FCFS predictions of victim gateway queueing at C = 8, 16, 32.

    uv run python scripts/v5_fcfs_predictions.py            # writes experiments/v5/FCFS_PREDICTIONS.json (refuses to overwrite)
    uv run python scripts/v5_fcfs_predictions.py --check    # recompute; exit 1 if it differs from the frozen file

The predictions are written BEFORE any v5 GPU run and are part of the v5 freeze commit. Model (an ESTIMATE):
  - arrivals   = the exact v5 schedule of each (cell, arm, seed) (tokenizer-independent: arrival times + token plan);
  - service    = per-request gateway slot hold [t_sent, t_terminal) resampled (with replacement, per request class) from
                 a v4 hold-time pool measured at C = 8 through the gateway, for the matching (shape, load, arm);
  - discipline = one global FCFS queue with C slots (the v4 gateway; post-hoc v4 replay reproduced measured queueing);
  - assumption = hold times are cap-invariant (see PROTOCOL_V5_DRAFT §3.3 for why this biases predictions low).

Leakage guard (PROTOCOL_V5_DRAFT §3.4): the ONLY permitted inputs are v4 runs with path == gateway and
max_global_inflight == 8. Direct-vLLM (R3) runs are excluded because their observed concurrency (max 9–14 at L = 200)
never reached 16, so they are de-facto measurements of the C = 16/32 cells. The script fails if any input violates this
or if any v5 result directory exists. Every input file is pinned by SHA-256 in the output.

Tolerances come only from v4 C = 8 data: leave-one-seed-out (LOSO) cross-validation of this exact predictor on the 30
v4 R1 L = 200 arms (each run's own arrivals, holds resampled from the OTHER seeds of the same arm).
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_v5  # noqa: E402

OUT = REPO / "experiments" / "v5" / "FCFS_PREDICTIONS.json"
CAPS = (8, 16, 32)
MC = 200                    # Monte Carlo draws of the hold-time resample per (cell, arm, seed, C)
RNG_ENTROPY = 50050         # fixed; part of the frozen spec
SLOW_MS = 500.0

# v5 (comparison, load, arm) -> v4 C = 8 gateway source (stage dir, report-name prefix, arm). Only these are read.
POOLS: dict[tuple[str, int, str], tuple[str, str, str]] = {
    ("decode_vs_short", 200, "attack"): ("r1", "v4_r1_decode_vs_short_L200", "attack"),
    ("decode_vs_short", 200, "control"): ("r1", "v4_r1_decode_vs_short_L200", "control"),
    ("prefill_vs_short", 200, "attack"): ("r1", "v4_r1_prefill_vs_short_L200", "attack"),
    ("prefill_vs_short", 200, "control"): ("r1", "v4_r1_prefill_vs_short_L200", "control"),
    ("aa_ind", 200, "attack"): ("r1", "v4_r1_aa_short_L200", "*"),
    ("aa_ind", 200, "control"): ("r1", "v4_r1_aa_short_L200", "*"),
    ("decode_vs_short", 400, "attack"): ("calibration", "v4_cal_D_L400", "*"),
    ("decode_vs_short", 400, "control"): ("calibration", "v4_cal_S_L400", "*"),
    ("aa_ind", 400, "attack"): ("calibration", "v4_cal_S_L400", "*"),
    ("aa_ind", 400, "control"): ("calibration", "v4_cal_S_L400", "*"),
}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _resolve(d: str) -> Path:
    p = Path(d)
    return p if p.exists() else REPO / p.relative_to(p.parents[2])


def v4_runs(stage: str, prefix: str, arm: str) -> list[tuple[int, Path]]:
    """(seed, run_dir) of the v4 report whose name is exactly `prefix` (not a *_direct variant)."""
    out = []
    for rep in sorted((REPO / "reports" / "v4" / stage).iterdir()):
        if rep.name != prefix or not (rep / "manifest.json").exists():
            continue
        man = json.loads((rep / "manifest.json").read_text())
        for a, by_seed in man["run_dirs"].items():
            if arm in ("*", a):
                out += [(int(s), _resolve(d)) for s, d in by_seed.items()]
    if not out:
        raise SystemExit(f"no v4 runs for {stage}/{prefix}/{arm}")
    return out


def assert_c8_gateway(run: Path) -> None:
    """Leakage guard: refuse any input that is not a v4 gateway run at C = 8."""
    cfg = yaml.safe_load((run / "config.resolved.yaml").read_text())
    path, cap = cfg.get("path", "gateway"), int((cfg.get("run") or {}).get("max_concurrency_cap") or -1)
    if path != "gateway" or cap != 8 or "direct" in run.parent.name:
        raise SystemExit(f"leakage guard: {run} is path={path} cap={cap}; only v4 gateway C=8 runs are allowed")


def holds(run: Path) -> pd.DataFrame:
    r = pd.read_parquet(run / "requests.parquet")
    r = r[r.t_sent.notna() & r.t_terminal.notna()].copy()
    r["hold_s"] = r.t_terminal - r.t_sent
    return r


def fcfs(arrival: np.ndarray, service: np.ndarray, cap: int) -> tuple[np.ndarray, np.ndarray]:
    """Global FCFS with `cap` slots. Returns (queue wait, start) per request (arrival order preserved)."""
    order = np.argsort(arrival, kind="stable")
    free = [0.0] * cap
    q, st = np.zeros(len(arrival)), np.zeros(len(arrival))
    for i in order:
        f = heapq.heappop(free)
        s = max(arrival[i], f)
        q[i], st[i] = s - arrival[i], s
        heapq.heappush(free, s + service[i])
    return q, st


def frac_time_at_cap(start: np.ndarray, service: np.ndarray, cap: int, horizon: float) -> float:
    ev = np.concatenate([np.stack([start, np.ones(len(start))], 1), np.stack([start + service, -np.ones(len(start))], 1)])
    ev = ev[np.lexsort((ev[:, 1], ev[:, 0]))]
    k = np.cumsum(ev[:, 1])
    t = np.append(ev[:, 0], horizon)
    dur = np.clip(np.minimum(t[1:], horizon) - np.minimum(t[:-1], horizon), 0, None)
    return float(dur[k >= cap].sum() / horizon)


def stats(q_v: np.ndarray) -> dict[str, float]:
    ms = q_v * 1000
    return {"victim_queue_mean_ms": float(ms.mean()), "victim_queue_p95_ms": float(np.percentile(ms, 95)),
            "victim_frac_queue_gt_500ms": float((ms > SLOW_MS).mean())}


def predict(arrival: np.ndarray, is_victim: np.ndarray, pool: dict[str, np.ndarray], cap: int, rng: np.random.Generator,
            horizon: float, draws: int = MC) -> dict[str, float]:
    acc: dict[str, list[float]] = {}
    for _ in range(draws):
        svc = np.where(is_victim, rng.choice(pool["victim"], len(arrival)), rng.choice(pool["competitor"], len(arrival)))
        q, st = fcfs(arrival, svc, cap)
        for k, v in {**stats(q[is_victim]), "frac_time_at_cap": frac_time_at_cap(st, svc, cap, horizon)}.items():
            acc.setdefault(k, []).append(v)
    out: dict[str, float] = {}
    for k, v in acc.items():
        a = np.asarray(v)
        out[k] = float(a.mean())
        out[f"{k}_pi90"] = [float(np.percentile(a, 5)), float(np.percentile(a, 95))]  # type: ignore[assignment]
    return out


def pool_of(runs: list[tuple[int, Path]], exclude_seed: int | None = None) -> dict[str, np.ndarray]:
    hs = pd.concat([holds(p) for s, p in runs if s != exclude_seed])
    return {c: hs.loc[hs.workload_class == c, "hold_s"].to_numpy() for c in ("victim", "competitor")}


def loso_validation(rng: np.random.Generator) -> dict:
    """C = 8 cross-validation on v4 R1 L = 200 (only v4 data): per-run abs error of the victim mean gateway queue."""
    rows = []
    for (comp, load, arm), (stage, prefix, src_arm) in POOLS.items():
        if load != 200 or (comp == "aa_ind" and arm == "control"):
            continue
        runs = v4_runs(stage, prefix, src_arm)
        for seed, run in runs:
            r = holds(run)
            obs = float(((r.t_sent - r.t_offered)[r.workload_class == "victim"]).mean() * 1000)
            pr = predict(r.t_offered.to_numpy(), (r.workload_class == "victim").to_numpy(),
                         pool_of(runs, exclude_seed=seed), 8, rng, float(r.t_terminal.max()), draws=50)
            rows.append({"source": prefix, "arm": run.parent.name.rsplit("__", 1)[-1], "seed": seed, "obs_ms": obs,
                         "pred_ms": pr["victim_queue_mean_ms"], "err_ms": pr["victim_queue_mean_ms"] - obs,
                         "covered": pr["victim_queue_mean_ms_pi90"][0] <= obs <= pr["victim_queue_mean_ms_pi90"][1]})
    d = pd.DataFrame(rows)
    ae = d.err_ms.abs()
    return {"n_runs": len(d), "mae_ms": float(ae.mean()), "bias_ms": float(d.err_ms.mean()),
            "rmse_ms": float(np.sqrt((d.err_ms ** 2).mean())), "abs_err_q95_ms": float(ae.quantile(0.95)),
            "rel_abs_err_median": float((ae / d.obs_ms.clip(lower=1.0)).median()),
            "rel_abs_err_q95_obs_ge_5ms": float((ae / d.obs_ms)[d.obs_ms >= 5.0].quantile(0.95)),
            "obs_range_ms": [float(d.obs_ms.min()), float(d.obs_ms.max())],
            "pi90_coverage": float(d.covered.mean()), "runs": d.round(3).to_dict(orient="records")}


def build(rng_entropy: int = RNG_ENTROPY) -> dict:
    from quotashift.local import _paired_traces_raw
    from quotashift.scenario import load_scenario

    if any(p.name.startswith("v5_") for p in (REPO / "results").iterdir()):
        raise SystemExit("leakage guard: v5 results exist; predictions must be frozen before any v5 run")
    rng = np.random.default_rng(np.random.SeedSequence(rng_entropy))
    inputs: dict[str, str] = {}
    pools: dict[tuple[str, int, str], dict[str, np.ndarray]] = {}
    for key, src in POOLS.items():
        runs = v4_runs(*src)
        for _, run in runs:
            assert_c8_gateway(run)
            for f in ("requests.parquet", "config.resolved.yaml"):
                inputs[str((run / f).relative_to(REPO))] = _sha(run / f)
        pools[key] = pool_of(runs)
    val = loso_validation(rng)
    tau_abs = max(5.0, val["abs_err_q95_ms"])
    rho = val["rel_abs_err_q95_obs_ge_5ms"]
    lo_ok, hi_ok = val["obs_range_ms"]
    cells: dict = {}
    files = {p: t for p, t in build_v5.build().items() if "smoke" not in p.parts and not p.stem.endswith("_direct")}
    for p in sorted(files):
        sc = load_scenario(p)
        comp, load = p.stem.split("_L")[0].removeprefix("v5_"), int(p.stem.split("_L")[1].split("_")[0])
        cap = sc.safety.max_global_inflight
        ent: dict = {"file": str(p.relative_to(REPO)), "C": cap, "L": load, "comparison": comp, "seeds": {}}
        for seed in range(sc.seed, sc.seed + sc.comparison.repetitions):
            atk, ctl, _ = _paired_traces_raw(sc, seed)
            ent["seeds"][str(seed)] = {}
            for arm, tr in (("attack", atk), ("control", ctl)):
                arr = np.array([it.request.arrival_time_s for it in tr])
                vic = np.array([it.request.workload_class == "victim" for it in tr])
                ent["seeds"][str(seed)][arm] = predict(arr, vic, pools[(comp, load, arm)], cap, rng, float(sc.runtime_seconds))
        for arm in ("attack", "control"):
            m = [ent["seeds"][s][arm]["victim_queue_mean_ms"] for s in ent["seeds"]]
            ent[f"{arm}_cell_victim_queue_mean_ms"] = float(np.mean(m))
        ent["delta_cell_victim_queue_mean_ms"] = ent["attack_cell_victim_queue_mean_ms"] - ent["control_cell_victim_queue_mean_ms"]
        for arm in ("attack", "control"):
            pc = ent[f"{arm}_cell_victim_queue_mean_ms"]
            ent[f"{arm}_tolerance_cell_ms"] = max(5.0, rho * pc)
            for s in ent["seeds"]:
                ps = ent["seeds"][s][arm]["victim_queue_mean_ms"]
                ent["seeds"][s][arm]["tolerance_ms"] = max(tau_abs, rho * ps)
        # a cell is inside the validated envelope only at L = 200 and predicted means within the LOSO observed range
        ent["validated_envelope"] = bool(load == 200 and all(
            ent[f"{a}_cell_victim_queue_mean_ms"] <= hi_ok for a in ("attack", "control")))
        cells[p.stem] = ent
        print(f"{p.stem:34s} pred victim queue mean atk {ent['attack_cell_victim_queue_mean_ms']:8.2f} ms  "
              f"ctl {ent['control_cell_victim_queue_mean_ms']:8.2f} ms", flush=True)
    return {
        "status": "FROZEN with the v5 freeze commit; written before any v5 GPU run",
        "kind": "estimate (FCFS replay, cap-invariant v4 C=8 hold times)",
        "model": {"discipline": "single global FCFS, C slots", "arrivals": "exact v5 schedule (tokenizer-independent)",
                  "service": "per-class resample of v4 C=8 gateway hold times [t_sent, t_terminal)",
                  "mc_draws": MC, "rng_entropy": rng_entropy, "slow_threshold_ms": SLOW_MS},
        "leakage_guard": {"allowed_inputs": "v4 runs with path == gateway and cap == 8",
                          "excluded": "all v4 R3 direct runs (observed max concurrency 9–14 at L=200: cap never binds, "
                                      "so they are de-facto C=16/32 measurements); all v5 data (none exists)",
                          "pools": {f"{c}|L{lo}|{a}": "/".join(s) for (c, lo, a), s in POOLS.items()},
                          "input_sha256": inputs},
        "validation_c8_loso": val,
        "tolerances": {
            "tau_abs_ms": tau_abs, "rho_rel": rho, "validated_obs_range_ms": [lo_ok, hi_ok],
            "seed_rule": "|obs - pred| <= max(tau_abs, rho * pred) per (cell, arm, seed); tau_abs = max(5 ms, q95 "
                         "|LOSO err|), rho = q95 |LOSO err|/obs over LOSO runs with obs >= 5 ms",
            "cell_rule": "|mean_obs - mean_pred| <= max(5 ms, rho * mean_pred) over the 10 seeds, per arm",
            "pass_rule": "a (cell, arm) prediction PASSES iff the cell rule holds AND >= 8/10 seeds meet the seed rule",
            "envelope": "cells outside the validated envelope (L = 400, or predicted mean above the LOSO range) are "
                        "scored and reported but labelled extrapolated and excluded from the H3 verdict",
            "pi90_coverage": "descriptive only (LOSO coverage was 0.57: the interval reflects hold resampling only)",
        },
        "cells": cells,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    out = Path(a.out)
    if not a.check and out.exists():
        print(f"refusing to overwrite frozen predictions {out}", file=sys.stderr)
        return 3
    res = build()
    text = json.dumps(res, indent=1, sort_keys=True) + "\n"
    if a.check:
        same = out.exists() and out.read_text() == text
        print("FCFS predictions reproduce exactly" if same else "FCFS predictions DIFFER from the frozen file")
        return 0 if same else 1
    out.write_text(text)
    print(f"wrote {out}: {len(res['cells'])} cells")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
