"""Protocol X2 analysis (docs/PROTOCOL_X2_DRAFT.md rev 2 section 6). NOT frozen until X2 Freeze Commit 1.

    uv run python scripts/x2_analysis.py --reports reports/x2 --experiments experiments/x2 --out reports/x2

Inputs: one experiment report per (platform, block) named x2_<plat>_<X2a|X2b|X2c|X2d>_<comparison>_low_<C8|C32|direct>,
each arm's x2_host_snapshots.json (boundary snapshots), and the platform's QUALIFICATION.json (admissibility).

Every decision rule is the FROZEN v5 implementation, imported unchanged from scripts/v5_analysis.py: classify_cell,
p_superiority (one-sided vs log 1.25), p_tost ([0.8, 1.25]), holm, threshold_above_noise, engine_queue_negligible,
stratum, attack_slo_degradation, t_cdf, mean_ci and the per-seed loader helpers. X2-H4's backend band [0.9, 1.1] is
computed with the frozen v5 mean_ci / t_cdf.

Families: F-H1 = X2-H1 over the 4 planned platforms (Holm; p = 1 if the platform is not admissible or not evaluable);
F-H23 = 4 x X2-H2 (direct) + 4 x X2-H3 (C = 32) (Holm over 8). A platform "replicates" iff H1 is supported AND H2, H3
and H4 hold on it. Verdict: REPLICATES iff >= 3 of 4 platforms replicate; REPLICATES-ON-k (k = 1, 2) descriptive;
otherwise NOT REPLICATED AT THIS POWER. No interim looks: real (non-synthetic) data are analysed only when every
expected cell of every ADMISSIBLE platform is present.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_x2  # noqa: E402
import v5_analysis as va  # noqa: E402  (frozen; read-only import)

CELL_RE = re.compile(r"x2_(g[01]m[01])_(X2[a-d])_(decode_vs_short|aa_ind)_low_(C8|C32|direct)")
PLATFORMS = tuple(build_x2.PLATFORMS)
ALPHA = va.ALPHA
BACKEND_LO, BACKEND_HI = math.log(0.9), math.log(1.1)
VLLM_VERSION = "0.17.1"
V5_GATES = ("backend_error_rate", "http_400_rate", "admission_rate", "competitor_completion", "primary_metric_present",
            "tokenized_context", "planned_vs_reported_tokens", "provenance", "victim_latency_censoring",
            "arrival_coverage", "realized_output_equals_authorized", "cap_configured", "occupancy_reconstruction",
            "gateway_timestamp_alignment")


def _snap(run: Path) -> dict:
    f = run / "x2_host_snapshots.json"
    if not f.exists():
        return {"available": False}
    r = json.loads(f.read_text())
    return {"available": True, "status": r["flags"]["status"], "flags": r["flags"]["flags"], "fails": r["flags"]["fails"],
            "metrics": r["metrics"]}


def load_cell(rep: Path) -> dict:
    """One X2 report -> the v5 per-seed table (same construction as v5_analysis.load_cell) + boundary snapshots."""
    m = CELL_RE.fullmatch(rep.name)
    if not m:
        raise ValueError(f"not an X2 cell report: {rep}")
    plat, block, comp, capk = m.groups()
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
               "log_ratio": math.log(a.victim_user_ttft_mean_ms) - math.log(c.victim_user_ttft_mean_ms)}
        for arm, r in (("attack", a), ("control", c)):
            run = va._resolve_run(r.run_dir)
            row[arm] = {"user_ttft_mean_ms": float(r.victim_user_ttft_mean_ms),
                        "backend_ttft_mean_ms": float(r.victim_backend_ttft_mean_ms),
                        "gateway_queue_mean_ms": float(r.victim_gateway_queue_mean_ms),
                        "slo_success": float(r.victim_slo_success_offered),
                        "engine_queue": va._engine_queue(run), "run_dir": str(run), "snapshot": _snap(run)}
        rows.append(row)
    return {"cell": rep.name, "platform": plat, "block": block, "comparison": comp, "C": C,
            "synthetic_backend": bool(man.get("synthetic_backend")), "failed_gates": failed,
            "server_start": list((man.get("provenance") or {}).get("server_start") or []),
            "provenance": man.get("provenance") or {}, "gates": [c["name"] for c in checks],
            "scenario_id": man.get("scenario_id"), "protocol_version": man.get("protocol_version"),
            "seeds": [r["seed"] for r in rows], "rows": rows}


def expected_cells() -> dict[str, dict[str, str]]:
    return {p: {b: build_x2.cell_id(p, b, comp, cap) for b, comp, cap, _, _ in build_x2.BLOCKS} for p in PLATFORMS}


def expected_seeds(block: str) -> list[int]:
    n = next(n for b, _, _, n, _ in build_x2.BLOCKS if b == block)
    return list(range(build_x2.MAIN_SEED0, build_x2.MAIN_SEED0 + n))


def summarize(cell: dict) -> dict:
    rows = cell["rows"]
    out = {"stratum": va.stratum([r["E"] for r in rows], [r["Vb"] for r in rows]), "n": len(rows),
           "primary": va.classify_cell([r["log_ratio"] for r in rows]),
           "attack_slo_degradation": va.attack_slo_degradation([r["attack"]["slo_success"] for r in rows],
                                                               [r["control"]["slo_success"] for r in rows])}
    snaps = [r[arm]["snapshot"] for r in rows for arm in ("attack", "control")]
    out["host"] = {"arms": len(snaps), "available": sum(s["available"] for s in snaps),
                   "flagged": sum(1 for s in snaps if s.get("status") == "flag"),
                   "failed": sum(1 for s in snaps if s.get("status") == "fail")}
    return out


def backend_tost(cell: dict) -> dict:
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
            per.append(va.engine_queue_negligible(eq.get("sum_s") or 0.0, eq.get("count") or 0.0, eq.get("buckets") or []))
    ev = [x for x in per if x.get("evaluable")]
    return {"evaluable": bool(per) and len(ev) == len(per), "all_negligible": bool(ev) and all(x["negligible"] for x in ev)}


def platform_identity(plat: str, pcells: dict[str, dict]) -> dict:
    if not pcells or all(c.get("synthetic_backend") for c in pcells.values()):
        return {"passed": True, "applicable": False}
    exp = build_x2.PLATFORMS[plat]
    probs = []
    for b, c in sorted(pcells.items()):
        pv = c.get("provenance") or {}
        if pv.get("model") != [exp["model"]]:
            probs.append(f"{b}: model {pv.get('model')}")
        if len(pv.get("vllm_version") or []) != 1 or VLLM_VERSION not in (pv.get("vllm_version") or [""])[0]:
            probs.append(f"{b}: vLLM {pv.get('vllm_version')}")
        if pv.get("model_revision_server_reported") != exp["revision"]:
            probs.append(f"{b}: server-reported revision {pv.get('model_revision_server_reported')}")
        if not str(c.get("scenario_id") or "").startswith(f"x2_{plat}_") or c.get("protocol_version") != 5:
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


def analyse(cells: dict[str, dict[str, dict]], admissible: dict[str, bool]) -> dict:
    for pc in cells.values():
        for c in pc.values():
            c["summary"] = summarize(c)
    ident = {p: platform_identity(p, cells.get(p, {})) for p in PLATFORMS}
    srv = {p: server_identity(cells.get(p, {})) for p in PLATFORMS}

    def ok(p: str, b: str, need_vb: bool = True) -> bool:
        c = cells.get(p, {}).get(b)
        if c is None or not admissible.get(p, False) or not ident[p]["passed"] or not srv[p]["passed"]:
            return False
        return c["summary"]["stratum"] == "E&Vb" if need_vb else c["summary"]["stratum"] != "notE"

    p1 = {p: (va.p_superiority([r["log_ratio"] for r in cells[p]["X2a"]["rows"]]) if ok(p, "X2a") else 1.0)
          for p in PLATFORMS}
    h1 = va.holm(p1)
    p23 = {}
    for p in PLATFORMS:
        p23[f"H2_{p}"] = va.p_tost([r["log_ratio"] for r in cells[p]["X2c"]["rows"]]) if ok(p, "X2c") else 1.0
        p23[f"H3_{p}"] = va.p_tost([r["log_ratio"] for r in cells[p]["X2d"]["rows"]]) if ok(p, "X2d") else 1.0
    h23 = va.holm(p23)
    per: dict[str, dict] = {}
    for p in PLATFORMS:
        res: dict = {"admissible": admissible.get(p, False)}
        res["H1"] = {"evaluable": ok(p, "X2a"), "p": p1[p], "holm_reject": h1[p], "supported": h1[p] and ok(p, "X2a"),
                     **({"primary": cells[p]["X2a"]["summary"]["primary"]} if "X2a" in cells.get(p, {}) else {})}
        if "X2a" in cells.get(p, {}) and "X2b" in cells.get(p, {}):
            res["H1"]["threshold_above_noise"] = va.threshold_above_noise([r["log_ratio"] for r in cells[p]["X2b"]["rows"]])
        for h, b in (("H2", "X2c"), ("H3", "X2d")):
            res[h] = {"evaluable": ok(p, b), "p_tost": p23[f"{h}_{p}"], "holm_reject": h23[f"{h}_{p}"],
                      "equivalent": h23[f"{h}_{p}"] and ok(p, b),
                      **({"primary": cells[p][b]["summary"]["primary"]} if b in cells.get(p, {}) else {})}
        if ok(p, "X2a", need_vb=False):
            bt, en = backend_tost(cells[p]["X2a"]), engine_negligible(cells[p]["X2a"])
            res["H4"] = {"evaluable": en["evaluable"], **bt, "engine": en,
                         "holds": en["evaluable"] and bt["p_tost"] < ALPHA and en["all_negligible"]}
        else:
            res["H4"] = {"evaluable": False, "holds": False}
        res["replicates"] = bool(res["H1"]["supported"] and res["H2"]["equivalent"] and res["H3"]["equivalent"]
                                 and res["H4"]["holds"])
        res["host"] = {b: c["summary"]["host"] for b, c in cells.get(p, {}).items()}
        res["platform_identity"], res["server_identity"] = ident[p], srv[p]
        per[p] = res
    k = sum(per[p]["replicates"] for p in PLATFORMS)
    verdict = "REPLICATES" if k >= 3 else (f"REPLICATES-ON-{k}" if k > 0 else "NOT REPLICATED AT THIS POWER")
    return {"platforms": per, "families": {"F-H1": p1, "F-H23": p23}, "replicating_platforms": k, "verdict": verdict,
            "counts": {h: sum(bool(per[p][h].get(key)) for p in PLATFORMS)
                       for h, key in (("H1", "supported"), ("H2", "equivalent"), ("H3", "equivalent"), ("H4", "holds"))}}


def load_all(dirs: list[Path]) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for d in dirs:
        for rep in sorted(p for p in d.rglob("x2_*") if (p / "manifest.json").exists() and CELL_RE.fullmatch(p.name)):
            c = load_cell(rep)
            out.setdefault(c["platform"], {})[c["block"]] = c
    return out


def admissibility(exp_root: Path | None) -> dict[str, bool]:
    out = {}
    for p in PLATFORMS:
        f = exp_root / p / "QUALIFICATION.json" if exp_root else None
        out[p] = bool(f and f.exists() and json.loads(f.read_text()).get("status") == "pass")
    return out


def run(dirs: list[Path], out: Path, *, exp_root: Path | None, force: bool = False,
        admissible_override: dict[str, bool] | None = None) -> dict:
    cells = load_all(dirs)
    synthetic = bool(cells) and all(c["synthetic_backend"] for pc in cells.values() for c in pc.values())
    adm = admissible_override if admissible_override is not None else admissibility(exp_root)
    if synthetic and admissible_override is None:
        adm = {p: True for p in PLATFORMS}               # mock plumbing only
    exp = expected_cells()
    missing = [cid for p, bs in exp.items() if adm.get(p) for b, cid in bs.items() if b not in cells.get(p, {})]
    if missing and not synthetic:
        raise SystemExit(f"refusing an incomplete real X2 analysis (no interim looks): {len(missing)} cells missing, "
                         f"e.g. {missing[:3]}")
    seeds_ok = all(c["seeds"] == expected_seeds(b) for pc in cells.values() for b, c in pc.items())
    res = analyse(cells, adm)
    res |= {"synthetic_backend": synthetic, "missing_cells": missing, "seed_sets_match_protocol": seeds_ok,
            "admissible": adm}
    out.mkdir(parents=True, exist_ok=True)
    js, md = out / "ANALYSIS_X2.json", out / "ANALYSIS_X2.md"
    if (js.exists() or md.exists()) and not force:
        raise SystemExit(f"refusing to overwrite {js} (use --force)")
    js.write_text(json.dumps(res, indent=1, default=str) + "\n")
    md.write_text(render_md(res))
    return res


def render_md(res: dict) -> str:
    L = ["# Protocol X2 analysis", ""]
    if res["synthetic_backend"]:
        L += ["**SYNTHETIC BACKEND (mock): plumbing only, not a measurement.**", ""]
    L += [f"**Verdict: {res['verdict']}** ({res['replicating_platforms']} of 4 platforms replicate)", "",
          "| Platform | admissible | H1 (p, Holm) | H2 direct | H3 C=32 | H4 | replicates |", "|---|---|---|---|---|---|---|"]
    for p, r in res["platforms"].items():
        L.append(f"| {p} | {r['admissible']} | {r['H1']['supported']} ({r['H1']['p']:.4g}) | {r['H2']['equivalent']} | "
                 f"{r['H3']['equivalent']} | {r['H4']['holds']} | {r['replicates']} |")
    L += ["", f"Missing cells: {len(res['missing_cells'])}; seed sets match protocol: {res['seed_sets_match_protocol']}."]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reports", action="append", required=True)
    ap.add_argument("--experiments", default=str(REPO / "experiments" / "x2"))
    ap.add_argument("--out", default=str(REPO / "reports" / "x2"))
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    res = run([Path(d) for d in a.reports], Path(a.out), exp_root=Path(a.experiments), force=a.force)
    print(json.dumps({"verdict": res["verdict"], "counts": res["counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
