"""X2: qualification rule and driver (mock), generator determinism and seeds, freeze ordering and pins (negative paths),
stage driver with injected runners, analysis rules on synthetic cells, harness boundary hook on the mock."""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import build_x2 as bx  # noqa: E402
import freeze_x2_traces as fx  # noqa: E402
import pin_x2  # noqa: E402
import x2_analysis as xa  # noqa: E402
import x2_qualify as xq  # noqa: E402
import x2_stage as xs  # noqa: E402

from quotashift.x2 import qualification as q  # noqa: E402
from quotashift.x2 import snapshot as sn  # noqa: E402

RATES = {"low": 200, "low_feasible": True}


# ------------------------------------------------------------------------------------------------ qualification
def test_design_constants_match_the_sizing_simulation():
    o = json.loads((REPO / "reports" / "x2" / "Q1_POWER.json").read_text())
    assert o["chosen"]["test"] == q.TEST == "T1s" and (o["chosen"]["K"], o["chosen"]["M"]) == (q.K_PAIRS, q.M_PER_SEGMENT)
    assert q.CI_LEVEL == 0.95 and (q.DELTA_ABS_MS, q.DELTA_REL) == (1.0, 0.02) and q.GUARD_S == sn.GUARD_S == 15.0
    assert o["chosen"]["worst_size"] <= q.ALPHA and o["chosen"]["pess"] >= 0.80


def test_t_quantiles_from_frozen_v5_t_cdf():
    for p, df, ref in ((0.975, 63, 1.998341), (0.95, 63, 1.669402), (0.975, 15, 2.131450)):
        assert q.t_ppf(p, df) == pytest.approx(ref, abs=1e-5)


def test_q1_order_balanced():
    o = q.q1_order()
    first = [a for i, (_, a) in enumerate(o) if i % 2 == 0]
    assert first.count("N") == first.count("P") == q.K_PAIRS // 2
    assert sum(i for i, (_, a) in enumerate(o) if a == "P") == sum(i for i, (_, a) in enumerate(o) if a == "N")


def _segs(shift: float, k: int = q.K_PAIRS, m: int = q.M_PER_SEGMENT, jitter: float = 0.2) -> list[dict]:
    out = []
    for j in range(k):
        w = jitter * ((j * 7) % 5 - 2) / 2
        for arm, sh in (("N", 0.0), ("P", shift + w)):
            out.append({"pair": j, "arm": arm, "ttft_ms": [52.0 + sh + 0.01 * i for i in range(m)],
                        "reset_verified": True, "procedure_ok": True})
    return out


def test_q1_decision_pass_fail_and_fail_closed():
    assert q.q1_decide(_segs(0.0))["status"] == "pass"
    assert q.q1_decide(_segs(1.6))["status"] == "fail" and q.q1_decide(_segs(-1.6))["status"] == "fail"
    s = _segs(0.0)
    s[5]["reset_verified"] = False
    assert q.q1_decide(s)["status"] == "fail"
    s = _segs(0.0)
    s[0]["ttft_ms"][3] = None
    assert q.q1_decide(s)["status"] == "fail"
    assert q.q1_decide(_segs(0.0)[:-1])["status"] == "fail"
    s = _segs(0.0)
    s[1]["procedure_ok"] = False
    assert "procedure not verified" in " ".join(q.q1_decide(s)["reasons"])


def test_qualify_mock_runs_phase1_q0_q1(tmp_path):
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "x2_qualify.py"), "--platform", "g1m1", "--mock",
                        "--out-root", str(tmp_path)], capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stderr
    rec = json.loads((tmp_path / "QUALIFICATION_g1m1.json").read_text())
    assert rec["synthetic"] and rec["phase1"]["status"] == "pass" and rec["q1"]["k_pairs"] == 4
    p = [s for s in rec["segments"]["q1"] if s["state"] == "P"]
    assert p and all(s["procedure_ok"] and "snapshot_metrics" in s for s in p)


