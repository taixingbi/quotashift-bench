"""Protocol v4 (docs/PROTOCOL_V4.md): spec-generated YAMLs, fixed-count workloads, full-window token-matched control,
frozen traces, new gates, and the R1/R2/R3 analysis on mock runs (plumbing only, never GPU evidence)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import yaml

from quotashift.local import FrozenTraceMismatch, check_frozen, paired_traces
from quotashift.scenario import ScenarioConfig, load_scenario
from quotashift.workload.generator import trace_hash
from quotashift.workload.tokenize import WhitespaceTokenizer, verify_trace

REPO = Path(__file__).resolve().parents[2]
V4 = REPO / "experiments" / "v4"


def _mod(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(m)
    return m


def test_v4_files_are_exactly_the_generated_spec():
    r = subprocess.run([sys.executable, str(REPO / "scripts/build_v4.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_v4_scenario_validates_with_v4_invariants():
    files = sorted(V4.rglob("*.yaml"))
    assert len(files) == 45  # 9 calibration + 9 R1 + 14 R2 + 9 R3 + 4 smoke
    for f in files:
        sc = load_scenario(f)
        assert sc.protocol_version == 4 and sc.prompt_token_unit == "tokenizer" and sc.ignore_eos
        assert sc.safety.max_global_inflight == 8 and sc.gateway is None and sc.cache_reset == "none"
        assert sc.comparison.preregistered_threshold == 1.25 and sc.frozen_traces == "../FROZEN_TRACES.json"
        assert all(p.request_count is not None for p in sc.phases)


def _sc(**upd) -> ScenarioConfig:
    base = yaml.safe_load((V4 / "r1/v4_r1_prefill_vs_short_L200.yaml").read_text())
    base.update(upd)
    return ScenarioConfig.model_validate(base)


def test_v4_schema_fails_closed():
    with pytest.raises(ValueError, match="tokenizer"):
        _sc(prompt_token_unit="whitespace")
    with pytest.raises(ValueError, match="together"):
        _sc(phases=[{"name": "main", "duration_seconds": 120, "input_tokens": 64, "request_count": 5}])
    with pytest.raises(ValueError, match="either rate_rps or request_count"):
        _sc(phases=[{"name": "main", "duration_seconds": 120, "input_tokens": 64, "output_tokens": 8,
                     "request_count": 5, "rate_rps": 1.0}])
    cmp = dict(_sc().comparison.model_dump())
    cmp["control_shape"] = None
    with pytest.raises(ValueError, match="control_shape"):
        _sc(comparison=cmp)
    with pytest.raises(ValueError, match="protocol_version: 4"):
        _sc(protocol_version=3, prompt_token_unit="tokenizer")


def test_fixed_count_phase_is_exact_spread_and_deterministic():
    sc = load_scenario(V4 / "r2/v4_r2f_s96.yaml")
    a1, _, _ = paired_traces(sc, 42)
    a2, _, _ = paired_traces(sc, 42)
    comp = [it.request for it in a1 if it.request.workload_class == "competitor"]
    assert len(comp) == 1250 and {(r.input_token_count, r.max_output_tokens) for r in comp} == {(64, 32)}
    t = np.array([r.arrival_time_s for r in comp])
    assert t.min() >= 0 and t.max() < 120 and t.min() < 30 and t.max() > 90
    assert trace_hash(a1) == trace_hash(a2)
    assert trace_hash(a1) != trace_hash(paired_traces(sc, 43)[0])


def test_token_matched_fixed_spreads_where_historical_control_front_loads():
    sc = load_scenario(V4 / "r1/v4_r1_prefill_vs_short_L300.yaml")
    atk, ctl, label = paired_traces(sc, 42)
    assert label == "token_matched_fixed"
    tok = lambda tr: sum(it.request.input_token_count + it.request.max_output_tokens  # noqa: E731
                         for it in tr if it.request.workload_class == "competitor")
    assert abs(tok(atk) - tok(ctl)) <= 128  # within one control request
    last = lambda tr: max(it.request.arrival_time_s for it in tr if it.request.workload_class == "competitor")  # noqa: E731
    assert last(ctl) / 120 > 0.9
    hist = load_scenario(REPO / "experiments/v3/a9_tok_prefill.yaml")
    _, hctl, hl = paired_traces(hist, 42)
    assert hl == "matched_total_short" and last(hctl) / hist.runtime_seconds < 0.6  # the audited front-loading
    vic = lambda tr: [(it.request.request_id, it.request.arrival_time_s, it.request.input_token_count)  # noqa: E731
                      for it in tr if it.request.workload_class == "victim"]
    assert vic(atk) == vic(ctl)


def test_offline_calibration_fits_and_frozen_check(tmp_path):
    sc = load_scenario(V4 / "r1/v4_r1_decode_vs_short_L200.yaml")
    w = WhitespaceTokenizer()
    atk, ctl, _ = paired_traces(sc, 42, w)
    for tr in (atk, ctl):
        assert verify_trace(tr, w, max_model_len=4096, exact=True)["ok"]
    frozen = {"scenarios": {sc.scenario_id: {"42": {"attack": {"trace_sha256": trace_hash(atk)},
                                                    "control": {"trace_sha256": trace_hash(ctl)}}}}}
    check_frozen(frozen, sc, 42, atk, ctl)
    with pytest.raises(FrozenTraceMismatch):
        check_frozen(frozen, sc, 42, ctl, atk)
    with pytest.raises(FrozenTraceMismatch, match="not in the frozen"):
        check_frozen(frozen, sc, 43, atk, ctl)


def test_v4_gates_coverage_output_and_regime():
    from quotashift.evaluation.attack_effect import RunMetrics, analyze_pair
    from quotashift.evaluation.validity import validity_gates

    def rm(arm, seed, **kw):
        b = RunMetrics(run_dir="/x", scenario="s", arm=arm, seed=seed, synthetic_backend=True, victim_completed=50,
                       victim_timed_out=0, victim_ttft_p50_ms=1, victim_ttft_p95_ms=1, victim_e2e_p50_ms=1,
                       victim_e2e_p95_ms=1, competitor_requests=20, competitor_tokens=1, victim_offered=50,
                       victim_admitted=50, competitor_offered=20, competitor_admitted=20, requests_sent=70,
                       backend_error_total=0, http_400_total=0, victim_user_ttft_p95_ms=100.0,
                       victim_censored_fraction=0.0, competitor_first_arrival_fraction=0.05,
                       competitor_last_arrival_fraction=0.97, output_mismatch_completed=0)
        return replace(b, **kw)
    ctl = [rm("control", s) for s in range(5)]
    front = [rm("attack", s, competitor_last_arrival_fraction=0.5) for s in range(5)]
    a = analyze_pair(front, ctl, metric="user_ttft_p95", threshold=1.25, direction="two_sided")
    v = validity_gates(front, ctl, a, max_model_len=4096, synthetic=True, protocol_version=4, ignore_eos=True)
    assert not v["passed"] and not [g for g in v["checks"] if g["name"] == "arrival_coverage"][0]["passed"]
    trunc = [rm("attack", s, output_mismatch_completed=3) for s in range(5)]
    v = validity_gates(trunc, ctl, a, max_model_len=4096, synthetic=True, protocol_version=4, ignore_eos=True)
    assert not [g for g in v["checks"] if g["name"] == "realized_output_equals_authorized"][0]["passed"]
    over = [rm("attack", s, competitor_requests=10, victim_censored_fraction=0.3) for s in range(5)]
    a = analyze_pair(over, ctl, metric="user_ttft_p95", threshold=1.25, direction="two_sided")
    v = validity_gates(over, ctl, a, max_model_len=4096, synthetic=True, protocol_version=4, ignore_eos=True,
                       feasibility_gates="classify")
    assert v["passed"] and v["regime"] == "overload"
    v = validity_gates(over, ctl, a, max_model_len=4096, synthetic=True, protocol_version=4, ignore_eos=True)
    assert not v["passed"] and v["regime"] is None


def _mock_experiment(src: Path, tmp: Path, *, runtime: int, path: str = "gateway", sid: str | None = None) -> Path:
    from quotashift.cli import main

    d = yaml.safe_load(src.read_text())
    n = d["phases"][0]["request_count"]
    d.update(runtime_seconds=runtime, frozen_traces=None, scenario_id=sid or d["scenario_id"])
    d["phases"][0].update(duration_seconds=runtime, request_count=max(4, round(n * runtime / 120)))
    d["comparison"]["repetitions"] = 2
    tmp.mkdir(parents=True, exist_ok=True)
    f = tmp / f"{d['scenario_id']}.yaml"
    f.write_text(yaml.safe_dump(d))
    out = tmp / "reports" / d["scenario_id"]
    rc = main(["experiment", str(f), "--reps", "2", "--mock", "--out", str(out), "--results-root", str(tmp / "results"),
               "--path", path])
    assert rc in (0, 5), rc  # 5 = gates refused (mock has no GPU energy / feasibility); report still written
    return out


@pytest.mark.parametrize("name", ["r1/v4_r1_prefill_vs_short_L200", "r2/v4_r2f_s256"])
def test_mock_end_to_end_reports_v4_fields(tmp_path, name):
    out = _mock_experiment(V4 / f"{name}.yaml", tmp_path, runtime=12)
    man = json.loads((out / "manifest.json").read_text())
    assert man["metric"] == "user_ttft_p95" and man["metric_label"] == "Victim user-facing TTFT P95"
    names = {g["name"] for g in man["validity"]["checks"]}
    assert {"arrival_coverage", "realized_output_equals_authorized"} <= names
    gate = {g["name"]: g for g in man["validity"]["checks"]}
    assert gate["arrival_coverage"]["passed"] and gate["realized_output_equals_authorized"]["passed"]
    import pandas as pd

    df = pd.read_csv(out / "summary.csv")
    for col in ("gw_saturation_fraction", "request_bound_fraction", "engine_bound_fraction", "victim_user_ttft_mean_ms",
                "competitor_first_arrival_fraction", "output_mismatch_completed"):
        assert col in df.columns
    assert (df.output_mismatch_completed == 0).all() and (df.gw_inflight_cap == 8).all()
    if "r2" in name:
        assert man["validity"]["regime"] in ("feasible", "overload")


def test_mock_analysis_select_load_r2_and_paths(tmp_path):
    va = _mod("v4_analysis")
    for sh in "PDS":
        _mock_experiment(V4 / f"calibration/v4_cal_{sh}_L200.yaml", tmp_path, runtime=12)
    sel = va.select_load(tmp_path / "reports")
    assert set(sel["probes"]) == {"v4_cal_P_L200", "v4_cal_D_L200", "v4_cal_S_L200"}
    # mock: provenance/energy unavailable is not an integrity failure here, but missing GPU energy is not gated;
    # the rule must at least evaluate every probe and return a decision string
    assert "decision" in sel and set(sel["feasible_at"]) == {200}
    r2 = tmp_path / "r2"
    r2.mkdir()
    for s in (96, 1024):
        _mock_experiment(V4 / f"r2/v4_r2f_s{s}.yaml", r2, runtime=12)
    summ = va.r2_summary(r2 / "reports")
    assert list(summ["size"]) == [96, 1024] and set(summ["limiting_resource"]) <= {
        "engine-bound", "request-bound (gateway)", "unconstrained"}
    gw = _mock_experiment(V4 / "r2/v4_r2f_s96.yaml", tmp_path / "p", runtime=12)
    di = _mock_experiment(V4 / "r3/v4_r2f_s96_direct.yaml", tmp_path / "p", runtime=12, path="direct")
    cmp = va.compare_paths(gw, di)
    dec = cmp["arms"]["attack"]["decomposition_ms"]
    assert dec["gateway_user_ttft_mean"] >= dec["gateway_backend_ttft_mean"] >= 0
    with pytest.raises(SystemExit):
        va.compare_paths(di, gw)


def test_frozen_manifest_covers_every_v4_scenario_and_seed():
    man = json.loads((V4 / "FROZEN_TRACES.json").read_text())
    assert man["tokenizer"]["kind"] == "vllm /tokenize"  # frozen on the live model tokenizer, not the stand-in
    for f in sorted(V4.rglob("*.yaml")):
        sc = load_scenario(f)
        ent = man["scenarios"][sc.scenario_id]
        for s in range(sc.seed, sc.seed + sc.comparison.repetitions):
            for arm in ("attack", "control"):
                r = ent[str(s)][arm]
                assert len(r["trace_sha256"]) == 64 and r["max_context_tokens"] <= sc.model_max_len
                cov = r["competitor_arrival_coverage"]
                assert cov is None or (cov["first"] <= 0.25 and cov["last"] >= 0.75)
            if sc.comparison.matched_token_budget:
                assert ent[str(s)]["budget"]["matched"] and ent[str(s)]["budget"]["total_tokens"] <= 0.05
