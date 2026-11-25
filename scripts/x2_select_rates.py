"""X2 low-point selection after calibration A (docs/PROTOCOL_X2_DRAFT.md rev 2 section 5.2; build_x2.choose_low).

    uv run python scripts/x2_select_rates.py --platform g0m0         # -> experiments/x2/<plat>/RATES.json

Per calibration-A grid point (A/A-ind short-short at C = 8, seeds 22000-22002), from CONTROL arms only:
  rho_ctl = mean over control runs of  sum over all requests (t_terminal - t_sent) / (8 x 120 s)
  slo_ctl = mean control victim offered-load SLO success (summary.csv)
Refuses unless the calA stage log is `completed` and every grid block passed (or its single rerun did). Never
substitutes a rate: the output is whatever the rule returns, including an infeasible low point.
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
import build_x2  # noqa: E402
import v5_analysis as va  # noqa: E402  (frozen; run-dir resolution only)

WINDOW_S = float(build_x2.RUNTIME)


def control_slot_demand(run: Path) -> float:
    r = pd.read_parquet(run / "requests.parquet", columns=["t_sent", "t_terminal"]).dropna()
    return float((r.t_terminal - r.t_sent).sum() / (build_x2.CAP * WINDOW_S))


def measure(plat: str, reports_root: Path) -> dict[int, dict]:
    st = reports_root / plat / "calA"
    log = json.loads((st / "STAGE_LOG.json").read_text())
    if log.get("status") != "completed":
        raise SystemExit(f"REFUSED: {plat}/calA stage status {log.get('status')} (must be completed)")
    out: dict[int, dict] = {}
    for sid in log["order"]:
        b, r2 = log["blocks"].get(sid), log["blocks"].get(f"{sid}{build_x2.RERUN}")
        use = sid if b and b.get("status") == "passed" else (f"{sid}{build_x2.RERUN}" if r2 and r2.get("status") == "passed" else None)
        if use is None:
            raise SystemExit(f"REFUSED: {sid} has no passed block")
        rep = st / use
        man = json.loads((rep / "manifest.json").read_text())
        ctl = pd.read_csv(rep / "summary.csv")
        ctl = ctl[ctl.arm == "control"]
        rhos = [control_slot_demand(va._resolve_run(d)) for d in man["run_dirs"]["control"].values()]
        m = re.search(r"_L(\d+)_C8", sid)
        if not m:
            raise SystemExit(f"REFUSED: unexpected calA block id {sid}")
        out[int(m.group(1))] = {"rho_ctl": sum(rhos) / len(rhos), "rho_ctl_per_seed": rhos,
                                "slo_ctl": float(ctl.victim_slo_success_offered.mean()), "block": use,
                                "seeds": sorted(int(s) for s in ctl.seed)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", choices=tuple(build_x2.PLATFORMS), required=True)
    ap.add_argument("--reports-root", default=str(REPO / "reports" / "x2"))
    ap.add_argument("--out-root", default=str(REPO / "experiments" / "x2"))
    a = ap.parse_args()
    out = Path(a.out_root) / a.platform / "RATES.json"
    if out.exists():
        print(f"REFUSED: {out} exists (rates are selected once)", file=sys.stderr)
        return 3
    cal = measure(a.platform, Path(a.reports_root))
    sel = build_x2.choose_low({r: {"rho_ctl": v["rho_ctl"], "slo_ctl": v["slo_ctl"]} for r, v in cal.items()})
    sel |= {"platform": a.platform, "selected_utc": datetime.now(UTC).isoformat(),
            "rule_source": "scripts/build_x2.py choose_low", "measurement": {str(r): cal[r] for r in sorted(cal)}}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sel, indent=1) + "\n")
    print(f"{a.platform}: low {sel['low']} tok/s, low feasible {sel['low_feasible']}")
    return 0 if sel["low_feasible"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
