"""X2 Amendment A2 (DRAFT): stratified competitor arrivals. Offline; no server, no GPU, no network."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import build_x2  # noqa: E402
import build_x2_a2 as b2  # noqa: E402
import freeze_v4  # noqa: E402
import freeze_v5  # noqa: E402
import freeze_x2_a2_traces as fa  # noqa: E402
import freeze_x2_traces as fx  # noqa: E402
import pin_x2_a2  # noqa: E402
import x2_a2_stage  # noqa: E402
import x2_runner_entry as ent  # noqa: E402

from quotashift.local import paired_traces  # noqa: E402
from quotashift.scenario import ScenarioConfig, load_scenario  # noqa: E402
from quotashift.workload.tokenize import WhitespaceTokenizer  # noqa: E402
from quotashift.x2 import arrivals_a2 as a2  # noqa: E402

PLAT = "g1m0"
TOK = WhitespaceTokenizer()
ORIG = REPO / "experiments" / "x2" / PLAT / "main"
A2M = REPO / "experiments" / "x2_a2" / PLAT / "main"


def _comp(tr):
    return sorted((it.request for it in tr if it.request.workload_class == "competitor"), key=lambda r: r.arrival_time_s)


def _victims(tr):
    return sorted((r.request_id, r.arrival_time_s, r.prompt_text, r.input_token_count, r.max_output_tokens)
                  for r in (it.request for it in tr) if r.workload_class != "competitor")


# ------------------------------------------------------------------------------------------------ the law
@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 10, 37])
def test_one_arrival_per_stratum_sorted_and_deterministic(n):
    t = a2.stratified_times(n, 120.0, a2.stratum_rng(23000, "comp", "main"))
    assert list(t) == sorted(t) and len(t) == n
    assert [int(x // (120.0 / n)) for x in t] == list(range(n))
    assert np.array_equal(t, a2.stratified_times(n, 120.0, a2.stratum_rng(23000, "comp", "main")))
    assert not np.array_equal(t, a2.stratified_times(n, 120.0, a2.stratum_rng(23001, "comp", "main")))


def test_stream_is_new_and_labels_are_independent():
    assert a2.STREAM_TAG not in (101, 102)
    x = a2.stratified_times(8, 120.0, a2.stratum_rng(23000, "comp", "main"))
    y = a2.stratified_times(8, 120.0, a2.stratum_rng(23000, "comp", "main~ind"))
    z = a2.stratified_times(8, 120.0, a2.stratum_rng(23000, "comp", "ctl_tmf"))
    assert not np.array_equal(x, y) and not np.array_equal(x, z)


@pytest.mark.parametrize("n", [4, 5, 9, 10, 40])
def test_n_at_least_4_always_passes_the_frozen_coverage_thresholds(n):
    for s in range(200):
        t = a2.stratified_times(n, 120.0, a2.stratum_rng(s, "comp", "main")) / 120.0
        assert t[0] <= 0.25 and t[-1] >= 0.75


# ------------------------------------------------------------------------------------------------ loader / frozen paths
@pytest.mark.parametrize("f", sorted(ORIG.rglob("*.yaml")) + sorted((REPO / "experiments" / "x2" / PLAT / "calA").glob("*.yaml"))[:2])
def test_non_a2_files_load_through_the_frozen_loader_with_identical_traces(f):
    x, y = a2.load_scenario_any(f), load_scenario(f)
    assert type(x) is ScenarioConfig and x == y
    s = x.seed
    assert [freeze_v5.schedule_sha(t) for t in paired_traces(x, s, TOK)[:2]] == \
           [freeze_v5.schedule_sha(t) for t in paired_traces(y, s, TOK)[:2]]


@pytest.mark.parametrize("f", sorted((REPO / "experiments" / "v3_1").rglob("*.yaml")), ids=lambda p: p.stem)
def test_other_amendment_labels_still_use_the_frozen_loader(f):
    """The frozen schema's free-text `protocol_amendment` (v3.1: "3.1") must never select A2."""
    x = a2.load_scenario_any(f)
    assert type(x) is ScenarioConfig and x == load_scenario(f)


def test_a2_loader_is_scoped_and_restored():
    import quotashift.scenario as qs
    frozen = qs.load_scenario
    with a2.a2_loader():
        assert qs.load_scenario is a2.load_scenario_any
    assert qs.load_scenario is frozen
    fa.freeze(PLAT, TOK, TOK.identity)
    assert qs.load_scenario is frozen