def test_qualify_refuses_live_without_token_and_mock_inside_repo(monkeypatch):
    monkeypatch.delenv("QUOTASHIFT_APPROVED", raising=False)
    assert any("x2_qual_g0m0" in x for x in xq.live_problems("g0m0"))
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "x2_qualify.py"), "--platform", "g0m0", "--mock",
                        "--out-root", str(REPO / "reports" / "x2" / "tmp")], capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 3


# ------------------------------------------------------------------------------------------------ generator
def test_grid_is_self_calibrated_and_monotone():
    for h in (0.8, 1.35, 2.5):
        g = bx.grid(h)
        assert g == sorted(set(g)) and len(g) == 6
        rho = [bx.predicted_rho(x, h) for x in g]
        assert all(abs(a - b) < 0.04 for a, b in zip(rho, bx.RHO_TARGETS, strict=True))
    with pytest.raises(ValueError):
        bx.grid(0)


def test_generator_deterministic_seeds_and_identity():
    f1 = bx.with_reruns({**bx.build_cal_a("g0m0", 1.35), **bx.build_main("g0m0", RATES)})
    f2 = bx.with_reruns({**bx.build_cal_a("g0m0", 1.35), **bx.build_main("g0m0", RATES)})
    assert bx.digest(f1) == bx.digest(f2) and len(f1) == 2 * (6 + 4)
    for text in f1.values():
        d = yaml.safe_load(text)
        assert d["scenario_id"].startswith("x2_g0m0_") and d["isolation_salt"].startswith("x2-g0m0-")
        assert d["protocol_version"] == 5 and d["comparison"]["preregistered_threshold"] == 1.25
        assert d["seed"] in (bx.CAL_A_SEED0, bx.MAIN_SEED0)
    with pytest.raises(SystemExit):
        bx.build_main("g0m0", {"low": 200, "low_feasible": False})


def test_x2_seeds_disjoint_from_v4_v5_x1():
    used = {*range(42, 47), 900, 1000, 4900, *range(5000, 5010), 4990, *range(7000, 7008), *range(8000, 8024)}
    x2 = {bx.SMOKE_SEED, *range(bx.CAL_A_SEED0, bx.CAL_A_SEED0 + bx.CAL_A_REPS), *range(bx.MAIN_SEED0, bx.MAIN_SEED0 + 24),
          *q.prompt_seeds(), *q.WARMUP_SEEDS, *range(xq.HOLD_SEED_S, xq.HOLD_SEED_D + xq.HOLD_PROBES)}
    a1_prompts = {1, 2, 77, 78, *range(100, 105), *range(200, 280), 900, 901, 902, *range(9000, 9060)}
    assert not x2 & used and not x2 & a1_prompts


def test_choose_low_rule():
    cal = {110: {"rho_ctl": 0.33, "slo_ctl": 0.99}, 190: {"rho_ctl": 0.45, "slo_ctl": 0.98}, 265: {"rho_ctl": 0.58, "slo_ctl": 0.9}}
    assert bx.choose_low(cal) == bx.choose_low(cal) and bx.choose_low(cal)["low"] == 190 and bx.choose_low(cal)["low_feasible"]
    assert not bx.choose_low({110: {"rho_ctl": 0.30, "slo_ctl": 0.99}})["low_feasible"]


# ------------------------------------------------------------------------------------------------ freeze + pins
@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = tmp_path / "x2"
    bx.write(bx.with_reruns({**bx.build_cal_a("g0m0", 1.35), **bx.build_main("g0m0", RATES)}), r)
    return r


def _qual(root: Path, status: str = "pass") -> None:
    (root / "g0m0" / "QUALIFICATION.json").write_text(json.dumps({"status": status, "phase1": {"hold_s_mean": 1.35}}))


