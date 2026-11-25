"""X1 pipeline end to end on the in-process MOCK (PLUMBING ONLY; no number here is a measurement):
generator -> calibration-B runs -> X1-H5 predictions (before any main run; leakage guard) -> main-stage runs ->
X1 analysis with predictions. Shortened copies: 10 s window, counts / 12, at most 3 seeds, no frozen traces."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import build_x1 as bx  # noqa: E402
import x1_analysis as xa  # noqa: E402
import x1_predictions as xp  # noqa: E402

PLAT, RATES, REPS = "g0m0", {"low": 200, "high": 400, "low_feasible": True}, 3


def _shorten(src: Path, dst: Path) -> Path:
    d = yaml.safe_load(src.read_text())
    d.pop("frozen_traces")
    d["runtime_seconds"] = 10
    d["comparison"]["repetitions"] = min(REPS, d["comparison"]["repetitions"])
    for p in d["phases"]:
        p["duration_seconds"], p["request_count"] = 10, max(2, round(p["request_count"] / 12))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(yaml.safe_dump(d, sort_keys=False))
    return dst


def _run_dir(ys: list[Path], rep: Path, res: Path) -> None:
    for y in ys:
        r = subprocess.run([sys.executable, "-m", "quotashift.cli", "experiment", str(y), "--reps",
                            str(yaml.safe_load(y.read_text())["comparison"]["repetitions"]), "--mock", "--path",
                            "direct" if y.stem.endswith("_direct") else "gateway", "--out", str(rep / y.stem),
                            "--results-root", str(res)], capture_output=True, text=True, cwd=REPO)
        assert (rep / y.stem / "manifest.json").exists(), (y.stem, r.returncode, r.stderr[-600:])


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory) -> dict:
    t = tmp_path_factory.mktemp("x1mock")
    gen = t / "gen"
    bx.write({**bx.build_cal_b(PLAT, RATES), **bx.build_main(PLAT, RATES)}, gen)
    calb = [_shorten(p, t / "short" / "calB" / p.name) for p in sorted((gen / PLAT / "calB").glob("x1_*.yaml"))]
    main = [_shorten(p, t / "short" / "main" / p.name) for p in sorted((gen / PLAT / "main").glob("x1_*.yaml"))]
    res = t / "results"
    _run_dir(calb, t / "rep" / PLAT / "calB", res)
    preds = xp.build(PLAT, t / "rep" / PLAT / "calB", t / "short" / "main", res)      # BEFORE any main run
    (t / "pred" / PLAT).mkdir(parents=True)
    (t / "pred" / PLAT / "FCFS_PREDICTIONS.json").write_text(json.dumps(preds, default=float))
    _run_dir(main, t / "rep" / PLAT / "main", res)
    return {"t": t, "preds": preds, "res": res}


def test_predictions_cover_the_h5_cells_from_calibration_only(pipeline):
    p = pipeline["preds"]
    assert sorted(c["block"] for c in p["cells"].values()) == ["Xa", "Xb", "Xe"]
    assert p["tolerances"]["tau_abs_ms"] >= 5.0 and p["tolerances"]["rho_source"] in ("loso", "v5_fallback")
    assert all("calB" in k for k in p["pool_inputs_sha256"])                       # pools: calibration B only
    for c in p["cells"].values():
        assert sorted(c["seeds"]) == ["8000", "8001", "8002"]


def test_leakage_guard_refuses_after_main_results_exist(pipeline):
    t = pipeline["t"]
    with pytest.raises(SystemExit, match="leakage guard"):
        xp.build(PLAT, t / "rep" / PLAT / "calB", t / "short" / "main", pipeline["res"])


def test_analysis_runs_every_rule_on_the_mock(pipeline):
    t = pipeline["t"]
    res = xa.run([t / "rep"], t / "out", predictions_root=t / "pred")
    assert res["synthetic_backend"] is True and res["seed_sets_match_protocol"] is False   # 3 plumbing seeds
    assert sorted(res["cells"][PLAT]) == ["Xa", "Xb", "Xc", "Xd", "Xe", "Xf"]
    pr = res["platforms"][PLAT]
    assert set(pr) >= {"H1", "H2", "H3", "H4", "H5", "D1", "D2", "server_identity"}
    assert len(pr["H5"]["scores"]) == 6                                             # Xa, Xb, Xe x 2 arms
    assert res["verdict"] in ("GENERALISES", "ANCHOR-ONLY", "PARTIAL")
    assert "SYNTHETIC BACKEND" in (t / "out" / "ANALYSIS_X1.md").read_text()
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        xa.run([t / "rep"], t / "out", predictions_root=t / "pred")
