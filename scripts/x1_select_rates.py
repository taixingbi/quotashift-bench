"""X1 rate selection after calibration A (rev 4 section 3; frozen rule build_x1.choose_rates, applied unchanged).

    uv run python scripts/x1_select_rates.py --platform g0m1            # -> experiments/x1/<plat>/RATES.json

Per calibration-A grid point (an A/A-ind short-short block at C = 8, seeds 7000-7002):
  rho_ctl = mean over the CONTROL-arm runs of  sum over all requests (t_terminal - t_sent) / (8 x 120 s)
  slo_ctl = mean CONTROL-arm victim offered-load SLO success (summary.csv)
Refuses unless the calA stage log is `completed` and every grid block passed (or its single rerun did). Never
substitutes a rate: the output is whatever the frozen rule returns, including an infeasible low point.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_x1  # noqa: E402
import v5_analysis as va  # noqa: E402

CAP, WINDOW_S = 8, float(build_x1.RUNTIME)


def control_slot_demand(run: Path) -> float:
    r = pd.read_parquet(run / "requests.parquet", columns=["t_sent", "t_terminal"]).dropna()
    return float((r.t_terminal - r.t_sent).sum() / (CAP * WINDOW_S))


def measure(plat: str, reports_root: Path) -> dict[int, dict]:
    st = reports_root / plat / "calA"
    log = json.loads((st / "STAGE_LOG.json").read_text())
    if log.get("status") != "completed":
        raise SystemExit(f"REFUSED: {plat}/calA stage status {log.get('status')} (must be completed)")
    out: dict[int, dict] = {}
    for sid in log["order"]:
        b, r2 = log["blocks"].get(sid), log["blocks"].get(f"{sid}{build_x1.RERUN}")
        use = sid if b and b.get("status") == "passed" else (f"{sid}{build_x1.RERUN}" if r2 and r2.get("status") == "passed" else None)
        if use is None:
            raise SystemExit(f"REFUSED: {sid} has no passed block")
        rep = st / use
        man = json.loads((rep / "manifest.json").read_text())
        df = pd.read_csv(rep / "summary.csv")
        ctl = df[df.arm == "control"]
        rates = [control_slot_demand(va._resolve_run(d)) for d in man["run_dirs"]["control"].values()]
        rate = int(re.search(r"_L(\d+)_C8", sid).group(1))
        out[rate] = {"rho_ctl": sum(rates) / len(rates), "rho_ctl_per_seed": rates,
                     "slo_ctl": float(ctl.victim_slo_success_offered.mean()), "block": use, "seeds": sorted(int(s) for s in ctl.seed)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", choices=tuple(build_x1.PLATFORMS), required=True)
    ap.add_argument("--reports-root", default=str(REPO / "reports" / "x1"))
    a = ap.parse_args()
    out = REPO / "experiments" / "x1" / a.platform / "RATES.json"
    if out.exists():
        print(f"REFUSED: {out} exists (rates are selected once)", file=sys.stderr)
        return 3
    cal = measure(a.platform, Path(a.reports_root))
    sel = build_x1.choose_rates({r: {"rho_ctl": v["rho_ctl"], "slo_ctl": v["slo_ctl"]} for r, v in cal.items()})
    sel |= {"platform": a.platform, "selected_utc": datetime.now(UTC).isoformat(),
            "rule_source": "scripts/build_x1.py choose_rates (X1 Freeze Commit 1)",
            "measurement": {str(r): {k: v for k, v in cal[r].items()} for r in sorted(cal)}}
    out.write_text(json.dumps(sel, indent=1) + "\n")
    print(f"{a.platform}: low {sel['low']} tok/s, high {sel['high']} tok/s, low feasible {sel['low_feasible']}")
    return 0 if sel["low_feasible"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