def test_freeze_ordering_negative_paths(tmp_path, root):
    rep, res = tmp_path / "rep", tmp_path / "res"
    assert any("qualification" in x for x in fx.ordering_problems("g0m0", "calA", root=root, reports_root=rep, results_root=res))
    _qual(root)
    assert fx.ordering_problems("g0m0", "calA", root=root, reports_root=rep, results_root=res) == []
    _qual(root)
    (root / "g0m0" / "QUALIFICATION.json").write_text(json.dumps({"status": "pass", "phase1": {"hold_s_mean": 2.0}}))
    assert any("generator" in x for x in fx.ordering_problems("g0m0", "calA", root=root, reports_root=rep, results_root=res))
    _qual(root)
    (rep / "g0m0" / "calA").mkdir(parents=True)
    (rep / "g0m0" / "calA" / "STAGE_LOG.json").write_text(json.dumps({"status": "running"}))
    assert any("BEFORE any calA run" in x for x in fx.ordering_problems("g0m0", "calA", root=root, reports_root=rep, results_root=res))
    main = fx.ordering_problems("g0m0", "main", root=root, reports_root=rep, results_root=res)
    assert any("calA has not completed" in x for x in main) and any("RATES.json missing" in x for x in main)


def test_offline_freeze_writes_schedule_then_traces(tmp_path, root, monkeypatch):
    import freeze_v4
    monkeypatch.setattr(freeze_v4, "REPO", tmp_path)       # freeze_v4 (frozen) records repo-relative file paths
    _qual(root)
    from quotashift.workload.tokenize import WhitespaceTokenizer
    sched, traces = fx.freeze("g0m0", "calA", WhitespaceTokenizer(), WhitespaceTokenizer().identity, root=root)
    assert len(sched["scenarios"]) == 12 and len(traces["scenarios"]) == 12


def test_pin_x2_refusals_and_candidate(tmp_path, monkeypatch):
    assert any("has not been made" in x for x in pin_x2.check(tmp_path / "none.json"))
    env = {k: v for k, v in os.environ.items() if k != "QUOTASHIFT_APPROVED"}
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "pin_x2.py"), "--write"], env=env, capture_output=True,
                       text=True, cwd=REPO)
    assert r.returncode == 3 and "x2_freeze1" in r.stderr
    before = pin_x2.MANIFEST.read_bytes()                  # Freeze Commit 1 exists (x2_freeze1); tests never rewrite it
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "pin_x2.py"), "--write"],
                       env={**env, "QUOTASHIFT_APPROVED": "x2_freeze1"}, capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 3 and "never overwritten" in r.stderr and pin_x2.MANIFEST.read_bytes() == before
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "pin_x2.py"), "--pin-phase", "g0m0", "calA"], env=env,
                       capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 3 and "x2_freeze_calA_g0m0" in r.stderr
    assert pin_x2.v5_dependency_problems() == [] and pin_x2.x1_problems() == []
    assert set(pin_x2.V5_DEPENDENCIES) <= set(json.loads((REPO / "experiments/v5/FROZEN_SHA256.json").read_text())["files"])


def test_phase_pin_problems_detect_unpinned_and_tampering(tmp_path, root):
    assert any("not pinned" in x for x in pin_x2.phase_pin_problems("g0m0", "calA", root=root, reports_root=tmp_path))
    _qual(root)
    for n in (fx.SCHED_FILE["calA"], fx.TRACE_FILE["calA"]):
        (root / "g0m0" / n).write_text("{}")
    (root / "g0m0" / "PHASE_PINS.json").write_text(json.dumps({"calA": pin_x2.phase_pin_record("g0m0", "calA", root)}))
    assert pin_x2.phase_pin_problems("g0m0", "calA", root=root, reports_root=tmp_path) == []
    (root / "g0m0" / fx.TRACE_FILE["calA"]).write_text('{"x": 1}')
    assert any("changed since" in x for x in pin_x2.phase_pin_problems("g0m0", "calA", root=root, reports_root=tmp_path))


