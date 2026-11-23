"""Protocol v5 run-level loader end to end on the in-process mock (§9 item 8). PLUMBING ONLY: shortened copies of the
12 stage-A YAMLs (10 s window, counts / 12, no frozen traces, 3 seeds) run through `quotashift experiment --mock`, then
`scripts/v5_analysis.py` loads every report and applies every rule. No number here is a measurement."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import v5_analysis as va  # noqa: E402

REPS = 3


@pytest.fixture(scope="module")
def stage_a_reports(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("v5mock")
    reps, res, ydir = root / "rep", root / "res", root / "y"
    ydir.mkdir()
    for f in sorted((REPO / "experiments" / "v5" / "stage_a").glob("*.yaml")):
        d = yaml.safe_load(f.read_text())
        d.pop("frozen_traces")
        d["runtime_seconds"] = 10
        for p in d["phases"]:
            p["duration_seconds"], p["request_count"] = 10, max(2, round(p["request_count"] / 12))
        y = ydir / f.name
        y.write_text(yaml.safe_dump(d, sort_keys=False))
        r = subprocess.run([sys.executable, "-m", "quotashift.cli", "experiment", str(y), "--reps", str(REPS), "--mock",
                            "--path", "direct" if f.stem.endswith("_direct") else "gateway", "--out", str(reps / f.stem),
                            "--results-root", str(res)], capture_output=True, text=True, cwd=REPO)
        assert (reps / f.stem / "manifest.json").exists(), (f.stem, r.returncode, r.stderr[-800:])
    return reps


def test_loader_covers_every_stage_a_cell_and_rule(stage_a_reports, tmp_path):
    res = va.run([stage_a_reports], "A", tmp_path)
    assert res["synthetic_backend"] is True
    assert res["seed_set_matches_protocol"] is False  # 3 plumbing seeds, not the protocol's 5000..5009
    assert res["missing_cells"] == [] and sorted(res["cells"]) == sorted(va.expected_cells("A"))
    h = res["hypotheses"]
    assert set(h) == {"H1", "H2a", "H2b", "H3", "H4", "H5", "H6"}
    assert set(h["H6"]) == {"C8", "C16", "C32"}
    # direct cells are not FCFS-predicted; every gateway cell x arm is scored
    assert set(h["H3"]["scores"]) == {f"{c}/{a}" for c in res["cells"] if not c.endswith("_direct") for a in ("attack", "control")}
    for c in res["cells"].values():
        assert c["summary"]["stratum"] in ("E&Vb", "E&notVb", "notE")
        assert len(c["per_seed"]) == REPS
        assert c["summary"]["threshold_above_noise"] is not None  # every stage-A (C, L) has an A/A-ind reference
    md = (tmp_path / "ANALYSIS_A.md").read_text()
    assert "SYNTHETIC BACKEND" in md
    json.loads((tmp_path / "analysis_A.json").read_text())
    with pytest.raises(SystemExit, match="overwrite"):
        va.run([stage_a_reports], "A", tmp_path)


def test_loader_reproduces_report_columns(stage_a_reports):
    """The loader's per-seed primary is exactly the summary.csv victim means; tail mass uses the same population."""
    rep = stage_a_reports / "v5_decode_vs_short_L200_C8"
    cell = va.load_cell(rep)
    df = pd.read_csv(rep / "summary.csv")
    for r in cell["rows"]:
        a = df[(df.seed == r["seed"]) & (df.arm == "attack")].iloc[0]
        c = df[(df.seed == r["seed"]) & (df.arm == "control")].iloc[0]
        assert math.isclose(r["log_ratio"], math.log(a.victim_user_ttft_mean_ms / c.victim_user_ttft_mean_ms))
        v = va._victims(va._resolve_run(a.run_dir))
        assert math.isclose(v.user_ttft_ms.mean(), a.victim_user_ttft_mean_ms, rel_tol=1e-9)
        assert r["attack"]["configured_cap"] == 8 and r["attack"]["slot"]["occ_max"] <= 8