def test_a2_needs_both_keys_and_x2_scope(tmp_path):
    d = yaml.safe_load((A2M / "x2_g1m0_X2a_decode_vs_short_low_C8.yaml").read_text())
    for bad in ({"competitor_arrival_law": None}, {"protocol_amendment": "X2-A3"}, {"protocol_version": 4},
                {"competitor_arrival_law": "iid"}):
        e = {**d, **bad}
        e = {k: v for k, v in e.items() if v is not None}
        f = tmp_path / "x.yaml"
        f.write_text(yaml.safe_dump(e))
        with pytest.raises((ValidationError, ValueError)):
            a2.load_scenario_any(f)


@pytest.mark.parametrize("f", sorted(A2M.rglob("*.yaml")), ids=lambda p: p.stem)
def test_a2_changes_only_competitor_arrival_times(f):
    o, a = load_scenario(ORIG / f.relative_to(A2M)), a2.load_scenario_any(f)
    assert isinstance(a, a2.ScenarioConfigA2)
    for s in range(a.seed, a.seed + a.comparison.repetitions):
        ao, co, _ = paired_traces(o, s, TOK)
        aa, ca, _ = paired_traces(a, s, TOK)
        for x, y in ((ao, aa), (co, ca)):
            assert _victims(x) == _victims(y)
            rx, ry = _comp(x), _comp(y)
            key = [(r.request_id, r.prompt_text, r.input_token_count, r.max_output_tokens) for r in rx]
            assert sorted(key) == sorted((r.request_id, r.prompt_text, r.input_token_count, r.max_output_tokens) for r in ry)
            cov = freeze_v4._coverage(y, a.runtime_seconds)
            assert cov["first"] <= 0.25 and cov["last"] >= 0.75
        if a.comparison.primary_control == "independent_replicate":
            assert freeze_v5.schedule_sha(aa, competitor_arrivals_only=True) != \
                   freeze_v5.schedule_sha(ca, competitor_arrivals_only=True)


def test_original_main_files_fail_the_gate_on_the_documented_seeds():
    sc = load_scenario(ORIG / "x2_g1m0_X2a_decode_vs_short_low_C8.yaml")
    fails = [s for s in range(23000, 23024)
             if (lambda c: c["first"] > 0.25 or c["last"] < 0.75)(freeze_v4._coverage(paired_traces(sc, s, TOK)[0], 120))]
    assert len(fails) == 12 and fails[0] == 23000


# ------------------------------------------------------------------------------------------------ generator
def test_generator_matches_committed_files_and_adds_only_the_keys():
    assert b2.check(PLAT) == []
    gen = b2.build_main_a2(PLAT, b2.rates_of(PLAT))
    orig = build_x2.with_reruns(build_x2.build_main(PLAT, b2.rates_of(PLAT)))
    assert set(gen) == set(orig) and len(gen) == 8
    for rel in gen:
        added = set(gen[rel].splitlines()) - set(orig[rel].splitlines())
        assert added == {b2.HEADER.strip(), "protocol_amendment: X2-A2", "competitor_arrival_law: stratified_v1"}
        assert set(orig[rel].splitlines()) <= set(gen[rel].splitlines())
    for name in b2.COPIED:
        assert (b2.A2 / PLAT / name).read_bytes() == (b2.X2 / PLAT / name).read_bytes()


def test_generator_refuses_an_unexpected_frozen_file():
    with pytest.raises(ValueError):
        b2.amend("schema_version: 1\n")


# ------------------------------------------------------------------------------------------------ freeze / pins
@pytest.fixture
def cal_done(tmp_path):
    rep = tmp_path / "rep"
    (rep / PLAT / "calA").mkdir(parents=True)
    (rep / PLAT / "calA" / "STAGE_LOG.json").write_text(json.dumps({"status": "completed"}))
    return rep


def test_a2_ordering_passes_and_frozen_ordering_would_refuse(cal_done, tmp_path):
    assert fa.ordering_problems(PLAT, reports_root=cal_done, results_root=tmp_path / "res") == []
    frozen = fx.ordering_problems(PLAT, "main", root=b2.A2, reports_root=cal_done, results_root=tmp_path / "res")
    assert frozen and all(x.startswith("main files do not match the generator") for x in frozen)


def test_a2_ordering_refuses_after_a_main_log(cal_done, tmp_path):
    (cal_done / PLAT / "main").mkdir()
    (cal_done / PLAT / "main" / "STAGE_LOG.json").write_text("{}")
    assert fa.ordering_problems(PLAT, reports_root=cal_done, results_root=tmp_path / "res")