# ------------------------------------------------------------------------------------------------ stage driver
def fake_runner(fail: set[str] | None = None, start: str = "1.0"):
    def run(src, *, mode, report, results_root, target=None):  # noqa: ANN001, ARG001
        assert json.loads(os.environ["QUOTASHIFT_X2_BOUNDARY"])["transport"] == "mock"
        bad = report.name in (fail or set())
        return {"rc": 5 if bad else 0, "wall_s": 1.0, "failed_gates": [], "server_start": [start],
                "status": "failed" if bad else "passed", "reason": "rc 5" if bad else None}
    return run


def _run(tmp: Path, root: Path, phase: str, runner, **kw) -> int:  # noqa: ANN001
    return xs.run_stage("g0m0", phase, mode="mock", reports_root=tmp / "rep", results_root=tmp / "res",
                        work=tmp / "w", root=root, runner=runner, guard_s=0.0, **kw)


def test_stage_order_qualification_rates_and_env_cleanup(tmp_path, root):
    assert _run(tmp_path, root, "calA", fake_runner()) == 3                  # qualification missing
    _qual(root)
    assert _run(tmp_path, root, "main", fake_runner()) == 3                  # calA not completed
    assert _run(tmp_path, root, "calA", fake_runner()) == 0
    assert "QUOTASHIFT_X2_BOUNDARY" not in os.environ                        # never leaks out of the stage
    assert _run(tmp_path, root, "main", fake_runner()) == 3                  # RATES.json missing
    (root / "g0m0" / "RATES.json").write_text(json.dumps(RATES))
    assert _run(tmp_path, root, "main", fake_runner()) == 0
    log = json.loads((tmp_path / "rep" / "g0m0" / "main" / "STAGE_LOG.json").read_text())
    assert log["protocol"] == "X2" and log["boundary"]["transport"] == "mock"


def test_stage_stop_rerun_and_infeasible(tmp_path, root):
    _qual(root)
    sid = "x2_g0m0_calA_aa_ind_L190_C8"
    assert _run(tmp_path, root, "calA", fake_runner(fail={sid})) == 4
    assert _run(tmp_path, root, "calA", fake_runner()) == 3
    assert _run(tmp_path, root, "calA", fake_runner(), rerun=sid) == 3
    assert _run(tmp_path, root, "calA", fake_runner(), rerun=sid, reason="harness fix") == 0
    (root / "g0m0" / "RATES.json").write_text(json.dumps({"low": 190, "low_feasible": False}))
    assert _run(tmp_path, root, "main", fake_runner()) == 3


def test_live_refuses_without_freeze_and_token(monkeypatch, root):
    monkeypatch.delenv("QUOTASHIFT_APPROVED", raising=False)
    probs = xs.live_problems("g0m0", "calA", interactive_ok=False, root=root)
    assert any("x2_cal_g0m0" in x for x in probs) and not any("Freeze Commit 1" in x for x in probs)  # frozen now
    assert any("interactively" in x for x in probs) and any("not pinned" in x for x in probs)


def test_live_g0_boundary_requires_ssh_host(monkeypatch):
    monkeypatch.delenv("QUOTASHIFT_X2_SSH_HOST", raising=False)
    with pytest.raises(SystemExit):
        xs.boundary_config("g0m0", mode="live")
    assert xs.boundary_config("g1m0", mode="live")["transport"] == "http"


# ------------------------------------------------------------------------------------------------ analysis rules
def _cell(plat: str, block: str, lr: float, n: int, backend: float = 0.0, start: str = "1.0") -> dict:
    rows = []
    for i in range(n):
        e = 0.03 * ((i * 7) % 5 - 2)
        rows.append({"seed": bx.MAIN_SEED0 + i, "E": True, "Vb": True, "log_ratio": lr + e,
                     "attack": {"user_ttft_mean_ms": 100 * math.exp(lr), "backend_ttft_mean_ms": 50 * math.exp(backend + e / 10),
                                "gateway_queue_mean_ms": 1.0, "slo_success": 1.0, "engine_queue": {"sum_s": 0.0, "count": 10.0,
                                "buckets": [(0.3, 10.0), ("+Inf", 10.0)]}, "snapshot": {"available": True, "status": "pass"}},
                     "control": {"user_ttft_mean_ms": 100.0, "backend_ttft_mean_ms": 50.0, "gateway_queue_mean_ms": 1.0,
                                 "slo_success": 1.0, "engine_queue": {"sum_s": 0.0, "count": 10.0,
                                 "buckets": [(0.3, 10.0), ("+Inf", 10.0)]}, "snapshot": {"available": True, "status": "pass"}}})
    return {"cell": bx.cell_id(plat, block, "x", None), "platform": plat, "block": block, "synthetic_backend": True,
            "server_start": [start], "rows": rows, "seeds": [r["seed"] for r in rows]}


