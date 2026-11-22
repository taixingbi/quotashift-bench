"""Protocol v4 analysis (docs/PROTOCOL_V4.md). Read-only on reports; writes only to --out.

    uv run python scripts/v4_analysis.py select-load  --reports reports/v4/calibration [--out ...]   # R1 §R1.2
    uv run python scripts/v4_analysis.py r2-summary   --reports reports/v4/r2          [--out ...]   # R2 §R2.3
    uv run python scripts/v4_analysis.py compare-paths --gateway <report> --direct <report> [--out ...]  # R3 §R3.3

Every rule here is the pre-registered one in PROTOCOL_V4.md; thresholds are module constants, never arguments.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from quotashift.evaluation.attack_effect import bootstrap_ci

# R1.2 feasibility rule for selecting the common offered load L* (stricter than the ADR-Q17 gates: margin)
CAL_MIN_COMPETITOR_COMPLETION = 0.98
CAL_MAX_VICTIM_CENSORED = 0.0
CAL_MAX_GW_SATURATION = 0.25
INTEGRITY_GATES = ("backend_error_rate", "http_400_rate", "admission_rate", "primary_metric_present",
                   "tokenized_context", "planned_vs_reported_tokens", "provenance", "arrival_coverage",
                   "realized_output_equals_authorized")
# R2.3 limiting-resource classification (attack arm, mean over seeds)
REQ_BOUND_MIN_SATURATION = 0.50
ENGINE_BOUND_MIN_WAITING = 0.05


def _load(rep: Path) -> tuple[dict, pd.DataFrame]:
    return json.loads((rep / "manifest.json").read_text()), pd.read_csv(rep / "summary.csv")


def _gate_map(man: dict) -> dict[str, bool]:
    return {g["name"]: bool(g["passed"]) for g in ((man.get("validity") or {}).get("checks") or [])}


def select_load(reports: Path) -> dict:
    probes = {}
    for rep in sorted(p for p in reports.iterdir() if (p / "manifest.json").exists()):
        m = re.fullmatch(r"v4_cal_([PDS])_L(\d+)", rep.name)
        if not m:
            continue
        man, df = _load(rep)
        gates = _gate_map(man)
        integ = [g for g in INTEGRITY_GATES if g in gates and not gates[g]]
        missing = [g for g in INTEGRITY_GATES if g not in gates]
        comp = (df.competitor_requests / df.competitor_offered).min()
        cens = df.victim_censored_fraction.max()
        sat = df.gw_saturation_fraction.max()
        ok = (not integ and not missing and comp >= CAL_MIN_COMPETITOR_COMPLETION and cens <= CAL_MAX_VICTIM_CENSORED
              and sat <= CAL_MAX_GW_SATURATION)
        probes[rep.name] = {"shape": m.group(1), "load": int(m.group(2)), "feasible": bool(ok),
                            "min_competitor_completion": float(comp), "max_victim_censored": float(cens),
                            "max_gw_saturation": float(sat), "failed_integrity_gates": integ, "missing_gates": missing}
    loads = sorted({p["load"] for p in probes.values()})
    feasible_at = {L: all(p["feasible"] for p in probes.values() if p["load"] == L)
                   and {p["shape"] for p in probes.values() if p["load"] == L} == {"P", "D", "S"} for L in loads}
    sel = None
    for L in loads:  # monotone rule: L* = the largest L such that it and every lower grid level are feasible
        if not feasible_at[L]:
            break
        sel = L
    return {"rule": {"min_competitor_completion": CAL_MIN_COMPETITOR_COMPLETION,
                     "max_victim_censored": CAL_MAX_VICTIM_CENSORED, "max_gw_saturation": CAL_MAX_GW_SATURATION,
                     "integrity_gates": list(INTEGRITY_GATES)},
            "feasible_at": feasible_at, "selected_load": sel, "probes": probes,
            "decision": (f"run experiments/v4/r1/*_L{sel}.yaml" if sel is not None else
                         "NO feasible grid load: stop and report (pre-registered fallback needs owner review)")}


def _ci(vals: list[float]) -> tuple[float, float, float]:
    v = [x for x in vals if x is not None and np.isfinite(x)]
    lo, hi = bootstrap_ci(v)
    return (float(np.mean(v)) if v else float("nan"), lo, hi)


def r2_summary(reports: Path) -> pd.DataFrame:
    rows = []
    for rep in sorted(p for p in reports.iterdir() if (p / "manifest.json").exists()):
        m = re.fullmatch(r"v4_r2([fb])_s(\d+)", rep.name)
        if not m:
            continue
        man, df = _load(rep)
        a, c = df[df.arm == "attack"], df[df.arm == "control"]
        sat = a.gw_saturation_fraction.mean()
        eng = a.engine_bound_fraction.mean()
        limiting = ("engine-bound" if eng > ENGINE_BOUND_MIN_WAITING else
                    "request-bound (gateway)" if sat >= REQ_BOUND_MIN_SATURATION else "unconstrained")
        ratio = (a.set_index("seed").victim_user_ttft_p95_ms / c.set_index("seed").victim_user_ttft_p95_ms).tolist()
        mu, lo, hi = _ci(ratio)
        rows.append({"family": m.group(1).upper(), "size": int(m.group(2)), "seeds": int(len(a)),
                     "regime": (man.get("validity") or {}).get("regime"),
                     "integrity_ok": all(v for k, v in _gate_map(man).items() if k in INTEGRITY_GATES),
                     "limiting_resource": limiting,
                     "competitor_requests": float(a.competitor_offered.mean()),
                     "competitor_completion": float((a.competitor_requests / a.competitor_offered).mean()),
                     "victim_censored": float(a.victim_censored_fraction.mean()),
                     "victim_slo_success": float(a.victim_slo_success_offered.mean()),
                     "victim_slo_success_baseline": float(c.victim_slo_success_offered.mean()),
                     "victim_user_ttft_p95_ms": float(a.victim_user_ttft_p95_ms.mean()),
                     "victim_user_ttft_p95_baseline_ms": float(c.victim_user_ttft_p95_ms.mean()),
                     "victim_user_ttft_p95_ratio": f"{mu:.3f} [{lo:.3f}, {hi:.3f}]",
                     "victim_gateway_queue_p95_ms": float(a.victim_gateway_queue_p95_ms.mean()),
                     "gw_saturation_fraction": float(sat), "request_bound_fraction": float(a.request_bound_fraction.mean()),
                     "engine_bound_fraction": float(eng), "engine_running_mean": float(a.engine_running_mean.mean()),
                     "gpu_util_mean": float(a.gpu_util_mean.mean()),
                     "competitor_realized_tokens_per_s": float(a.competitor_realized_tokens_per_s.mean()),
                     "gpu_dynamic_energy_kj": float(a.gpu_dynamic_energy_j.mean() / 1000)
                     if a.gpu_dynamic_energy_j.notna().any() else float("nan")})
    out = pd.DataFrame(rows)
    return out.sort_values(["family", "size"]).reset_index(drop=True) if len(out) else out


def r2_boundary(s: pd.DataFrame) -> dict:
    """Per family: the smallest size s* such that s* and every larger size are feasible (all seeds)."""
    res = {}
    for fam, g in s.groupby("family"):
        g = g.sort_values("size", ascending=False)
        star = None
        for _, r in g.iterrows():
            if r.regime != "feasible" or not r.integrity_ok:
                break
            star = int(r["size"])
        res[fam] = star
    return res


PATH_METRICS = ("victim_user_ttft_p95_ms", "victim_backend_ttft_p95_ms", "victim_gateway_queue_p95_ms",
                "victim_user_ttft_mean_ms", "victim_backend_ttft_mean_ms", "victim_gateway_queue_mean_ms",
                "victim_slo_success_offered", "victim_censored_fraction", "engine_running_mean", "engine_running_max",
                "engine_waiting_mean", "gpu_util_mean", "gpu_dynamic_energy_j", "competitor_realized_tokens_per_s")


def compare_paths(gw: Path, direct: Path) -> dict:
    gman, gdf = _load(gw)
    dman, ddf = _load(direct)
    if gman.get("path") != "gateway" or dman.get("path") != "direct":
        raise SystemExit(f"expected gateway vs direct reports, got {gman.get('path')} / {dman.get('path')}")
    out: dict = {"gateway_report": str(gw), "direct_report": str(direct), "arms": {}}
    for arm in ("attack", "control"):
        g = gdf[gdf.arm == arm].set_index("seed")
        d = ddf[ddf.arm == arm].set_index("seed")
        seeds = sorted(set(g.index) & set(d.index))
        arm_out: dict = {"seeds": seeds}
        for k in PATH_METRICS:
            gv, dv = g.loc[seeds, k].astype(float), d.loc[seeds, k].astype(float)
            ratio = (dv / gv).replace([np.inf, -np.inf], np.nan).tolist()
            mu, lo, hi = _ci(ratio)
            arm_out[k] = {"gateway_mean": float(gv.mean()), "direct_mean": float(dv.mean()),
                          "direct_over_gateway": [mu, lo, hi]}
        # decomposition (means are additive): user TTFT = gateway queue + backend TTFT
        q = g.loc[seeds, "victim_gateway_queue_mean_ms"].astype(float).mean()
        b = g.loc[seeds, "victim_backend_ttft_mean_ms"].astype(float).mean()
        db = d.loc[seeds, "victim_backend_ttft_mean_ms"].astype(float).mean()
        arm_out["decomposition_ms"] = {
            "gateway_user_ttft_mean": float(q + b), "gateway_queue_share": float(q / (q + b)) if q + b else None,
            "gateway_backend_ttft_mean": float(b), "direct_backend_ttft_mean": float(db),
            "backend_interference_change_direct_minus_gateway": float(db - b)}
        out["arms"][arm] = arm_out
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("select-load")
    s1.add_argument("--reports", required=True)
    s1.add_argument("--out", default=None)
    s2 = sub.add_parser("r2-summary")
    s2.add_argument("--reports", required=True)
    s2.add_argument("--out", default=None)
    s3 = sub.add_parser("compare-paths")
    s3.add_argument("--gateway", required=True)
    s3.add_argument("--direct", required=True)
    s3.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.cmd == "select-load":
        res = select_load(Path(a.reports))
    elif a.cmd == "r2-summary":
        s = r2_summary(Path(a.reports))
        res = {"points": s.to_dict(orient="records"), "boundary_size": r2_boundary(s) if len(s) else {}}
    else:
        res = compare_paths(Path(a.gateway), Path(a.direct))
    text = json.dumps(res, indent=2, default=float)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
