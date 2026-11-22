"""Offline re-analysis of the historical A1-A9 live reports under ADR-Q16 (no GPU, no new runs).

For every original report it (1) recomputes the pre-registered primary with the original metric key and checks it
reproduces the stored value exactly, (2) adds both TTFT definitions, gateway queue, E2E, victim outcomes and
offered-load SLO success (labelled post-hoc), (3) reports the ADR-Q17 validity gates (report-only: historical
classifications are never changed), and (4) writes a corrected, metric-labelled report to a NEW directory.
Original reports/manifests/run dirs are read-only inputs.

    uv run python scripts/reanalyze_suite.py [--out reports/corrected/2026-11-21_adr_q16]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from quotashift.evaluation.attack_effect import analyze_pair, run_metrics, secondary_endpoints, write_report
from quotashift.evaluation.validity import run_manifest_provenance, validity_gates
from quotashift.scenario import load_scenario

REPO = Path(__file__).resolve().parents[1]
REPORTS = [
    "live/a1_burst_arrivals", "live/a1_burst_arrivals_r20", "live/a2_prefill_heavy", "live/a2_prefill_heavy_r20",
    "live/a2_sweep_in128", "live/a2_sweep_in256", "live/a2_sweep_in512", "live/a2_sweep_in768",
    "live/a3_decode_heavy", "live/a4_mixed_shapes", "live/stateful_sequences",
    "v3/a7v_cache_isolation_validation", "v3/a7_prefix_cache", "v3/a7_prefix_cache_reset",
    "v3/a8_lifecycle_churn", "v3/a8_retry_churn",
    "v3/a9_tok_prefill", "v3/a9_tok_decode", "v3/a9_tok_longctx", "v3/a9_tok_prefix_reuse",
    "v3/a9_rate_prefill", "v3/a9_rate_decode", "v3/a9_rate_longctx", "v3/a9_rate_prefix_reuse",
]
INVALID = {
    "a9_tok_longctx": "INVALID (Suite S audit): 112/116 attack-arm competitor requests HTTP 400 (context length); "
                      "superseded by protocol v3.1 a9_tok_longctx_v31",
    "a9_rate_longctx": "INVALID (Suite S audit): 112/116 attack-arm competitor requests HTTP 400 (context length); "
                       "superseded by protocol v3.1 a9_rate_longctx_v31",
}
SCENARIO_FILE = {"a5_stateful_sequence": "experiments/stateful_sequences.yaml"}


def scenario_path(sid: str) -> Path:
    if sid in SCENARIO_FILE:
        return REPO / SCENARIO_FILE[sid]
    for p in sorted((REPO / "experiments").rglob("*.yaml")):
        if "smoke" in p.parts or "v3_1" in p.parts:
            continue
        if f"scenario_id: {sid}\n" in p.read_text():
            return p
    raise FileNotFoundError(sid)


def local_run_dir(recorded: str) -> Path:
    """Recorded absolute paths predate the repo move; resolve by experiment dir + run id under results/."""
    p = Path(recorded)
    loc = REPO / "results" / p.parent.name / p.name
    if not loc.exists():
        raise FileNotFoundError(f"{recorded} -> {loc}")
    return loc


def _ci(a: dict) -> str:
    lo, hi = a["ratio_ci95"]
    return f"{a['mean_ratio']:.3f} [{lo:.3f}, {hi:.3f}]" if np.isfinite(a["mean_ratio"]) else "n/a"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "reports/corrected/2026-11-21_adr_q16"))
    args = ap.parse_args()
    out_root = Path(args.out)
    if (out_root / "corrected_analysis.json").exists():
        raise SystemExit(f"refusing to overwrite {out_root} (use a new --out)")
    rows, arm_rows = [], []
    for rel in REPORTS:
        man = json.loads((REPO / "reports" / rel / "manifest.json").read_text())
        sid = man["scenario_id"]
        sc = load_scenario(scenario_path(sid))
        orig = man.get("analysis") or {}
        direction = orig.get("effect_direction") or "increase"
        thr = man["preregistered_threshold"]
        seeds = [int(s) for s in man["seeds"]]
        dirs = {arm: {int(s): local_run_dir(p) for s, p in man["run_dirs"][arm].items()} for arm in ("attack", "control")}
        attack = [run_metrics(dirs["attack"][s], sid, "attack", s) for s in seeds]
        control = [run_metrics(dirs["control"][s], sid, "control", s) for s in seeds]
        hist = analyze_pair(attack, control, metric=man["metric"], threshold=thr, direction=direction)
        reproduced = bool(np.isclose(hist["mean_ratio"], orig.get("mean_ratio", np.nan), rtol=0, atol=1e-9)
                          and np.allclose(hist["ratio_ci95"], orig.get("ratio_ci95", [np.nan, np.nan]), rtol=0, atol=1e-9))
        v1 = "classification" not in orig
        if v1:  # protocol v1 had no CI classification; keep its majority-of-seeds verdict rule, add no label
            hist["classification"] = "n/a (protocol v1: majority-of-seeds verdict)"
        else:
            assert hist["classification"] == orig["classification"], (rel, hist["classification"], orig["classification"])
        user = analyze_pair(attack, control, metric="user_ttft_p95", threshold=thr, direction=direction)
        sec = secondary_endpoints(attack, control, threshold=thr, direction=direction)
        prov = run_manifest_provenance([*dirs["attack"].values(), *dirs["control"].values()])
        prov["model_revision_status"] = None  # not recorded for historical runs
        gates = validity_gates(attack, control, hist, max_model_len=sc.model_max_len,
                               prompt_token_unit=sc.prompt_token_unit,
                               designed_early_termination=sc.lifecycle is not None, provenance=prov,
                               tokenization=None, synthetic=False)
        pairs = {"control_label": man["control_label"], "seeds": seeds, "attack": dirs["attack"],
                 "control": dirs["control"], "budgets": {s: man["per_seed_budget"][str(s)] for s in seeds},
                 "arm_order": man.get("arm_order") or {}, "protocol_version": man.get("protocol_version", 1),
                 "path": man.get("path", "gateway"), "provenance": prov}
        note = ("CORRECTED REPORT (ADR-Q16, offline, 2026-11-21): metric-specific labels; pre-registered primary "
                f"recomputed from the original runs ({'reproduced exactly' if reproduced else 'DID NOT REPRODUCE'}) "
                f"and its historical classification kept unchanged. User-facing TTFT, gateway queue and offered-load "
                "SLO success are POST-HOC (not pre-registered). Validity gates are reported only. "
                f"Original report: reports/{rel}/.")
        if sid in INVALID:
            note = f"**{INVALID[sid]}.** " + note
        write_report(sid, pairs, hist, attack, control, out_root / rel, commands=[
            f"uv run python scripts/reanalyze_suite.py --out {out_root.relative_to(REPO) if out_root.is_relative_to(REPO) else out_root}"],
            secondary=sec, validity=gates, note=note)
        failed = [c["name"] for c in gates["checks"] if c["severity"] == "fail" and not c["passed"]]
        unavailable = [c["name"] for c in gates["checks"] if not c["available"]]
        flagged = [c["name"] for c in gates["checks"] if c["severity"] == "flag" and not c["passed"]]

        def mean_of(ms, f):
            v = [getattr(m, f) for m in ms if getattr(m, f) is not None]
            return float(np.mean(v)) if v else None

        def sum_of(ms, f):
            v = [getattr(m, f) for m in ms if getattr(m, f) is not None]
            return int(np.sum(v)) if v else None

        row = {"report": rel, "scenario_id": sid, "series": "v1" if v1 else f"v{man.get('protocol_version')}",
               "seeds": len(seeds), "metric": man["metric"], "metric_label": hist["metric_label"],
               "threshold": thr, "direction": direction, "historical": _ci(hist), "historical_mean": hist["mean_ratio"],
               "historical_ci": hist["ratio_ci95"], "historical_classification": hist["classification"],
               "historical_success_rate": hist["attack_success_rate"], "reproduced": reproduced,
               "invalid": INVALID.get(sid),
               "user_ttft_ratio": _ci(user), "user_ttft_posthoc_label": user["classification"]
               if len(seeds) >= 5 else user["classification"],
               "user_ttft_mean": user["mean_ratio"], "user_ttft_ci": user["ratio_ci95"],
               "gates_failed": failed, "gates_unavailable": unavailable, "gates_flagged": flagged}
        for k, s2 in sec.items():
            row[f"{k}_ratio"] = _ci(s2)
            row[f"{k}_mean"] = s2["mean_ratio"]
            row[f"{k}_label"] = s2["classification"]
        for arm, ms in (("attack", attack), ("control", control)):
            for f in ("victim_offered", "victim_completed", "victim_rejected", "victim_timed_out", "victim_backend_error",
                      "victim_cancelled", "competitor_offered", "competitor_requests", "competitor_backend_error",
                      "competitor_http_400", "competitor_timed_out", "competitor_cancelled"):
                row[f"{arm}_{f}_sum"] = sum_of(ms, f)
            for f in ("victim_slo_success_offered", "victim_user_ttft_p95_ms", "victim_backend_ttft_p95_ms",
                      "victim_gateway_queue_p95_ms", "victim_e2e_p95_ms", "victim_censored_fraction"):
                row[f"{arm}_{f}_mean"] = mean_of(ms, f)
        rows.append(row)
        for m in (*attack, *control):
            arm_rows.append({"report": rel, **m.as_row()})
        print(f"{rel:40s} hist {row['historical']:26s} {str(hist['classification'])[:12]:12s} reproduced={reproduced} "
              f"user {row['user_ttft_ratio']:26s} failed={failed}")
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "corrected_analysis.json").write_text(json.dumps(rows, indent=2, default=float) + "\n")
    pd.DataFrame(rows).to_csv(out_root / "corrected_analysis.csv", index=False)
    pd.DataFrame(arm_rows).to_csv(out_root / "per_arm_metrics.csv", index=False)
    print(f"wrote {len(rows)} corrected reports under {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
