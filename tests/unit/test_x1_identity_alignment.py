"""X1-specific identity checks and host-telemetry clock alignment (owner review of 9727889, item 5)."""

from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests" / "unit"))
import x1_analysis as xa  # noqa: E402
from test_x1_analysis import _cell, _platform  # noqa: E402

from quotashift.config import BackendConfig  # noqa: E402
from quotashift.runtime.runner import local_mock_server  # noqa: E402
from quotashift.x1 import preflight as pf  # noqa: E402
from quotashift.x1.tokenize_probe import clock_offset_probe  # noqa: E402


def _real(plat: str, cells: dict, *, model: str | None = None, version: str = '{"version": "0.17.1"}',
          revision: str | None = None, drop_gate: str | None = None, start: str = "1.0") -> dict:
    exp = xa.build_x1.PLATFORMS[plat]
    for b, c in cells.items():
        c["synthetic_backend"] = False
        c["server_start"] = [start]
        c["scenario_id"] = f"x1_{plat}_{b}_x"
        c["protocol_version"] = 5
        c["gates"] = [g for g in xa.V5_GATES if g != drop_gate]
        c["provenance"] = {"model": [model or exp["model"]], "vllm_version": [version],
                           "model_revision_server_reported": revision or exp["revision"]}
    return cells


def test_identity_passes_and_each_mismatch_makes_the_platform_not_evaluable():
    base = {p: _real(p, _platform(p, 1.6)) for p in xa.PLATFORMS}
    res = xa.analyse(base, {})
    assert all(res["platforms"][p]["platform_identity"]["passed"] for p in xa.PLATFORMS) and res["verdict"] == "GENERALISES"
    for kw, needle in (({"model": "Qwen/Other"}, "model"), ({"version": '{"version": "0.34.0"}'}, "vLLM"),
                       ({"revision": "f" * 40}, "revision"), ({"drop_gate": "cap_configured"}, "gates missing")):
        cells = {p: _real(p, _platform(p, 1.6), **(kw if p == "g1m1" else {})) for p in xa.PLATFORMS}
        r = xa.analyse(cells, {})
        pi = r["platforms"]["g1m1"]["platform_identity"]
        assert not pi["passed"] and any(needle in x for x in pi["problems"]), (kw, pi)
        assert r["platforms"]["g1m1"]["H1"]["evaluable"] is False and r["families"]["F-X1"]["g1m1"] == 1.0


def test_server_restart_within_a_platform_blocks_its_hypotheses():
    cells = {p: _real(p, _platform(p, 1.6)) for p in xa.PLATFORMS}
    cells["g0m1"]["Xe"]["server_start"] = ["2.0"]
    r = xa.analyse(cells, {})
    assert not r["platforms"]["g0m1"]["server_identity"]["passed"] and not r["platforms"]["g0m1"]["H1"]["evaluable"]


def test_clock_offset_shifts_the_arm_window(tmp_path):
    c = _cell("g1m0", "Xa", [1.6])
    d = tmp_path / "run"
    d.mkdir()
    t0 = 1_800_000_000.0
    (d / "manifest.json").write_text(json.dumps({"created_wall_utc": datetime.fromtimestamp(t0, UTC).isoformat()}))
    for arm in ("attack", "control"):
        c["rows"][0][arm]["run_dir"] = str(d)
    # the GPU host clock runs 60 s ahead: its hot samples are at t0+60 .. t0+210
    hot = [{"ts": t0 + 60 + j, "host_busy": 0.99, "api_cpu": 0.99, "mem_available": 8 * 2**30, "oom_kill": 0,
            "pswpin": 0} for j in range(150)]
    cold = [{"ts": t0 + j, "host_busy": 0.1, "api_cpu": 0.1, "mem_available": 8 * 2**30, "oom_kill": 0, "pswpin": 0}
            for j in range(60)]
    assert xa.host_flags(c, cold + hot, offset_s=0.0)["arms"]["8000/attack"]["status"] == "flag"   # mixes windows
    assert xa.host_flags(c, cold + hot, offset_s=60.0)["arms"]["8000/attack"]["cpu"] == "flag"
    assert xa.host_flags(c, cold, offset_s=0.0)["arms"]["8000/attack"]["status"] == "pass"


def test_clock_offset_rule():
    assert pf.clock_offset_check(0.4, 0.5)["status"] == "pass"
    assert pf.clock_offset_check(1.8, 0.5)["status"] == "flag"
    assert pf.clock_offset_check(-4.9, 0.5)["status"] == "fail"
    assert pf.clock_offset_check(None, None)["status"] == "fail"


def test_date_header_probe_on_the_local_mock():
    with local_mock_server(BackendConfig(kind="mock_http", model="mock-model", time_scale=1.0)) as url:
        r = clock_offset_probe(url, n=12)
    assert r["offset_s"] is not None and abs(r["offset_s"]) < 1.5 and r["bound_s"] <= 1.0, r
    assert pf.clock_offset_check(r["offset_s"], r["bound_s"])["status"] == "pass"
    assert math.isfinite(r["offset_s"])
