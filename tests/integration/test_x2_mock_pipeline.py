"""X2 end to end on the in-process MOCK (PLUMBING ONLY; no number is a measurement): self-calibrated calA grid ->
x2_stage (frozen v5 run_block, real `quotashift experiment --mock`, X2 boundary hook on every arm) -> rate selection
from control arms -> main generation -> x2_stage main -> X2 analysis. Shortened arms (10 s), 2 seeds."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import build_x2 as bx  # noqa: E402
import x2_analysis as xa  # noqa: E402
import x2_select_rates as xr  # noqa: E402
import x2_stage as xs  # noqa: E402

PLAT = "g0m0"


def _strip(root: Path) -> None:
    """Mock runs cannot use frozen traces (they are frozen against the live tokenizer); seeds -> 2 for speed."""
    for f in root.rglob("x2_*.yaml"):
        d = yaml.safe_load(f.read_text())
        d.pop("frozen_traces", None)
        d["comparison"]["repetitions"] = min(2, d["comparison"]["repetitions"])
        f.write_text(yaml.safe_dump(d, sort_keys=False))


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory) -> dict:
    t = tmp_path_factory.mktemp("x2mock")
    root, rep, res = t / "x2", t / "rep", t / "res"
    bx.write(bx.build_cal_a(PLAT, 1.35), root)
    _strip(root)
    (root / PLAT / "QUALIFICATION.json").write_text(json.dumps({"status": "pass", "phase1": {"hold_s_mean": 1.35}}))
    rc_cal = xs.run_stage(PLAT, "calA", mode="mock", reports_root=rep, results_root=res, work=t / "w", shorten=10,
                          root=root, guard_s=0.0)
    cal = xr.measure(PLAT, rep)
    rates = bx.choose_low({r: {"rho_ctl": v["rho_ctl"], "slo_ctl": v["slo_ctl"]} for r, v in cal.items()})
    rates["low_feasible"] = True                       # plumbing: the mock's slot demand is not a measurement
    (root / PLAT / "RATES.json").write_text(json.dumps(rates))
    bx.write(bx.build_main(PLAT, rates), root)
    _strip(root)
    rc_main = xs.run_stage(PLAT, "main", mode="mock", reports_root=rep, results_root=res, work=t / "w", shorten=10,
                           root=root, guard_s=0.0)
    return {"t": t, "rep": rep, "res": res, "rc": (rc_cal, rc_main), "cal": cal, "rates": rates}


def test_stages_complete_with_boundary_snapshots_on_every_arm(pipeline):
    assert pipeline["rc"] == (0, 0)
    for phase, n_blocks in (("calA", 6), ("main", 4)):
        log = json.loads((pipeline["rep"] / PLAT / phase / "STAGE_LOG.json").read_text())
        assert log["status"] == "completed" and len(log["blocks"]) == n_blocks and log["boundary"]["transport"] == "mock"
    snaps = list(pipeline["res"].rglob("x2_host_snapshots.json"))
    assert len(snaps) == 2 * 2 * (6 + 4)                     # 2 arms x 2 seeds x 10 blocks
    assert all(json.loads(s.read_text())["metrics"]["synthetic"] for s in snaps)


def test_rate_selection_reads_control_arms_of_every_grid_point(pipeline):
    assert sorted(pipeline["cal"]) == bx.grid(1.35)
    assert all(len(v["rho_ctl_per_seed"]) == 2 and v["rho_ctl"] > 0 for v in pipeline["cal"].values())
    assert pipeline["rates"]["low"] in bx.grid(1.35)


def test_analysis_runs_every_rule_on_the_mock(pipeline):
    res = xa.run([pipeline["rep"] / PLAT / "main"], pipeline["t"] / "ana", exp_root=None)
    assert res["synthetic_backend"] is True
    p = res["platforms"][PLAT]
    for h in ("H1", "H2", "H3", "H4"):
        assert h in p
    assert set(p["host"]) == {"X2a", "X2b", "X2c", "X2d"} and all(v["available"] == v["arms"] for v in p["host"].values())
    assert "verdict" in res and (pipeline["t"] / "ana" / "ANALYSIS_X2.md").exists()
