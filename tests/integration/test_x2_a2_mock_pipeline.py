"""X2 Amendment A2 end to end on the in-process MOCK (PLUMBING ONLY; no number is a measurement): the committed A2
main files -> x2_a2_stage (frozen x2_stage.run_stage, frozen v5 block runner, real `quotashift experiment --mock`
subprocess, X2 boundary hook on every arm) -> X2 analysis. Full 120 s windows (the mock runs in simulated time; a
shortened window scales the competitor counts below N = 4, where no arrival law can guarantee the frozen coverage gate),
2 seeds. Also proves the harness subprocess applied the A2 arrival law and the frozen runtime coverage gate passed:
every recorded competitor arrival sits one per stratum of [0, T)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import x2_a2_stage as st  # noqa: E402
import x2_analysis as xa  # noqa: E402

PLAT = "g1m0"
SHORT = 120                   # = runtime_seconds: counts unchanged (N >= 4 in every arm)


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory) -> dict:
    t = tmp_path_factory.mktemp("x2a2mock")
    root, rep, res = t / "x2a2", t / "rep", t / "res"
    shutil.copytree(REPO / "experiments" / "x2_a2" / PLAT, root / PLAT)
    for f in root.rglob("x2_*.yaml"):
        d = yaml.safe_load(f.read_text())
        assert d["protocol_amendment"] == "X2-A2"
        d.pop("frozen_traces", None)          # frozen against the live tokenizer
        d["comparison"]["repetitions"] = min(2, d["comparison"]["repetitions"])
        f.write_text(yaml.safe_dump(d, sort_keys=False))
    (rep / PLAT / "calA").mkdir(parents=True)
    (rep / PLAT / "calA" / "STAGE_LOG.json").write_text(json.dumps({"status": "completed", "mode": "mock"}))
    rc = st.run(PLAT, mode="mock", reports_root=rep, results_root=res, root=root, work=t / "w", shorten=SHORT,
                guard_s=0.0)
    return {"t": t, "rep": rep, "res": res, "rc": rc}


def test_a2_stage_completes_with_marker_and_boundary_snapshots(pipeline):
    assert pipeline["rc"] == 0
    log = json.loads((pipeline["rep"] / PLAT / "main" / "STAGE_LOG.json").read_text())
    assert log["status"] == "completed" and log["amendment"] == "X2-A2" and len(log["blocks"]) == 4
    assert log["boundary"]["transport"] == "mock"
    assert all(b["status"] == "passed" for b in log["blocks"].values())
    snaps = list(pipeline["res"].rglob("x2_host_snapshots.json"))
    assert len(snaps) == 2 * 2 * 4 and all(json.loads(s.read_text())["metrics"]["synthetic"] for s in snaps)


def test_harness_subprocess_used_the_stratified_law(pipeline):
    runs = list(pipeline["res"].rglob("requests.parquet"))
    assert len(runs) == 16
    for f in runs:
        r = pd.read_parquet(f, columns=["workload_class", "trace_arrival_s"])
        c = sorted(r[r.workload_class == "competitor"].trace_arrival_s)
        n = len(c)
        assert n >= 4 and [int(x // (SHORT / n)) for x in c] == list(range(n)), (f, c)


def test_analysis_runs_on_the_a2_mock(pipeline):
    res = xa.run([pipeline["rep"] / PLAT / "main"], pipeline["t"] / "ana", exp_root=None)
    assert res["synthetic_backend"] is True and "H1" in res["platforms"][PLAT]