def test_incomplete_real_stage_is_refused(stage_a_reports, tmp_path, monkeypatch):
    """No interim looks: on non-synthetic data an incomplete stage is refused before any endpoint is computed."""
    one = tmp_path / "partial"
    one.mkdir()
    (one / "v5_decode_vs_short_L200_C8").symlink_to(stage_a_reports / "v5_decode_vs_short_L200_C8")
    real = va.load_cell
    monkeypatch.setattr(va, "load_cell", lambda rep: real(rep) | {"synthetic_backend": False})
    with pytest.raises(SystemExit, match="incomplete"):
        va.run([one], "A", tmp_path / "out")


def _synthetic_ten(cell: dict, log_ratios: list[float]) -> dict:
    """Rule-wiring fixture: copy a mock cell's first row to the 10 protocol seeds with chosen per-seed log ratios."""
    base = cell["rows"][0]
    rows = [base | {"seed": s, "E": True, "Vb": True, "log_ratio": lr, "log_ratio_p95": lr}
            for s, lr in zip(va.SEEDS, log_ratios, strict=True)]
    return cell | {"rows": rows, "seeds": list(va.SEEDS)}


def test_rule_wiring_on_evaluable_cells(stage_a_reports):
    """H1/H2a/H2b (F1 Holm) and H6 (F2 Holm) are wired to the right cells once every cell is E&Vb with 10 seeds."""
    cells = {p.name: va.load_cell(p) for p in sorted(stage_a_reports.iterdir()) if va.CELL_RE.fullmatch(p.name)}
    jit = [0.02 * ((i % 3) - 1) for i in range(10)]
    big = {8: 0.6, 16: 0.3, 32: 0.0}  # D vs S: log 1.82 at C=8, vanishing by C=32
    for k in cells:
        if k.startswith("v5_decode_vs_short"):
            m = big.get(cells[k]["C"], 0.0)
            cells[k] = _synthetic_ten(cells[k], [m + j for j in jit])
        else:  # A/A-ind and P vs S: no effect, tight
            cells[k] = _synthetic_ten(cells[k], jit)
    h = va.analyse(cells, "A")["hypotheses"]
    assert h["H1"]["verdict"] == "supported" and h["H1"]["holm_reject"]
    assert h["H2a"]["verdict"] == "supported" and h["H2a"]["ratio_change_per_doubling"] < 1
    assert h["H2b"]["verdict"] == "equivalent"
    assert {v["verdict"] for v in h["H6"].values()} == {"equivalent"}
    # a single non-E&Vb cell makes only the hypotheses that need it non-evaluable (no seed dropping)
    k32 = "v5_decode_vs_short_L200_C32"
    cells[k32] = cells[k32] | {"rows": [r | {"Vb": False} if r["seed"] == 5003 else r for r in cells[k32]["rows"]]}
    h = va.analyse(cells, "A")["hypotheses"]
    assert h["H1"]["verdict"] == "supported"
    assert h["H2a"]["verdict"] == "not_evaluable" and h["H2b"]["verdict"] == "not_evaluable"


def test_mock_applies_the_cell_cap(stage_a_reports):
    """The in-process simulator now applies max_concurrency_cap like the live runner; cap_configured passes."""
    for name in ("v5_decode_vs_short_L200_C8", "v5_decode_vs_short_L200_C16", "v5_decode_vs_short_L200_direct"):
        man = json.loads((stage_a_reports / name / "manifest.json").read_text())
        g = {c["name"]: c for c in man["validity"]["checks"]}
        assert g["cap_configured"]["passed"], g["cap_configured"]
        assert "occupancy_reconstruction" in g


def test_server_identity_stage_gate(stage_a_reports):
    cells = {p.name: va.load_cell(p) for p in sorted(stage_a_reports.iterdir()) if va.CELL_RE.fullmatch(p.name)}
    assert va.server_identity(cells)["applicable"] is False
    real = {k: c | {"synthetic_backend": False, "server_start": ["1795268683.89"]} for k, c in cells.items()}
    assert va.server_identity(real)["passed"]
    k = "v5_aa_ind_L200_C16"
    real[k] = real[k] | {"server_start": ["1795999999.00"]}
    sid = va.server_identity(real)
    assert not sid["passed"] and sid["failed_stages"] == ["A"]