def test_offline_freeze_passes_every_frozen_gate_and_carries_provenance():
    sched, traces = fa.freeze(PLAT, TOK, TOK.identity)
    assert len(traces["scenarios"]) == 8 and traces["amendment"]["protocol"] == "X2-A2"
    assert sched["amendment"] == traces["amendment"]
    assert traces["amendment"]["law_module_sha256"] == pin_x2_a2.pin_x2.sha("src/quotashift/x2/arrivals_a2.py")
    for ent_ in traces["scenarios"].values():
        for s in ent_["seeds"]:
            for arm in ("attack", "control"):
                cov = ent_[str(s)][arm]["competitor_arrival_coverage"]
                assert cov["first"] <= 0.25 and cov["last"] >= 0.75


def test_original_files_still_refused_by_the_frozen_freeze():
    with pytest.raises(SystemExit, match="arrival coverage gate would fail"):
        fx.freeze(PLAT, "main", TOK, TOK.identity)


def test_a2_freeze_not_made_and_pins_refuse_without_tokens(monkeypatch):
    assert not pin_x2_a2.MANIFEST.exists()
    assert any("A2 freeze has not been made" in x for x in pin_x2_a2.check())
    monkeypatch.setattr(sys, "argv", ["pin_x2_a2.py", "--write"])
    monkeypatch.delenv("QUOTASHIFT_APPROVED", raising=False)
    assert pin_x2_a2.main() == 3
    monkeypatch.setattr(sys, "argv", ["pin_x2_a2.py", "--pin-phase", PLAT, "main"])
    monkeypatch.setenv("QUOTASHIFT_APPROVED", "x2_freeze_main_g1m0")      # the X2 token is not the A2 token
    assert pin_x2_a2.main() == 3
    assert not (b2.A2 / PLAT / "PHASE_PINS.json").exists()


def test_a2_live_stage_refuses_wrong_token_and_unfrozen_amendment(monkeypatch, tmp_path):
    monkeypatch.setenv("QUOTASHIFT_APPROVED", "x2_main_g1m0")
    assert x2_a2_stage.live_problems(PLAT, interactive_ok=True, reports_root=tmp_path) == [
        "QUOTASHIFT_APPROVED must be x2a2_main_g1m0 (owner approval for the A2 main stage)"]
    monkeypatch.setenv("QUOTASHIFT_APPROVED", "x2a2_main_g1m0")
    p = x2_a2_stage.live_problems(PLAT, interactive_ok=True, reports_root=tmp_path)
    assert any("A2 freeze has not been made" in x for x in p) and any("not pinned" in x for x in p)
    assert __import__("os").environ["QUOTASHIFT_APPROVED"] == "x2a2_main_g1m0"


# ------------------------------------------------------------------------------------------------ in-VPC routing
SHA = "a" * 64


def test_overrides_route_a2_kinds_to_a2_drivers_only():
    o = ent.overrides("a2_main", PLAT, "b", [], {"QUOTASHIFT_X2_INPUTS_SHA256": SHA, "QUOTASHIFT_STAGE_APPROVAL": "x2a2_main_g1m0"})
    cmd = o["containerOverrides"][0]["command"]
    assert "scripts/x2_a2_stage.py" in cmd and "--live" in cmd and "scripts/x2_stage.py" not in cmd
    o = ent.overrides("a2_freeze_main", PLAT, "b", [], {"QUOTASHIFT_X2_INPUTS_SHA256": SHA,
                                                         "QUOTASHIFT_STAGE_APPROVAL": "x2a2_freeze_main_g1m0"})
    assert "scripts/freeze_x2_a2_traces.py" in o["containerOverrides"][0]["command"]
    for kind, tok in (("a2_main", "x2_main_g1m0"), ("main", "x2a2_main_g1m0"), ("a2_main", "x2a2_main_g1m1")):
        with pytest.raises(SystemExit):
            ent.overrides(kind, PLAT, "b", [], {"QUOTASHIFT_X2_INPUTS_SHA256": SHA, "QUOTASHIFT_STAGE_APPROVAL": tok})


def test_inputs_include_a2_files_and_extract_allows_them(tmp_path):
    assert ent.allowed("experiments/x2_a2/g1m0/main/x.yaml", PLAT)
    assert not ent.allowed("experiments/x2_a2/g1m1/main/x.yaml", PLAT)
    assert not ent.allowed("experiments/x2_a2/AMENDMENT_A2_SHA256.json", PLAT)
    import tarfile
    sha = ent.pack(PLAT, tmp_path / "i.tgz", REPO)
    names = tarfile.open(tmp_path / "i.tgz").getnames()
    assert any(n.startswith("experiments/x2_a2/g1m0/main/") for n in names)
    assert any(n.startswith("experiments/x2/g1m0/") for n in names) and len(sha) == 64
