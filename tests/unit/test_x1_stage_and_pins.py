"""X1 stage driver (scripts/x1_stage.py) with injected runners, and X1 pinning (scripts/pin_x1.py). No GPU."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import build_x1 as bx  # noqa: E402
import pin_x1  # noqa: E402
import x1_stage as xs  # noqa: E402

RATES = {"low": 200, "high": 400, "low_feasible": True}


def fake_runner(fail: set[str] | None = None, start: str = "1.0"):
    calls: list[str] = []

    def run(src, *, mode, report, results_root, target=None):  # noqa: ANN001, ARG001
        calls.append(report.name)
        bad = report.name in (fail or set())
        return {"rc": 5 if bad else 0, "wall_s": 1.0, "failed_gates": ["x"] if bad else [], "server_start": [start],
                "status": "failed" if bad else "passed", "reason": "rc 5" if bad else None}
    run.calls = calls  # type: ignore[attr-defined]
    return run


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = tmp_path / "x1"
    bx.write(bx.with_reruns({**bx.build_cal_a("g0m0", 1.0), **bx.build_cal_b("g0m0", RATES),
                             **bx.build_main("g0m0", RATES)}), r)
    return r


def _run(tmp: Path, root: Path, phase: str, runner, **kw) -> int:  # noqa: ANN001
    return xs.run_stage("g0m0", phase, mode="mock", reports_root=tmp / "rep", results_root=tmp / "res",
                        work=tmp / "w", root=root, runner=runner, **kw)


def test_phase_order_rates_and_predictions_required(tmp_path, root):
    assert _run(tmp_path, root, "calB", fake_runner()) == 3                  # calA not completed
    assert _run(tmp_path, root, "calA", fake_runner()) == 0
    assert _run(tmp_path, root, "calB", fake_runner()) == 3                  # RATES.json missing
    (root / "g0m0" / "RATES.json").write_text(json.dumps(RATES))
    assert _run(tmp_path, root, "calB", fake_runner()) == 0
    assert _run(tmp_path, root, "main", fake_runner()) == 3                  # predictions (Freeze 3) missing
    (root / "g0m0" / "FCFS_PREDICTIONS.json").write_text("{}")
    r = fake_runner()
    assert _run(tmp_path, root, "main", r) == 0
    assert [c.split("_")[2] for c in r.calls] == ["Xa", "Xb", "Xc", "Xd", "Xe", "Xf"]


def test_stop_single_rerun_and_server_identity(tmp_path, root):
    _run(tmp_path, root, "calA", fake_runner(fail={"x1_g0m0_calA_aa_ind_L200_C8"}))
    log = json.loads((tmp_path / "rep" / "g0m0" / "calA" / "STAGE_LOG.json").read_text())
    assert log["status"] == "stopped"
    assert _run(tmp_path, root, "calA", fake_runner()) == 3                   # no plain resume
    assert _run(tmp_path, root, "calA", fake_runner(), rerun="x1_g0m0_calA_aa_ind_L200_C8") == 3   # reason needed
    r = fake_runner()
    assert _run(tmp_path, root, "calA", r, rerun="x1_g0m0_calA_aa_ind_L200_C8", reason="harness fix") == 0
    assert r.calls[0] == "x1_g0m0_calA_aa_ind_L200_C8__r2"
    t2 = tmp_path / "b"
    starts = iter([1.0, 1.0, 2.0])
    assert xs.run_stage("g0m0", "calA", mode="mock", reports_root=t2 / "rep", results_root=t2 / "res", work=t2 / "w",
                        root=root, runner=fake_runner(), server_start_fn=lambda: next(starts)) == 4


def test_live_refuses_before_freeze(monkeypatch, root):
    monkeypatch.delenv("QUOTASHIFT_APPROVED", raising=False)
    monkeypatch.delenv("QUOTASHIFT_IN_VPC_RUNNER", raising=False)
    p = "\n".join(xs.live_problems("g0m0", "main", interactive_ok=False, root=root, reports_root=root.parent / "rep"))
    for needle in ("x1_main_g0m0", "interactively", "g0m0/main is not pinned", "HOST_VERIFICATION"):
        assert needle in p, needle


def test_pin_candidate_and_check(tmp_path, monkeypatch):
    assert pin_x1.v5_dependency_problems() == []                          # X1 imports unchanged v5 rules
    assert any("has not been made" in x for x in pin_x1.check(tmp_path / "none.json"))
    man = tmp_path / "m.json"
    man.write_text(json.dumps(pin_x1.manifest("test")))
    assert pin_x1.check(man) == []
    m = json.loads(man.read_text())
    m["files"]["scripts/x1_analysis.py"] = "0" * 64
    man.write_text(json.dumps(m))
    assert any("x1_analysis.py changed" in x for x in pin_x1.check(man))
    monkeypatch.delenv("QUOTASHIFT_APPROVED", raising=False)
    assert pin_x1.MANIFEST.exists() and pin_x1.check() == []            # Freeze Commit 1 executed and intact
    assert os.environ.get("QUOTASHIFT_APPROVED") != "x1_freeze1"
