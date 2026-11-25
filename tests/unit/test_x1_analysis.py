"""X1 analysis rules (scripts/x1_analysis.py). Synthetic per-seed tables + one equivalence check of the X1 loader
against the frozen v5 loader on a real (local, git-ignored) v5 Stage A report when it is present."""

from __future__ import annotations

import json
import math
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import v5_analysis as va  # noqa: E402
import x1_analysis as xa  # noqa: E402

V5_CELL = REPO / "reports" / "v5" / "stage_a" / "v5_decode_vs_short_L200_C8"


@pytest.mark.skipif(not (V5_CELL / "manifest.json").exists(), reason="local v5 raw report not present")
def test_x1_loader_reproduces_the_v5_per_seed_table(tmp_path):
    dst = tmp_path / "x1_g0m0_Xa_decode_vs_short_low_C8"
    dst.mkdir()
    for f in ("manifest.json", "summary.csv"):
        shutil.copy(V5_CELL / f, dst / f)
    v5 = va.load_cell(V5_CELL)["rows"]
    x1 = xa.load_x1_cell(dst)["rows"]
    for a, b in zip(v5, x1, strict=True):
        for arm in ("attack", "control"):
            b[arm].pop("run_dir")
        assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def _row(seed: int, ratio: float, backend_ratio: float = 1.0, *, slo: float = 1.0, eq_ms: float = 0.003) -> dict:
    def arm(ttft: float, be: float) -> dict:
        return {"user_ttft_mean_ms": ttft, "backend_ttft_mean_ms": be, "gateway_queue_mean_ms": max(0.0, ttft - be),
                "slo_success": slo, "engine_queue": {"sum_s": eq_ms / 1000 * 100, "count": 100.0,
                                                     "buckets": [[0.3, 100.0], ["+Inf", 100.0]]},
                "slot": {"h3_obs_victim_queue_mean_ms": max(0.0, ttft - be)}, "run_dir": "/nonexistent"}
    return {"seed": seed, "E": True, "Vb": True, "log_ratio": math.log(ratio),
            "attack": arm(85.0 * ratio, 85.0 * backend_ratio), "control": arm(85.0, 85.0)}


def _cell(plat: str, block: str, ratios: list[float], **kw) -> dict:  # noqa: ANN003
    return {"cell": f"x1_{plat}_{block}", "platform": plat, "block": block, "synthetic_backend": True,
            "server_start": [], "rows": [_row(8000 + i, r, **kw) for i, r in enumerate(ratios)]}


def _platform(plat: str, xa: float, *, spread: float = 0.05) -> dict:
    n24 = [xa * math.exp(spread * ((i % 5) - 2)) for i in range(24)]
    eq = [math.exp(0.01 * ((i % 5) - 2)) for i in range(10)]
    return {"Xa": _cell(plat, "Xa", n24), "Xb": _cell(plat, "Xb", eq), "Xc": _cell(plat, "Xc", eq),
            "Xd": _cell(plat, "Xd", [math.exp(0.02 * ((i % 5) - 2)) for i in range(24)]),
            "Xe": _cell(plat, "Xe", [5.0] * 10), "Xf": _cell(plat, "Xf", eq)}


def test_generalises_when_three_of_four_platforms_carry_the_mechanism():
    cells = {"g0m0": _platform("g0m0", 1.6), "g0m1": _platform("g0m1", 1.5), "g1m0": _platform("g1m0", 1.7),
             "g1m1": _platform("g1m1", 1.0)}
    res = xa.analyse(cells, {p: None for p in cells})
    assert res["counts"]["H1"] == 3 and res["verdict"] == "GENERALISES"
    assert res["platforms"]["g1m1"]["H1"]["supported"] is False
    assert all(res["platforms"][p]["H2"]["equivalent"] and res["platforms"][p]["H4"]["holds"] for p in cells)
    assert res["platforms"]["g0m0"]["H5"]["verdict"] == "not_evaluable"          # no frozen predictions given


def test_anchor_only_and_partial():
    one = {"g0m0": _platform("g0m0", 1.6), **{p: _platform(p, 1.0) for p in ("g0m1", "g1m0", "g1m1")}}
    assert xa.analyse(one, {})["verdict"] == "ANCHOR-ONLY"
    two = {"g0m0": _platform("g0m0", 1.6), "g0m1": _platform("g0m1", 1.6), "g1m0": _platform("g1m0", 1.0),
           "g1m1": _platform("g1m1", 1.0)}
    assert xa.analyse(two, {})["verdict"] == "PARTIAL"


def test_h4_fails_when_backend_moves_or_engine_queues():
    cells = {p: _platform(p, 1.6) for p in xa.PLATFORMS}
    cells["g1m0"]["Xa"] = _cell("g1m0", "Xa", [1.6] * 24, backend_ratio=1.2)
    cells["g1m1"]["Xa"] = _cell("g1m1", "Xa", [1.6] * 24, eq_ms=50.0)
    res = xa.analyse(cells, {})
    assert res["platforms"]["g1m0"]["H4"]["holds"] is False and res["platforms"]["g1m1"]["H4"]["holds"] is False
    assert res["counts"]["H4"] == 2 and res["verdict"] == "PARTIAL"


def test_not_evaluable_platform_enters_holm_with_p_one():
    cells = {p: _platform(p, 1.6) for p in xa.PLATFORMS}
    for r in cells["g1m1"]["Xa"]["rows"]:
        r["Vb"] = False
    res = xa.analyse(cells, {})
    assert res["families"]["F-X1"]["g1m1"] == 1.0 and res["platforms"]["g1m1"]["H1"]["evaluable"] is False


def test_host_limited_label_on_a_flagged_differing_gpu_contrast(tmp_path):
    cells = {p: _platform(p, 1.6) for p in xa.PLATFORMS}
    cells["g1m0"]["Xa"] = _cell("g1m0", "Xa", [1.0] * 24)
    t0 = 1_800_000_000.0
    for i, r in enumerate(cells["g1m0"]["Xa"]["rows"]):                 # give every arm a real window
        for k, arm in enumerate(("attack", "control")):
            d = tmp_path / f"run{i}{k}"
            d.mkdir()
            start = t0 + (2 * i + k) * 200
            (d / "manifest.json").write_text(json.dumps({"created_wall_utc": datetime.fromtimestamp(start, UTC).isoformat()}))
            r[arm]["run_dir"] = str(d)
    hot = [{"t": j, "ts": t0 + j, "host_busy": 0.9, "api_cpu": 0.9, "mem_available": 8 * 2**30, "oom_kill": 0,
            "pswpin": 0} for j in range(0, 24 * 400, 1)]
    res = xa.analyse(cells, {}, host={"g1m0": hot})
    assert res["platforms"]["g1m0"]["D2"]["Xa"]["flag"] is True
    assert res["platforms"]["g1m0"]["gpu_contrast"]["H1"] == "GPU+host, host-limited"
    assert res["platforms"]["g1m0"]["gpu_contrast"]["H2"] == "same"
    quiet = [dict(x, host_busy=0.2, api_cpu=0.2) for x in hot]
    res2 = xa.analyse({p: _platform(p, 1.6) for p in xa.PLATFORMS} | {"g1m0": cells["g1m0"]}, {}, host={"g1m0": quiet})
    assert res2["platforms"]["g1m0"]["gpu_contrast"]["H1"] == "differs"   # not flagged -> reported as a GPU contrast
