"""X1 trace-freeze ordering (owner review of 9727889). Offline stand-in tokenizer in a temporary tree; no server.

calA traces before any calA run; calB traces after calA completed + rates selected, before any calB run; main traces
after calB completed, together with predictions, before any main run. Pins are re-checked by the stage driver."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import build_x1 as bx  # noqa: E402
import freeze_v4  # noqa: E402
import freeze_x1_traces as fx  # noqa: E402
import pin_x1  # noqa: E402

from quotashift.workload.tokenize import WhitespaceTokenizer  # noqa: E402

PLAT, RATES = "g0m0", {"low": 200, "high": 400, "low_feasible": True}


@pytest.fixture
def tree(tmp_path, monkeypatch) -> dict:
    monkeypatch.setattr(freeze_v4, "REPO", tmp_path)       # freeze_v4 records repo-relative file paths
    root, rep, res = tmp_path / "x1", tmp_path / "rep", tmp_path / "res"
    res.mkdir()
    bx.write(bx.with_reruns(bx.build_cal_a(PLAT, 1.0)), root)
    return {"root": root, "rep": rep, "res": res}


def _freeze_and_pin(t: dict, phase: str) -> dict:
    sched, traces = fx.freeze(PLAT, phase, WhitespaceTokenizer(), {"tokenizer": "whitespace"}, root=t["root"])
    (t["root"] / PLAT / fx.SCHED_FILE[phase]).write_text(json.dumps(sched))
    (t["root"] / PLAT / fx.TRACE_FILE[phase]).write_text(json.dumps(traces))
    assert pin_x1.pin_phase_problems(PLAT, phase, root=t["root"], reports_root=t["rep"], results_root=t["res"]) == []
    pins = t["root"] / PLAT / "PHASE_PINS.json"
    allp = json.loads(pins.read_text()) if pins.exists() else {}
    allp[phase] = pin_x1.phase_pin_record(PLAT, phase, root=t["root"])
    pins.write_text(json.dumps(allp))
    return traces


def _complete(t: dict, phase: str, started: str = "2099-01-01T00:00:00+00:00") -> None:
    d = t["rep"] / PLAT / phase
    d.mkdir(parents=True, exist_ok=True)
    (d / "STAGE_LOG.json").write_text(json.dumps({"status": "completed", "started_utc": started}))


def test_cal_a_traces_frozen_before_any_cal_a_run(tree):
    assert fx.ordering_problems(PLAT, "calA", root=tree["root"], reports_root=tree["rep"], results_root=tree["res"]) == []
    traces = _freeze_and_pin(tree, "calA")
    ids = set(traces["scenarios"])
    files = {p.stem for p in fx.phase_files(PLAT, "calA", tree["root"])}
    assert ids == files and any(i.endswith("__r2") for i in ids)          # reruns frozen with their blocks
    assert pin_x1.phase_pin_problems(PLAT, "calA", root=tree["root"], reports_root=tree["rep"]) == []
    # a calA run that started before the pin is detected
    d = tree["rep"] / PLAT / "calA"
    d.mkdir(parents=True)
    (d / "STAGE_LOG.json").write_text(json.dumps({"status": "running", "started_utc": "2000-01-01T00:00:00+00:00"}))
    assert any("before its pin" in x for x in pin_x1.phase_pin_problems(PLAT, "calA", root=tree["root"],
                                                                        reports_root=tree["rep"]))
    # and freezing is refused once a calA stage log exists
    assert any("BEFORE any calA run" in x for x in fx.ordering_problems(PLAT, "calA", root=tree["root"],
                                                                        reports_root=tree["rep"], results_root=tree["res"]))


def test_cal_b_traces_need_cal_a_complete_and_selected_rates(tree):
    bx.write(bx.with_reruns(bx.build_cal_b(PLAT, RATES)), tree["root"])
    probs = fx.ordering_problems(PLAT, "calB", root=tree["root"], reports_root=tree["rep"], results_root=tree["res"])
    assert any("calA has not completed" in x for x in probs) and any("RATES.json missing" in x for x in probs)
    _complete(tree, "calA")
    (tree["root"] / PLAT / "RATES.json").write_text(json.dumps({"low": 210, "high": 400, "low_feasible": True}))
    probs = fx.ordering_problems(PLAT, "calB", root=tree["root"], reports_root=tree["rep"], results_root=tree["res"])
    assert any("does not match the generator" in x for x in probs)       # files built at other rates are refused
    (tree["root"] / PLAT / "RATES.json").write_text(json.dumps(RATES))
    assert fx.ordering_problems(PLAT, "calB", root=tree["root"], reports_root=tree["rep"], results_root=tree["res"]) == []
    _freeze_and_pin(tree, "calB")
    rec = json.loads((tree["root"] / PLAT / "PHASE_PINS.json").read_text())["calB"]
    assert "rates" in rec and "predictions" not in rec


def test_main_traces_need_cal_b_complete_and_predictions_and_detect_tampering(tree):
    (tree["root"] / PLAT / "RATES.json").write_text(json.dumps(RATES))
    bx.write(bx.with_reruns(bx.build_main(PLAT, RATES)), tree["root"])
    assert any("calB has not completed" in x for x in fx.ordering_problems(
        PLAT, "main", root=tree["root"], reports_root=tree["rep"], results_root=tree["res"]))
    _complete(tree, "calB")
    sched, traces = fx.freeze(PLAT, "main", WhitespaceTokenizer(), {"tokenizer": "whitespace"}, root=tree["root"])
    (tree["root"] / PLAT / fx.SCHED_FILE["main"]).write_text(json.dumps(sched))
    (tree["root"] / PLAT / fx.TRACE_FILE["main"]).write_text(json.dumps(traces))
    assert any("FCFS_PREDICTIONS.json missing" in x for x in pin_x1.pin_phase_problems(
        PLAT, "main", root=tree["root"], reports_root=tree["rep"], results_root=tree["res"]))
    (tree["root"] / PLAT / "FCFS_PREDICTIONS.json").write_text("{}")
    assert pin_x1.pin_phase_problems(PLAT, "main", root=tree["root"], reports_root=tree["rep"], results_root=tree["res"]) == []
    (tree["root"] / PLAT / "PHASE_PINS.json").write_text(json.dumps({"main": pin_x1.phase_pin_record(PLAT, "main",
                                                                                                     root=tree["root"])}))
    assert pin_x1.phase_pin_problems(PLAT, "main", root=tree["root"], reports_root=tree["rep"]) == []
    t = tree["root"] / PLAT / fx.TRACE_FILE["main"]
    t.write_text(t.read_text() + " ")
    assert any("FROZEN_TRACES_MAIN.json changed" in x for x in pin_x1.phase_pin_problems(
        PLAT, "main", root=tree["root"], reports_root=tree["rep"]))
    (tree["res"] / "x1_g0m0_Xa_decode_vs_short_low_C8__attack").mkdir()
    assert any("results for g0m0 exist" in x for x in fx.ordering_problems(
        PLAT, "main", root=tree["root"], reports_root=tree["rep"], results_root=tree["res"]))


def test_generated_files_point_at_their_phase_trace_file(tree):
    import yaml
    for phase, gen in (("calA", bx.build_cal_a(PLAT, 1.0)), ("calB", bx.build_cal_b(PLAT, RATES)),
                       ("main", bx.build_main(PLAT, RATES))):
        for text in gen.values():
            assert yaml.safe_load(text)["frozen_traces"] == f"../{fx.TRACE_FILE[phase]}"


def test_pin_phase_cli_is_approval_gated():
    env = {k: v for k, v in os.environ.items() if k != "QUOTASHIFT_APPROVED"}
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "pin_x1.py"), "--pin-phase", "g0m0", "calA"], cwd=REPO,
                       env=env, capture_output=True, text=True)
    assert r.returncode == 3 and "x1_freeze_calA_g0m0" in r.stderr