def _cells(effect: dict[str, float]) -> dict:
    out = {}
    for p, lr in effect.items():
        out[p] = {"X2a": _cell(p, "X2a", lr, 24), "X2b": _cell(p, "X2b", 0.0, 24), "X2c": _cell(p, "X2c", 0.0, 10),
                  "X2d": _cell(p, "X2d", 0.0, 10)}
    return out


def test_analysis_verdicts_and_inadmissible_platform():
    strong = {p: math.log(1.6) for p in xa.PLATFORMS}
    r = xa.analyse(_cells(strong), {p: True for p in xa.PLATFORMS})
    assert r["verdict"] == "REPLICATES" and r["replicating_platforms"] == 4
    r = xa.analyse(_cells(strong), {"g0m0": False, "g0m1": False, "g1m0": True, "g1m1": True})
    assert r["platforms"]["g0m0"]["H1"]["p"] == 1.0 and r["verdict"] == "REPLICATES-ON-2"
    none = {p: 0.0 for p in xa.PLATFORMS}
    assert xa.analyse(_cells(none), {p: True for p in xa.PLATFORMS})["verdict"] == "NOT REPLICATED AT THIS POWER"


def test_analysis_refuses_interim_looks(tmp_path):
    """Real (non-synthetic) analysis with expected cells of admissible platforms missing -> refused."""
    with pytest.raises(SystemExit):
        xa.run([tmp_path], tmp_path / "out", exp_root=None, admissible_override={p: True for p in xa.PLATFORMS})
    res = xa.run([tmp_path], tmp_path / "out2", exp_root=None, admissible_override={p: False for p in xa.PLATFORMS})
    assert res["verdict"] == "NOT REPLICATED AT THIS POWER" and res["missing_cells"] == []


# ------------------------------------------------------------------------------------------------ harness hook (mock)
def _short(src: Path, dst: Path) -> Path:
    d = yaml.safe_load(src.read_text())
    d.pop("frozen_traces")
    d["runtime_seconds"] = 10
    d["comparison"]["repetitions"] = 2
    for p in d["phases"]:
        p["duration_seconds"], p["request_count"] = 10, max(2, round(p["request_count"] / 12))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(yaml.safe_dump(d, sort_keys=False))
    return dst


@pytest.mark.parametrize("hook", [False, True])
def test_experiment_hook_writes_snapshots_only_when_enabled(tmp_path, hook):
    gen = tmp_path / "gen"
    bx.write(bx.build_main("g0m0", RATES), gen)
    y = _short(next((gen / "g0m0" / "main").glob("*X2a*.yaml")), tmp_path / "s.yaml")
    env = {k: v for k, v in os.environ.items() if k != sn.ENV}
    if hook:
        env[sn.ENV] = json.dumps({"transport": "mock", "guard_s": 0})
    r = subprocess.run([sys.executable, "-m", "quotashift.cli", "experiment", str(y), "--reps", "2", "--mock", "--path",
                        "gateway", "--out", str(tmp_path / "rep"), "--results-root", str(tmp_path / "res")],
                       capture_output=True, text=True, cwd=REPO, env=env)
    assert (tmp_path / "rep" / "manifest.json").exists(), r.stderr[-500:]
    files = list((tmp_path / "res").rglob("x2_host_snapshots.json"))
    assert len(files) == (4 if hook else 0)
    if hook:
        assert xs.snapshot_failures(tmp_path / "rep", tmp_path / "res") == []
