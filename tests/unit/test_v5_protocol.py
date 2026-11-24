"""Protocol v5 (docs/PROTOCOL_V5_DRAFT.md), offline only: spec-generated YAMLs, seed-shared schedules across caps,
the independent A/A control, the frozen schedule and FCFS predictions (incl. the leakage guard), engine-histogram
bucket deltas, and the pre-registered decision rules on synthetic inputs. No GPU evidence anywhere."""

from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

from quotashift.instrumentation.engine_counters import counter_deltas
from quotashift.instrumentation.prom import parse_prometheus_text, resolve
from quotashift.local import _paired_traces_raw
from quotashift.scenario import ScenarioConfig, load_scenario

REPO = Path(__file__).resolve().parents[2]
V5 = REPO / "experiments" / "v5"


def _mod(name: str):
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    assert spec.loader is not None
    spec.loader.exec_module(m)
    return m


A = _mod("v5_analysis")


# ---------------------------------------------------------------- spec / YAMLs
def test_v5_files_are_exactly_the_generated_spec():
    r = subprocess.run([sys.executable, str(REPO / "scripts/build_v5.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_v5_scenario_validates_and_only_the_cap_varies():
    files = sorted(f for f in V5.rglob("*.yaml") if "reruns" not in f.parts)
    assert len(files) == 23  # 4 smoke + 12 stage A + 7 stage B
    for f in files:
        sc = load_scenario(f)
        assert sc.protocol_version == 5 and sc.prompt_token_unit == "tokenizer" and sc.ignore_eos
        assert sc.comparison.degradation_metric == "user_ttft_mean" and sc.comparison.preregistered_threshold == 1.25
        assert sc.frozen_traces == "../FROZEN_TRACES.json" and sc.gateway is None
        cap = f.stem.rsplit("_", 1)[-1]
        assert sc.safety.max_global_inflight == (8 if cap == "direct" else int(cap.removeprefix("C")))
    # files of one (comparison, L) differ only in id/salt/header/cap
    def strip(p: Path) -> list[str]:
        return [ln for ln in p.read_text().splitlines() if not ln.startswith(("#", "scenario_id:", "isolation_salt:",
                                                                               "  max_global_inflight:"))]
    for stage in ("stage_a", "stage_b"):
        groups: dict[str, list[Path]] = {}
        for f in (V5 / stage).glob("*.yaml"):
            groups.setdefault(f.stem.rsplit("_", 1)[0], []).append(f)
        for fs in groups.values():
            assert len({tuple(strip(f)) for f in fs}) == 1, fs


def test_same_seed_same_schedule_across_caps_and_direct():
    sched = json.loads((V5 / "FROZEN_SCHEDULE.json").read_text())["scenarios"]
    by_cell: dict[str, set] = {}
    for sid, ent in sched.items():
        if "smoke" in sid:
            continue
        key = sid.rsplit("_", 1)[0]
        by_cell.setdefault(key, set()).add(json.dumps({s: {a: v[a]["schedule_sha256"] for a in v}
                                                       for s, v in ent["seeds"].items()}, sort_keys=True))
    assert by_cell and all(len(v) == 1 for v in by_cell.values())


def test_frozen_schedule_reproduces():
    r = subprocess.run([sys.executable, str(REPO / "scripts/freeze_v5.py"), "--schedule", "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_independent_replicate_control():
    sc = load_scenario(V5 / "stage_a" / "v5_aa_ind_L200_C8.yaml")
    atk, ctl, label = _paired_traces_raw(sc, 5000)
    assert label == "independent_replicate"
    vic = lambda tr: [(r.request.request_id, r.request.arrival_time_s) for r in tr if r.request.workload_class == "victim"]  # noqa: E731
    comp = lambda tr: [r.request for r in tr if r.request.workload_class == "competitor"]  # noqa: E731
    assert vic(atk) == vic(ctl)
    ca, cc = comp(atk), comp(ctl)
    assert len(ca) == len(cc) and {(r.input_token_count, r.max_output_tokens) for r in ca + cc} == {(64, 64)}
    assert sorted(r.arrival_time_s for r in ca) != sorted(r.arrival_time_s for r in cc)
    assert max(r.arrival_time_s for r in cc) <= sc.runtime_seconds


def test_independent_replicate_requires_v5():
    base = yaml.safe_load((V5 / "stage_a" / "v5_aa_ind_L200_C8.yaml").read_text())
    base["protocol_version"] = 4
    with pytest.raises(ValueError, match="protocol_version: 5"):
        ScenarioConfig.model_validate(base)


# ---------------------------------------------------------------- FCFS predictions + leakage guard
P = _mod("v5_fcfs_predictions")


def test_fcfs_replay_toy():
    q, st = P.fcfs(np.array([0.0, 0.0, 0.0]), np.array([1.0, 1.0, 1.0]), 2)
    assert list(q) == [0.0, 0.0, 1.0] and list(st) == [0.0, 0.0, 1.0]


def test_leakage_guard_rejects_direct_runs():
    direct = sorted((REPO / "results" / "v4_r1_decode_vs_short_L200_direct__attack").iterdir())[0]
    with pytest.raises(SystemExit, match="leakage guard"):
        P.assert_c8_gateway(direct)


def test_frozen_predictions_use_only_c8_gateway_inputs():
    pred = json.loads((V5 / "FCFS_PREDICTIONS.json").read_text())
    ins = pred["leakage_guard"]["input_sha256"]
    assert ins and not any("direct" in k or "v5_" in k for k in ins)
    for k in ins:
        if k.endswith("config.resolved.yaml"):
            cfg = yaml.safe_load((REPO / k).read_text())
            assert cfg["path"] == "gateway" and cfg["run"]["max_concurrency_cap"] == 8
    assert {c["C"] for c in pred["cells"].values()} == {8, 16, 32}
    assert all(not k.endswith("_direct") for k in pred["cells"])
    t = pred["tolerances"]
    assert t["tau_abs_ms"] >= 5.0 and 0 < t["rho_rel"] < 1


def test_frozen_predictions_pin_inputs_by_hash():
    pred = json.loads((V5 / "FCFS_PREDICTIONS.json").read_text())
    for rel, sha in list(pred["leakage_guard"]["input_sha256"].items())[:6]:
        assert P._sha(REPO / rel) == sha


# ---------------------------------------------------------------- engine histogram buckets
def _snap(cnt: float, s: float, b03: float) -> object:
    t = (f'vllm:request_queue_time_seconds_sum{{engine="0"}} {s}\n'
         f'vllm:request_queue_time_seconds_count{{engine="0"}} {cnt}\n'
         f'vllm:request_queue_time_seconds_bucket{{engine="0",le="0.3"}} {b03}\n'
         f'vllm:request_queue_time_seconds_bucket{{engine="0",le="+Inf"}} {cnt}\n')
    return resolve(parse_prometheus_text(t))


def test_queue_histogram_bucket_deltas_and_h4_rule():
    d = counter_deltas(_snap(10, 0.001, 10), _snap(110, 0.002, 110))
    assert d["queue_time_seconds_count"] == 100 and d["queue_time_seconds_buckets"] == [(0.3, 100.0), ("+Inf", 100.0)]
    ok = A.engine_queue_negligible(d["queue_time_seconds_sum"], 100, d["queue_time_seconds_buckets"])
    assert ok["negligible"] and ok["frac_le_0p3s"] == 1.0
    d2 = counter_deltas(_snap(10, 0.001, 10), _snap(110, 5.0, 105))
    assert not A.engine_queue_negligible(d2["queue_time_seconds_sum"], 100, d2["queue_time_seconds_buckets"])["negligible"]


# ---------------------------------------------------------------- decision rules
def test_t_quantiles():
    assert A.t_ppf(0.975, 9) == pytest.approx(2.262157, abs=1e-5)
    assert A.t_ppf(0.95, 9) == pytest.approx(1.833113, abs=1e-5)


def test_feasibility_is_two_criteria_and_baseline_uses_control_only():
    assert A.execution_feasible(integrity_ok=True, completion=(0.99, 0.97), censoring=(0.0, 0.01))
    assert not A.execution_feasible(integrity_ok=True, completion=(0.99, 0.90), censoring=(0.0, 0.0))
    assert A.baseline_victim_slo_feasible(0.96) and not A.baseline_victim_slo_feasible(0.94)
    assert A.stratum([True] * 10, [True] * 10) == "E&Vb"
    assert A.stratum([True] * 10, [True] * 9 + [False]) == "E&notVb"
    assert A.stratum([True] * 9 + [False], [True] * 10) == "notE"
    out = A.attack_slo_degradation([0.5] * 5 + [0.6] * 5, [0.99] * 10)  # attack-arm SLO collapse is an OUTCOME
    assert out["mean_diff"] == pytest.approx(-0.44)


def test_classify_cell():
    rng = np.random.default_rng(0)
    assert A.classify_cell(list(math.log(2.0) + rng.normal(0, 0.05, 10)))["classification"] == "supported_increase"
    assert A.classify_cell(list(rng.normal(0, 0.03, 10)))["classification"] == "equivalent"
    assert A.classify_cell(list(rng.normal(0.2, 0.4, 10)))["classification"] == "inconclusive"


def test_h2a_and_h2b_are_separate_decisions():
    rng = np.random.default_rng(1)
    dec = {8: list(0.6 + rng.normal(0, 0.1, 10)), 16: list(0.3 + rng.normal(0, 0.1, 10)), 32: list(rng.normal(0, 0.05, 10))}
    aa = list(rng.normal(0, 0.03, 10))
    assert A.h2a_dose_response(dec)["supported"]
    assert A.h2b_equivalence_c32(dec[32], aa)["verdict"] == "equivalent"
    # a clear dose-response that still ends ABOVE the band at C=32: H2a supported, H2b not equivalent
    dec2 = {8: list(1.2 + rng.normal(0, 0.05, 10)), 16: list(0.9 + rng.normal(0, 0.05, 10)),
            32: list(0.6 + rng.normal(0, 0.05, 10))}
    assert A.h2a_dose_response(dec2)["supported"] and A.h2b_equivalence_c32(dec2[32], aa)["verdict"] == "not_equivalent"
    # flat: no dose-response, yet equivalent at 32
    flat = {c: list(rng.normal(0, 0.04, 10)) for c in (8, 16, 32)}
    assert not A.h2a_dose_response(flat)["supported"]
    assert A.h2b_equivalence_c32(flat[32], aa)["verdict"] == "equivalent"
    # noisy A/A: equivalence cannot be claimed
    noisy = list(rng.normal(0, 0.4, 10))
    assert A.h2b_equivalence_c32(flat[32], noisy)["verdict"] != "equivalent"


def test_sign_flip_exact():
    assert A.sign_flip_p([-1.0] * 10) == pytest.approx(1 / 1024)
    assert A.sign_flip_p([1.0] * 10) == 1.0


def test_holm():
    assert A.holm({"a": 0.01, "b": 0.02, "c": 0.04}) == {"a": True, "b": True, "c": True}
    assert A.holm({"a": 0.01, "b": 0.04, "c": 0.03}) == {"a": True, "b": False, "c": False}


def test_score_fcfs():
    ok = A.score_fcfs([0.0] * 10, [1.0] * 9 + [30.0], [7.0] * 10, 0.0, 5.0)
    assert ok["seeds_within"] == 9 and ok["cell_error_ms"] == pytest.approx(3.9) and ok["pass"]
    bad = A.score_fcfs([0.0] * 10, [10.0] * 10, [7.0] * 10, 0.0, 5.0)
    assert not bad["pass"]


# ---------------------------------------------------------------- §9 item 9: v5 gates
def _v5_rm(arm, seed, **kw):
    from dataclasses import replace

    from quotashift.evaluation.attack_effect import RunMetrics
    b = RunMetrics(run_dir="/x", scenario="s", arm=arm, seed=seed, synthetic_backend=True, victim_completed=50,
                   victim_timed_out=0, victim_ttft_p50_ms=1, victim_ttft_p95_ms=1, victim_e2e_p50_ms=1,
                   victim_e2e_p95_ms=1, competitor_requests=20, competitor_tokens=1, victim_offered=50,
                   victim_admitted=50, competitor_offered=20, competitor_admitted=20, requests_sent=70,
                   backend_error_total=0, http_400_total=0, victim_user_ttft_mean_ms=100.0, victim_user_ttft_p95_ms=100.0,
                   victim_censored_fraction=0.0, competitor_first_arrival_fraction=0.05,
                   competitor_last_arrival_fraction=0.97, output_mismatch_completed=0, gw_inflight_cap=16,
                   gw_inflight_max=16, occ_recon_max=16, occ_recon_exact_frac=0.97, occ_recon_time_basis="t_gw_rel_s")
    return replace(b, **kw)


def _gates(attack, control, **kw):
    from quotashift.evaluation.attack_effect import analyze_pair
    from quotashift.evaluation.validity import validity_gates
    a = analyze_pair(attack, control, metric="user_ttft_mean", threshold=1.25, direction="two_sided")
    v = validity_gates(attack, control, a, max_model_len=4096, synthetic=True, protocol_version=5, ignore_eos=True, **kw)
    return v, {g["name"]: g for g in v["checks"]}


def test_cap_configured_gate():
    ctl = [_v5_rm("control", s) for s in range(3)]
    v, g = _gates([_v5_rm("attack", s) for s in range(3)], ctl, expected_cap=16)
    assert v["passed"] and g["cap_configured"]["passed"] and g["cap_configured"]["severity"] == "fail"
    _, g = _gates([_v5_rm("attack", s) for s in range(3)], ctl, expected_cap=32)      # wrong cell cap resolved
    assert not g["cap_configured"]["passed"]
    v, g = _gates([_v5_rm("attack", 0, occ_recon_max=17), *[_v5_rm("attack", s) for s in (1, 2)]], ctl, expected_cap=16)
    assert not v["passed"] and not g["cap_configured"]["passed"]                       # cap exceeded (rebuilt)
    _, g = _gates([_v5_rm("attack", 0, gw_inflight_max=17), *[_v5_rm("attack", s) for s in (1, 2)]], ctl, expected_cap=16)
    assert not g["cap_configured"]["passed"]                                           # cap exceeded (sampled)
    _, g = _gates([_v5_rm("attack", s) for s in range(3)], ctl, expected_cap=None)
    assert not g["cap_configured"]["passed"] and not g["cap_configured"]["available"]  # fail-closed
    direct = [_v5_rm(a, s, gw_inflight_cap=512, gw_inflight_max=25, occ_recon_max=25) for a in ("attack",) for s in range(3)]
    _, g = _gates(direct, [_v5_rm("control", s, gw_inflight_cap=512) for s in range(3)], expected_cap=8, path="direct")
    assert g["cap_configured"]["passed"] and "direct path" in g["cap_configured"]["detail"]


def test_occupancy_reconstruction_gate_is_a_flag():
    ctl = [_v5_rm("control", s) for s in range(3)]
    v, g = _gates([_v5_rm("attack", 0, occ_recon_exact_frac=0.85), _v5_rm("attack", 1), _v5_rm("attack", 2)], ctl,
                  expected_cap=16)
    assert v["passed"] and not g["occupancy_reconstruction"]["passed"] and "occupancy_reconstruction" in v["flags"]


def test_v4_gate_set_unchanged_below_protocol_5():
    from quotashift.evaluation.attack_effect import analyze_pair
    from quotashift.evaluation.validity import validity_gates
    arms = [_v5_rm("attack", s) for s in range(3)], [_v5_rm("control", s) for s in range(3)]
    a = analyze_pair(*arms, metric="user_ttft_mean", threshold=1.25, direction="two_sided")
    names = {g["name"] for g in validity_gates(*arms, a, max_model_len=4096, synthetic=True, protocol_version=4)["checks"]}
    assert not names & {"cap_configured", "occupancy_reconstruction"}


def test_occupancy_reconstruction_and_time_basis():
    import pandas as pd

    from quotashift.evaluation.occupancy import reconstruction
    req = pd.DataFrame({"t_sent": [0.0, 0.5, 1.0, None], "t_terminal": [2.0, 1.0, 3.0, None]})
    # k(t): [0,0.5)=1, [0.5,1)=2, [1,2)=2 (release before admission at 1.0), [2,3)=1
    ts = pd.DataFrame({"t_rel_s": [0.1, 0.6, 1.5, 2.5], "t_gw_rel_s": [0.2, 0.7, 1.6, 2.6], "gw_inflight": [1, 2, 2, 1]})
    r = reconstruction(req, ts)
    assert r["occ_recon_max"] == 2 and r["gw_inflight_max"] == 2
    assert r["occ_recon_exact_frac"] == 1.0 and r["occ_recon_time_basis"] == "t_gw_rel_s"
    # no t_gw_rel_s (v4 runs): samples stamped 0.15 s early agree only after the frozen +0.15 s shift
    r = reconstruction(req, ts.drop(columns="t_gw_rel_s").assign(t_rel_s=[0.05, 0.45, 1.35, 2.35]))
    assert r["occ_recon_time_basis"] == "t_rel_s+0.15" and r["occ_recon_exact_frac"] == 1.0


def test_rerun_variants_differ_only_in_id_salt_header_and_keep_the_schedule():
    """§8 rule 2: one pre-generated rerun per block; new salt, same frozen schedule (keyed by the base id)."""
    build_v5 = _mod("build_v5")
    schedule_sha = _mod("freeze_v5").schedule_sha
    sched = json.loads((V5 / "FROZEN_SCHEDULE.json").read_text())["scenarios"]
    reruns = sorted((V5 / "reruns").glob("*.yaml"))
    assert len(reruns) == 23
    for r in reruns:
        base = next(f for f in V5.rglob(r.name.replace(build_v5.RERUN, "")) if "reruns" not in f.parts)
        body = lambda p: [ln for ln in p.read_text().splitlines()  # noqa: E731
                          if not ln.startswith(("#", "scenario_id:", "isolation_salt:"))]
        assert body(r) == body(base)
        a, b = load_scenario(r), load_scenario(base)
        assert a.scenario_id == b.scenario_id + "__r2" and a.isolation_salt != b.isolation_salt
        assert a.frozen_traces == b.frozen_traces and build_v5.path_of(r) == build_v5.path_of(base)
        if "smoke" in b.scenario_id:
            continue
        atk, ctl, _ = _paired_traces_raw(a, a.seed)
        ent = sched[b.scenario_id]["seeds"][str(a.seed)]
        assert schedule_sha(atk) == ent["attack"]["schedule_sha256"] and schedule_sha(ctl) == ent["control"]["schedule_sha256"]


# ---------------------------------------------------------------- rev 3
def test_h4b_is_a_paired_queue_reduction_test_independent_of_h3():
    q8 = [60.0, 55.0, 70.0, 40.0, 80.0, 52.0, 65.0, 58.0, 49.0, 75.0]
    r = A.h4b_queue_reduction(q8, [0.0] * 10)
    assert r["supported"] and r["p_perm"] == 1 / 1024 and r["mean_reduction_ms"] == pytest.approx(60.4)
    assert r["ci95_ms"][0] > 0 and len(r["per_seed_reduction_ms"]) == 10
    mixed = A.h4b_queue_reduction(q8, [q + (5 if i % 2 else -5) for i, q in enumerate(q8)])  # no net reduction
    assert not mixed["supported"]
    one = A.h4b_queue_reduction([500.0] + [1.0] * 9, [0.0] * 10)   # one huge seed, 9 tiny: the sign-flip still holds
    assert one["p"] == max(one["p_t"], one["p_perm"])
    import inspect
    assert "score_fcfs" not in inspect.getsource(A.h4b_queue_reduction)


def test_primary_ratio_is_the_geometric_mean_of_per_seed_ratios():
    ratios = [2.0, 0.5, 4.0, 1.0]
    c = A.classify_cell([math.log(r) for r in ratios])
    assert c["ratio"] == pytest.approx(math.prod(ratios) ** (1 / 4))   # geometric, not arithmetic (1.875)


def test_gateway_timestamp_alignment_scan():
    import pandas as pd

    from quotashift.evaluation.occupancy import reconstruction
    req = pd.DataFrame({"t_sent": [0.0, 1.0, 2.0, 3.0], "t_terminal": [0.6, 1.6, 2.6, 3.6]})
    grid = [0.1 + 0.1 * i for i in range(38)]
    from quotashift.evaluation.occupancy import k_at, occupancy_steps
    t, k = occupancy_steps(req)
    truth = k_at(t, k, pd.Series(grid).to_numpy())
    ok = pd.DataFrame({"t_rel_s": grid, "t_gw_rel_s": grid, "gw_inflight": truth})
    r = reconstruction(req, ok)
    assert r["occ_recon_best_lag_s"] == 0.0 and r["scrape_gw_offset_median_s"] == 0.0
    late = ok.assign(t_gw_rel_s=[x - 0.2 for x in grid])   # the recorded read time is 0.2 s early
    r = reconstruction(req, late)
    assert abs(r["occ_recon_best_lag_s"] - 0.2) <= 0.05 and r["occ_recon_exact_frac"] < 1.0
