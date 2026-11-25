"""X1 closeout: DESCRIPTIVE quantification of the g0m0 sampler-equivalence data (post hoc; decides nothing).

    uv run python scripts/x1_closeout_descriptive.py      # -> reports/x1/X1_CLOSEOUT_DESCRIPTIVE.json

Inputs: the three committed g0m0 Phase 1 records (attempt1, attempt2, the A1 run) and, for the per-segment and
telemetry figures, the git-ignored raw A1 files under reports/x1/g0m0/preflight/ (checksums in A1_RUN_SHA256SUMS).
The A1 verdict (FAIL, fb81bef) is final; nothing here re-tests or reclassifies it. Pair-level numbers recompute exactly
what the pinned rule reported; everything else (one-sided tests, bootstrap, robust location, telemetry split) is
descriptive and was not pre-registered.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from quotashift.x1.preflight import pctl
from quotashift.x1.sampler_equivalence_a1 import _t_cdf

REPO = Path(__file__).resolve().parents[1]
G = REPO / "experiments" / "x1" / "g0m0"
RAW = REPO / "reports" / "x1" / "g0m0" / "preflight"
OUT = REPO / "reports" / "x1" / "X1_CLOSEOUT_DESCRIPTIVE.json"
SEED = 81000


def main() -> int:
    a1 = json.loads((G / "HOST_VERIFICATION.json").read_text())["preflight"]["phase1"]
    e = a1["checks"]["sampler_equivalence"]
    d = np.array(e["pair_diffs_ms"])
    k, m, se, delta = len(d), e["mean_diff_ms"], e["se_ms"], e["delta_ms"]
    rng = np.random.default_rng(SEED)
    boot = np.array([rng.choice(d, k).mean() for _ in range(20000)])
    walsh = [(d[i] + d[j]) / 2 for i in range(k) for j in range(i, k)]
    big = [i for i, x in enumerate(d) if x > 2.0]
    rest = np.delete(d, big)
    out: dict = {
        "status": "descriptive, post hoc; the A1 FAIL (fb81bef) is final and is not re-tested",
        "attempts": {},
        "a1": {"k_pairs": k, "mean_diff_ms": m, "sd_pair_diff_ms": e["sd_pair_diff_ms"], "se_ms": se, "delta_ms": delta,
               "ci90_ms": e["ci90_ms"], "ci95_ms": e["ci95_ms_reported"],
               "tost_upper_p_effect_below_plus_delta": _t_cdf((m - delta) / se, k - 1),
               "tost_lower_p_effect_above_minus_delta": 1 - _t_cdf((m + delta) / se, k - 1),
               "one_sided_p_effect_above_zero": 1 - _t_cdf(m / se, k - 1),
               "one_sided_p_effect_above_plus_delta": 1 - _t_cdf((m - delta) / se, k - 1),
               "bootstrap_mean_ci90_ms": np.quantile(boot, [0.05, 0.95]).tolist(),
               "bootstrap_mean_ci95_ms": np.quantile(boot, [0.025, 0.975]).tolist(),
               "median_pair_diff_ms": float(np.median(d)), "hodges_lehmann_ms": float(np.median(walsh)),
               "positive_pairs": int((d > 0).sum()),
               "pairs_above_2ms": {str(i): float(d[i]) for i in big},
               "other_pairs_mean_sd_ms": [float(rest.mean()), float(rest.std(ddof=1))],
               "off_first_vs_on_first_mean_ms": [float(d[0::2].mean()), float(d[1::2].mean())],
               "legacy_rev4_point_rule": {x: a1["legacy_rev4_point_rule"].get(x) for x in ("status", "diff_ms")}},
    }
    for name, f in (("attempt1", "HOST_VERIFICATION.attempt1.json"), ("attempt2", "HOST_VERIFICATION.attempt2.json")):
        r = json.loads((G / f).read_text())["preflight"]["phase1"]
        se_ = r["checks"]["sampler_equivalence"]
        out["attempts"][name] = {"verdict": r["status"], "diff_ms": se_["diff_ms"], "median_on_ms": se_["median_on_ms"],
                                 "median_off_ms": se_["median_off_ms"], "started_utc": r["started_utc"]}
    f2 = json.loads((G / "HOST_VERIFICATION.attempt2.json").read_text())["preflight"]["phase1"]["ttft_floor_ms"]
    on2, off2 = np.array(f2["sampler_on_ms"]), np.array(f2["sampler_off_ms"])
    b2 = np.array([pctl(list(rng.choice(on2, 20)), 50) - pctl(list(rng.choice(off2, 20)), 50) for _ in range(20000)])
    out["attempts"]["attempt2"]["bootstrap_ci95_ms"] = np.quantile(b2, [0.025, 0.975]).tolist()
    segs_f = RAW / "a1_segments.json"
    if segs_f.exists():
        segs = json.loads(segs_f.read_text())
        rows = []
        for j in range(k):
            on = next(s for s in segs if s["pair"] == j and s["arm"] == "on")
            off = next(s for s in segs if s["pair"] == j and s["arm"] == "off")
            tel = [json.loads(x) for x in (RAW / "a1_telemetry" / f"g0m0_a1_p{j:02d}.jsonl").read_text().splitlines()
                   if x.startswith('{"t"')]
            rows.append({"pair": j, "d_ms": float(d[j]), "positions_on_off": [on["position"], off["position"]],
                         "p50_on_ms": pctl(on["ttft_ms"], 50), "p50_off_ms": pctl(off["ttft_ms"], 50),
                         "q90_on_ms": float(np.quantile(on["ttft_ms"], 0.9)),
                         "q90_off_ms": float(np.quantile(off["ttft_ms"], 0.9)),
                         "host_busy_cores_mean": float(np.mean([t["host_busy"] * t["ncpu"] for t in tel])),
                         "api_cpu_mean": float(np.mean([t["api_cpu"] or 0 for t in tel])),
                         "engine_cpu_mean": float(np.mean([t["engine_cpu"] or 0 for t in tel])),
                         "server_ttft_hist_mean_ms_on_off": [on["server_ttft_hist"]["mean_ms"],
                                                             off["server_ttft_hist"]["mean_ms"]]})
        out["a1_pairs"] = rows
        slow = [r for r in rows if r["d_ms"] > 2.0]
        norm = [r for r in rows if r["d_ms"] <= 2.0]
        out["a1_telemetry_slow_vs_other_pairs"] = {
            key: [float(np.mean([r[key] for r in slow])), float(np.mean([r[key] for r in norm]))]
            for key in ("host_busy_cores_mean", "api_cpu_mean", "engine_cpu_mean")}
    OUT.write_text(json.dumps(out, indent=1, default=lambda o: None if isinstance(o, float) and math.isnan(o) else o) + "\n")
    print(json.dumps({k_: v for k_, v in out["a1"].items() if k_ != "pairs_above_2ms"}, indent=1))
    print("attempts", json.dumps(out["attempts"]))
    print("telemetry slow vs other", out.get("a1_telemetry_slow_vs_other_pairs"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
