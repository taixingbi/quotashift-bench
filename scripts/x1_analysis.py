"""Protocol X1 analysis (docs/PROTOCOL_X1_CROSS_PLATFORM_DRAFT.md rev 4, section 5). FROZEN with X1 Freeze Commit 1.

    uv run python scripts/x1_analysis.py --reports reports/x1 --predictions experiments/x1 --out reports/x1

Inputs: one experiment report per (platform, block) named x1_<plat>_<block>_<comparison>_<point>_<C8|C32|direct>
(written by the harness / scripts/x1_stage.py), the platform's frozen X1-H5 predictions
(experiments/x1/<plat>/FCFS_PREDICTIONS.json, Freeze Commit 3) and, optionally, the platform's host-telemetry JSONL
(scripts/x1_host_sampler.py) for the per-cell host flags (X1-D2).

Every decision rule is the FROZEN v5 implementation, imported unchanged from scripts/v5_analysis.py:
  mean_ci / classify_cell (geo-mean ratio, 95% t CI), p_superiority (one-sided vs log 1.25), p_tost ([0.8, 1.25]),
  holm, threshold_above_noise, score_fcfs (H5), engine_queue_negligible (v5 section 5.2), stratum, attack_slo_degradation,
  and the per-seed loader helpers (_resolve_run, _victims, slot_time, _engine_queue).
The only X1-specific rule is X1-H4's backend TOST band [0.9, 1.1] (rev 4), computed with the frozen v5 t_cdf.

Families (rev 4): F-X1 = X1-H1 over the 4 platforms (Holm, fixed family, p = 1 if not evaluable);
F-X2 = 4 x X1-H2 + 4 x X1-H3 (Holm over 8). Verdict: GENERALISES iff H1 supported on >= 3/4 AND H2 equivalent on
>= 3/4 AND H4 holds on >= 3/4; ANCHOR-ONLY iff H1 supported only on g0m0; else PARTIAL. No interim looks: real
(non-synthetic) data are analysed only when every expected cell of all four platforms is present.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))
import build_x1  # noqa: E402
import v5_analysis as va  # noqa: E402  (frozen; read-only import)

from quotashift.x1 import preflight as pf  # noqa: E402

CELL_RE = re.compile(r"x1_(g[01]m[01])_(X[a-f])_(decode_vs_short|aa_ind)_(low|high)_(C8|C32|direct)")
PLATFORMS = tuple(build_x1.PLATFORMS)
ALPHA = va.ALPHA
BACKEND_LO, BACKEND_HI = math.log(0.9), math.log(1.1)
ARM_WINDOW_PAD_S = 30.0
X1_VLLM_VERSION = "0.17.1"
# every v5 harness gate must be present in every X1 cell report (protocol_version 5 => the full v5 gate set)
V5_GATES = ("backend_error_rate", "http_400_rate", "admission_rate", "competitor_completion", "primary_metric_present",
            "tokenized_context", "planned_vs_reported_tokens", "provenance", "victim_latency_censoring",
            "arrival_coverage", "realized_output_equals_authorized", "cap_configured", "occupancy_reconstruction",
            "gateway_timestamp_alignment")


# ------------------------------------------------------------------------------------------------ loader
def load_x1_cell(rep: Path) -> dict:
    """One X1 report -> the v5 per-seed table (identical construction to v5_analysis.load_cell; verified by test)."""
    m = CELL_RE.fullmatch(rep.name)
    if not m:
        raise ValueError(f"not an X1 cell report: {rep}")
    plat, block, comp, point, capk = m.groups()
    man = json.loads((rep / "manifest.json").read_text())
    df = pd.read_csv(rep / "summary.csv")
    checks = (man.get("validity") or {}).get("checks") or []
    failed = [c["name"] for c in checks if c.get("severity") == "fail" and not c.get("passed")]
    integrity_ok = bool(checks) and not failed
    C = None if capk == "direct" else int(capk[1:])
    rows = []
    for seed in sorted(int(s) for s in df.seed.unique()):
        a = df[(df.seed == seed) & (df.arm == "attack")].iloc[0]
        c = df[(df.seed == seed) & (df.arm == "control")].iloc[0]
        comp_done = (a.competitor_requests / a.competitor_offered, c.competitor_requests / c.competitor_offered)
        cens = (a.victim_censored_fraction, c.victim_censored_fraction)
        row = {"seed": seed, "integrity_ok": integrity_ok,
               "E": va.execution_feasible(integrity_ok=integrity_ok, completion=comp_done, censoring=cens),
               "Vb": va.baseline_victim_slo_feasible(float(c.victim_slo_success_offered)),
               "competitor_completion": list(map(float, comp_done)), "victim_censored": list(map(float, cens)),
               "log_ratio": math.log(a.victim_user_ttft_mean_ms) - math.log(c.victim_user_ttft_mean_ms),
               "log_ratio_p95": math.log(a.victim_user_ttft_p95_ms) - math.log(c.victim_user_ttft_p95_ms)}
        for arm, r in (("attack", a), ("control", c)):
            run = va._resolve_run(r.run_dir)
            v = va._victims(run)
            row[arm] = {
                "user_ttft_mean_ms": float(r.victim_user_ttft_mean_ms), "user_ttft_p95_ms": float(r.victim_user_ttft_p95_ms),
                "backend_ttft_mean_ms": float(r.victim_backend_ttft_mean_ms),
                "backend_ttft_p95_ms": float(r.victim_backend_ttft_p95_ms),
                "gateway_queue_mean_ms": float(r.victim_gateway_queue_mean_ms),
                "gateway_queue_p95_ms": float(r.victim_gateway_queue_p95_ms),
                "slo_success": float(r.victim_slo_success_offered), "tpot_p95_ms": float(r.victim_tpot_p95_ms),
                **{f"frac_user_ttft_gt_{int(t)}ms": float((v.user_ttft_ms > t).mean()) if len(v) else float("nan")
                   for t in va.TAIL_MS},
                "gpu_dynamic_energy_j_per_realized_tok": (float(r.gpu_dynamic_energy_j) / float(r.realized_tokens)
                                                          if pd.notna(r.gpu_dynamic_energy_j) and r.realized_tokens else None),
                "engine_queue": va._engine_queue(run),
                "slot": va.slot_time(run, C if C is not None else 8),
                "configured_cap": None if pd.isna(r.gw_inflight_cap) else int(r.gw_inflight_cap),
                "path": r.path, "run_dir": str(run),
            }
        rows.append(row)
    return {"cell": rep.name, "platform": plat, "block": block, "comparison": comp, "point": point, "C": C,
            "path": "direct" if C is None else "gateway", "report": str(rep),
            "synthetic_backend": bool(man.get("synthetic_backend")), "failed_gates": failed,
            "server_start": list((man.get("provenance") or {}).get("server_start") or []),
            "provenance": man.get("provenance") or {}, "gates": [c["name"] for c in checks],
            "scenario_id": man.get("scenario_id"), "protocol_version": man.get("protocol_version"),
            "seeds": [r["seed"] for r in rows], "rows": rows}


def expected_cells() -> dict[str, dict[str, str]]:
    return {p: {b: build_x1.cell_id(p, b, comp, point, cap) for b, comp, point, cap, _ in build_x1.BLOCKS}
            for p in PLATFORMS}


def expected_seeds(block: str) -> list[int]:
    n = next(n for b, *_, n in build_x1.BLOCKS if b == block)
    return list(range(build_x1.MAIN_SEED0, build_x1.MAIN_SEED0 + n))


# ------------------------------------------------------------------------------------------------ rules
def summarize(cell: dict) -> dict:
    rows = cell["rows"]
    out = {"stratum": va.stratum([r["E"] for r in rows], [r["Vb"] for r in rows]), "n": len(rows),
           "primary": va.classify_cell([r["log_ratio"] for r in rows]),
           "attack_slo_degradation": va.attack_slo_degradation([r["attack"]["slo_success"] for r in rows],
                                                               [r["control"]["slo_success"] for r in rows])}
    for arm in ("attack", "control"):
        out[f"{arm}_means"] = {k: float(np.mean([r[arm][k] for r in rows])) for k in
                               ("user_ttft_mean_ms", "backend_ttft_mean_ms", "gateway_queue_mean_ms", "slo_success")}
    return out


def backend_tost(cell: dict) -> dict:
    """X1-H4 (rev 4): TOST of the per-seed log backend-TTFT ratio (attack / control) within [log 0.9, log 1.1]."""
    lr = [math.log(r["attack"]["backend_ttft_mean_ms"]) - math.log(r["control"]["backend_ttft_mean_ms"])
          for r in cell["rows"]]
    ci = va.mean_ci(lr)
    if ci.se == 0:
        p = 0.0 if BACKEND_LO < ci.mean < BACKEND_HI else 1.0
    else:
        p = max(1.0 - va.t_cdf((ci.mean - BACKEND_LO) / ci.se, ci.n - 1), va.t_cdf((ci.mean - BACKEND_HI) / ci.se, ci.n - 1))
    return {"p_tost": p, "ratio": math.exp(ci.mean), "n": ci.n}


def engine_negligible(cell: dict) -> dict:
    per = []
    for r in cell["rows"]:
        for arm in ("attack", "control"):
            eq = r[arm]["engine_queue"] or {}
            res = va.engine_queue_negligible(eq.get("sum_s") or 0.0, eq.get("count") or 0.0, eq.get("buckets") or [])
            per.append(res)
    ev = [x for x in per if x.get("evaluable")]
    return {"evaluable": bool(per) and len(ev) == len(per), "all_negligible": bool(ev) and all(x["negligible"] for x in ev),
            "n_arms": len(per)}


def h5_scores(plat_cells: dict[str, dict], preds: dict | None) -> dict:
    if not preds:
        return {"verdict": "not_evaluable", "reason": "no frozen predictions", "scores": {}}
    scores = {}
    for cid, pc in preds["cells"].items():
        block = pc["block"]
        cell = plat_cells.get(block)
        for arm in ("attack", "control"):
            if cell is None or cell["summary"]["stratum"] == "notE":
                scores[f"{cid}/{arm}"] = {"evaluable": False}
                continue
            by_seed = {r["seed"]: r for r in cell["rows"]}
            seeds = sorted(int(s) for s in pc["seeds"] if int(s) in by_seed)
            obs = [by_seed[s][arm]["slot"]["h3_obs_victim_queue_mean_ms"] for s in seeds]
            pred = [pc["seeds"][str(s)][arm]["victim_queue_mean_ms"] for s in seeds]
            tol = [pc["seeds"][str(s)][arm]["tolerance_ms"] for s in seeds]
            sc = va.score_fcfs(pred, obs, tol, pc[f"{arm}_cell_victim_queue_mean_ms"], pc[f"{arm}_tolerance_cell_ms"])
            scores[f"{cid}/{arm}"] = {"evaluable": True, "pred_cell_ms": pc[f"{arm}_cell_victim_queue_mean_ms"],
                                      "obs_cell_ms": float(np.mean(obs)), **sc}
    ev = [s for s in scores.values() if s["evaluable"]]
    verdict = ("not_evaluable" if len(ev) < len(scores) or not ev else
               "supported" if all(s["pass"] for s in ev) else "not_supported")
    return {"verdict": verdict, "scores": scores}


def host_flags(cell: dict, samples: list[dict] | None, offset_s: float = 0.0) -> dict:
    """X1-D2: per arm, slice the platform's 1 Hz host telemetry to the arm window [created, created + 120 s + pad]
    and apply the frozen per-arm gates (host_cpu_headroom / host_ram_headroom; OOM -> fail). Samples are stamped by
    the GPU host; the window (runner clock) is shifted by the Phase-1 clock offset (GPU host minus runner)."""
    if samples is None:
        return {"available": False}
    out = {"available": True, "arms": {}, "flag": False, "oom_fail": False, "clock_offset_s": offset_s}
    for r in cell["rows"]:
        for arm in ("attack", "control"):
            run = Path(r[arm]["run_dir"])
            try:
                t0 = datetime.fromisoformat(json.loads((run / "manifest.json").read_text())["created_wall_utc"]
                                            .replace("Z", "+00:00")).timestamp()
            except (OSError, KeyError, ValueError):
                out["arms"][f"{r['seed']}/{arm}"] = {"status": "no_window"}
                continue
            a0 = t0 + offset_s
            win = [s for s in samples if "ts" in s and a0 <= s["ts"] <= a0 + build_x1.RUNTIME + ARM_WINDOW_PAD_S]
            cpu, ram = pf.cpu_check(win, preflight=False), pf.ram_check(win)
            st = pf.combine(cpu, ram)
            out["arms"][f"{r['seed']}/{arm}"] = {"status": st, "cpu": cpu["status"], "ram": ram["status"]}
            out["flag"] = out["flag"] or st != "pass"
            out["oom_fail"] = out["oom_fail"] or ram.get("oom_kills", 0) > 0
    return out


def analyse(cells: dict[str, dict[str, dict]], preds: dict[str, dict | None],
            host: dict[str, list[dict] | None] | None = None, host_offsets: dict[str, float] | None = None) -> dict:
    """cells: platform -> block -> loaded cell (with 'summary')."""
    host, host_offsets = host or {}, host_offsets or {}
    for pc in cells.values():
        for c in pc.values():
            c["summary"] = summarize(c)
            c["host"] = host_flags(c, host.get(c["platform"]), host_offsets.get(c["platform"], 0.0))
    ident = {p: platform_identity(p, cells.get(p, {})) for p in PLATFORMS}
    srv = {p: server_identity(cells.get(p, {})) for p in PLATFORMS}

    def ok(p: str, b: str, need_vb: bool = True) -> bool:
        c = cells.get(p, {}).get(b)
        if c is None or not ident[p]["passed"] or not srv[p]["passed"]:
            return False          # identity / server-identity failure: the platform's hypotheses are not evaluable
        return c["summary"]["stratum"] == "E&Vb" if need_vb else c["summary"]["stratum"] != "notE"

    p1 = {p: (va.p_superiority([r["log_ratio"] for r in cells[p]["Xa"]["rows"]]) if ok(p, "Xa") else 1.0)
          for p in PLATFORMS}
    h1 = va.holm(p1)
    p2 = {}
    for p in PLATFORMS:
        p2[f"H2_{p}"] = va.p_tost([r["log_ratio"] for r in cells[p]["Xb"]["rows"]]) if ok(p, "Xb") else 1.0
        p2[f"H3_{p}"] = va.p_tost([r["log_ratio"] for r in cells[p]["Xc"]["rows"]]) if ok(p, "Xc") else 1.0
    h23 = va.holm(p2)
    per: dict[str, dict] = {}
    for p in PLATFORMS:
        res: dict = {"role": build_x1.PLATFORMS[p]["role"]}
        res["H1"] = {"evaluable": ok(p, "Xa"), "p": p1[p], "holm_reject": h1[p], "supported": h1[p] and ok(p, "Xa"),
                     **({"primary": cells[p]["Xa"]["summary"]["primary"]} if p in cells and "Xa" in cells[p] else {})}
        for h, b in (("H2", "Xb"), ("H3", "Xc")):
            res[h] = {"evaluable": ok(p, b), "p_tost": p2[f"{h}_{p}"], "holm_reject": h23[f"{h}_{p}"],
                      "equivalent": h23[f"{h}_{p}"] and ok(p, b),
                      **({"primary": cells[p][b]["summary"]["primary"]} if p in cells and b in cells[p] else {})}
        if ok(p, "Xa", need_vb=False):
            bt, en = backend_tost(cells[p]["Xa"]), engine_negligible(cells[p]["Xa"])
            res["H4"] = {"evaluable": en["evaluable"], **bt, "engine": en,
                         "holds": en["evaluable"] and bt["p_tost"] < ALPHA and en["all_negligible"]}
        else:
            res["H4"] = {"evaluable": False, "holds": False}
        res["H5"] = h5_scores(cells.get(p, {}), preds.get(p))
        d1: dict = {}
        if ok(p, "Xe", need_vb=False):
            s = cells[p]["Xe"]["summary"]
            d1 = {"primary": s["primary"], "attack_slo_degradation": s["attack_slo_degradation"]}
            if "Xf" in cells.get(p, {}):
                d1["threshold_above_noise"] = va.threshold_above_noise([r["log_ratio"] for r in cells[p]["Xf"]["rows"]])
        if "Xa" in cells.get(p, {}) and "Xd" in cells.get(p, {}):
            res["H1"]["threshold_above_noise"] = va.threshold_above_noise([r["log_ratio"] for r in cells[p]["Xd"]["rows"]])
        res["D1"] = d1
        res["D2"] = {b: {"flag": c["host"].get("flag"), "oom_fail": c["host"].get("oom_fail"),
                         "available": c["host"]["available"]} for b, c in cells.get(p, {}).items()}
        res["server_identity"] = srv[p]
        res["platform_identity"] = ident[p]
        per[p] = res
    # interpretation rule (rev 4 section 2.2): a G1 claim that differs from its G0 counterpart (same model) AND
    # carries a host flag is reported as "GPU+host, host-limited", not as a GPU effect
    for g1, g0 in (("g1m0", "g0m0"), ("g1m1", "g0m1")):
        lab = {}
        for h, key, b in (("H1", "supported", "Xa"), ("H2", "equivalent", "Xb"), ("H4", "holds", "Xa")):
            differs = per[g1][h].get(key) != per[g0][h].get(key)
            flagged = bool(per[g1]["D2"].get(b, {}).get("flag"))
            lab[h] = "GPU+host, host-limited" if differs and flagged else ("differs" if differs else "same")
        per[g1]["gpu_contrast"] = lab
    n1 = sum(per[p]["H1"]["supported"] for p in PLATFORMS)
    n2 = sum(per[p]["H2"]["equivalent"] for p in PLATFORMS)
    n4 = sum(per[p]["H4"]["holds"] for p in PLATFORMS)
    if n1 >= 3 and n2 >= 3 and n4 >= 3:
        verdict = "GENERALISES"
    elif n1 == 1 and per["g0m0"]["H1"]["supported"]:
        verdict = "ANCHOR-ONLY"
    else:
        verdict = "PARTIAL"
    return {"platforms": per, "families": {"F-X1": p1, "F-X2": p2}, "counts": {"H1": n1, "H2": n2, "H4": n4},
            "verdict": verdict}


def platform_identity(plat: str, pcells: dict[str, dict]) -> dict:
    """X1-specific identity (fail): every cell of the platform ran the platform's model at its pinned revision on
    vLLM 0.17.1, is an `x1_<plat>_` scenario with protocol_version 5, and carries the full v5 gate set."""
    if not pcells or all(c.get("synthetic_backend") for c in pcells.values()):
        return {"passed": True, "applicable": False}
    exp = build_x1.PLATFORMS[plat]
    probs = []
    for b, c in sorted(pcells.items()):
        pv = c.get("provenance") or {}
        if pv.get("model") != [exp["model"]]:
            probs.append(f"{b}: model {pv.get('model')} != {exp['model']}")
        if not any(X1_VLLM_VERSION in v for v in pv.get("vllm_version") or []) or len(pv.get("vllm_version") or []) != 1:
            probs.append(f"{b}: vLLM {pv.get('vllm_version')} != {X1_VLLM_VERSION}")
        if pv.get("model_revision_server_reported") != exp["revision"]:
            probs.append(f"{b}: server-reported revision {pv.get('model_revision_server_reported')} != {exp['revision']}")
        if not str(c.get("scenario_id") or "").startswith(f"x1_{plat}_") or c.get("protocol_version") != 5:
            probs.append(f"{b}: scenario {c.get('scenario_id')} / protocol {c.get('protocol_version')}")
        missing = [g for g in V5_GATES if g not in (c.get("gates") or [])]
        if missing:
            probs.append(f"{b}: v5 gates missing {missing}")
    return {"passed": not probs, "applicable": True, "problems": probs}


def server_identity(pcells: dict[str, dict]) -> dict:
    if not pcells or all(c["synthetic_backend"] for c in pcells.values()):
        return {"passed": True, "applicable": False}
    starts = {s for c in pcells.values() for s in (c["server_start"] or ["None"])}
    return {"passed": len(starts) == 1 and "None" not in starts, "applicable": True, "server_starts": sorted(starts)}


# ------------------------------------------------------------------------------------------------ driver
def load_all(dirs: list[Path]) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for d in dirs:
        for rep in sorted(p for p in d.rglob("x1_*") if (p / "manifest.json").exists() and CELL_RE.fullmatch(p.name)):
            c = load_x1_cell(rep)
            out.setdefault(c["platform"], {})[c["block"]] = c
    return out


def run(dirs: list[Path], out: Path, *, predictions_root: Path | None = None, host_files: dict[str, Path] | None = None,
        force: bool = False) -> dict:
    cells = load_all(dirs)
    synthetic = bool(cells) and all(c["synthetic_backend"] for pc in cells.values() for c in pc.values())
    exp = expected_cells()
    missing = [cid for p, bs in exp.items() for b, cid in bs.items() if b not in cells.get(p, {})]
    if missing and not synthetic:
        raise SystemExit(f"refusing an incomplete real X1 analysis (no interim looks): {len(missing)} cells missing, "
                         f"e.g. {missing[:3]}")
    seeds_ok = all(c["seeds"] == expected_seeds(b) for pc in cells.values() for b, c in pc.items())
    preds = {p: (json.loads((predictions_root / p / "FCFS_PREDICTIONS.json").read_text())
                 if predictions_root and (predictions_root / p / "FCFS_PREDICTIONS.json").exists() else None)
             for p in PLATFORMS}
    host = {p: ([json.loads(x) for x in f.read_text().splitlines() if x.strip().startswith('{"t"')]
                if f.exists() else None) for p, f in (host_files or {}).items()}
    offs = {}
    for p in PLATFORMS:
        hv = (predictions_root / p / "HOST_VERIFICATION.json") if predictions_root else None
        if hv and hv.exists():
            o = ((json.loads(hv.read_text()).get("preflight") or {}).get("phase1") or {}).get("clock_offset_s")
            if o is not None:
                offs[p] = float(o)
    res = analyse(cells, preds, host, offs)
    res |= {"synthetic_backend": synthetic, "missing_cells": missing, "seed_sets_match_protocol": seeds_ok,
            "cells": {p: {b: {"cell": c["cell"], "summary": c["summary"], "seeds": c["seeds"],
                              "failed_gates": c["failed_gates"], "per_seed": c["rows"]} for b, c in pc.items()}
                      for p, pc in cells.items()}}
    out.mkdir(parents=True, exist_ok=True)
    js, md = out / "ANALYSIS_X1.json", out / "ANALYSIS_X1.md"
    if (js.exists() or md.exists()) and not force:
        raise SystemExit(f"refusing to overwrite {js} (use --force)")
    js.write_text(json.dumps(res, indent=1, default=str) + "\n")
    md.write_text(render_md(res))
    return res


def render_md(res: dict) -> str:
    L = ["# Protocol X1 analysis", ""]
    if res["synthetic_backend"]:
        L += ["**SYNTHETIC BACKEND (mock): plumbing only, not a measurement.**", ""]
    L += [f"**Verdict: {res['verdict']}** (H1 supported on {res['counts']['H1']}/4, H2 equivalent on "
          f"{res['counts']['H2']}/4, H4 holds on {res['counts']['H4']}/4)", "",
          "| Platform | Role | H1 (p, Holm) | H2 | H3 | H4 | H5 | D1 (high, C=8) | GPU contrast |", "|---|---|---|---|---|---|---|---|---|"]
    for p, r in res["platforms"].items():
        d1 = r["D1"].get("primary", {})
        L.append(f"| {p} | {r['role']} | {r['H1']['supported']} ({r['H1']['p']:.4g}) | {r['H2']['equivalent']} | "
                 f"{r['H3']['equivalent']} | {r['H4']['holds']} | {r['H5']['verdict']} | "
                 f"{d1.get('ratio', float('nan')):.3f} {d1.get('classification', '')} | {r.get('gpu_contrast', '—')} |")
    L += ["", f"Missing cells: {len(res['missing_cells'])}; seed sets match protocol: {res['seed_sets_match_protocol']}."]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reports", action="append", required=True)
    ap.add_argument("--predictions", default=str(REPO / "experiments" / "x1"))
    ap.add_argument("--host", action="append", default=[], help="<platform>=<samples.jsonl>")
    ap.add_argument("--out", default=str(REPO / "reports" / "x1"))
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    hf = {k: Path(v) for k, v in (x.split("=", 1) for x in a.host)}
    res = run([Path(d) for d in a.reports], Path(a.out), predictions_root=Path(a.predictions), host_files=hf,
              force=a.force)
    print(json.dumps({"verdict": res["verdict"], "counts": res["counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
