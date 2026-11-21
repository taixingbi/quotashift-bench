"""Protocol v3 (A7–A9): deterministic replay, matching contracts, cache-state separation, lifecycle bounds,
classification and cost accounting. CPU only."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from quotashift.evaluation.attack_effect import RunMetrics, _metric_value, analyze_pair, classify
from quotashift.instrumentation.engine_counters import cost_accounting
from quotashift.local import budget_view, paired_traces
from quotashift.scenario import load_scenario
from quotashift.schema import EventType
from quotashift.workload.generator import trace_hash
from quotashift.workload.lifecycle import LifecycleClient, lifecycle_plans

REPO = Path(__file__).resolve().parents[2]
V3 = sorted((REPO / "experiments" / "v3").glob("*.yaml")) + sorted((REPO / "experiments" / "v3" / "smoke").glob("*.yaml"))


def _blk(it, n=16):
    return " ".join(it.request.prompt_text.split(" ")[:n])


@pytest.mark.parametrize("path", V3, ids=lambda p: p.stem)
def test_v3_replay_deterministic_and_budget_gate(path):
    sc = load_scenario(path)
    assert sc.protocol_version == 3 and sc.comparison.preregistered_threshold == 1.25
    assert sc.comparison.threshold_justification  # documented, not inherited
    a1, c1, _ = paired_traces(sc, sc.seed)
    a2, c2, _ = paired_traces(sc, sc.seed)
    assert trace_hash(a1) == trace_hash(a2) and trace_hash(c1) == trace_hash(c2)
    assert trace_hash(paired_traces(sc, sc.seed + 1)[0]) != trace_hash(a1)
    # victim traffic identical within the pair (ids, arrivals, lengths)
    va = [(i.request.request_id, i.request.arrival_time_s, i.request.input_token_count, i.request.max_output_tokens)
          for i in a1 if i.request.workload_class == "victim"]
    vc = [(i.request.request_id, i.request.arrival_time_s, i.request.input_token_count, i.request.max_output_tokens)
          for i in c1 if i.request.workload_class == "victim"]
    assert va == vc
    if sc.lifecycle:
        assert lifecycle_plans(sc, a1, sc.seed) == lifecycle_plans(sc, a2, sc.seed)
        assert len(budget_view(sc, a1, sc.seed)) >= len(a1)


def test_a7_cache_state_separation_and_exact_matching():
    sc = load_scenario(REPO / "experiments" / "v3" / "a7_prefix_cache.yaml")
    for seed in (42, 43, 44):
        atk, ctl, label = paired_traces(sc, seed)
        assert label == "prefix_unique"
        # exact matching: same ids, arrivals, word counts, planned tokens for EVERY request
        for x, y in zip(atk, ctl, strict=True):
            assert x.request.request_id == y.request.request_id and x.request.arrival_time_s == y.request.arrival_time_s
            assert len(x.request.prompt_text.split(" ")) == len(y.request.prompt_text.split(" "))
            assert x.request.input_token_count == y.request.input_token_count
            assert x.request.max_output_tokens == y.request.max_output_tokens
        ca = [_blk(i) for i in atk if i.request.workload_class == "competitor"]
        cc = [_blk(i) for i in ctl if i.request.workload_class == "competitor"]
        assert len(set(ca)) == 1 and len(ca) > 5          # A7-A: one shared prefix within the arm
        assert len(set(cc)) == len(cc)                     # A7-C: every prefix unique
        assert not set(ca) & set(cc)                       # no cross-arm sharing
        for arm in (atk, ctl):                             # victims: one shared prefix per tenant per arm
            per = Counter((i.request.tenant_id, _blk(i, 8)) for i in arm if i.request.workload_class == "victim")
            assert len({t for t, _ in per}) == len(per)
        vb_a = {_blk(i) for i in atk if i.request.workload_class == "victim"}
        vb_c = {_blk(i) for i in ctl if i.request.workload_class == "victim"}
        assert not vb_a & vb_c                             # victim prefixes salted per arm


def test_a7v_isolation_protocol_distinct_from_a7():
    sc = load_scenario(REPO / "experiments" / "v3" / "a7v_cache_isolation_validation.yaml")
    assert sc.prefix_cache is None and sc.comparison.primary_control == "identical_workload"
    atk, ctl, _ = paired_traces(sc, sc.seed)
    ba, bc = [_blk(i) for i in atk], [_blk(i) for i in ctl]
    assert len(set(ba)) == len(ba) and len(set(bc)) == len(bc) and not set(ba) & set(bc)


def test_lifecycle_plans_fractions_and_twins():
    sc = load_scenario(REPO / "experiments" / "v3" / "a8_lifecycle_churn.yaml")
    atk, ctl, _ = paired_traces(sc, sc.seed)
    plans = lifecycle_plans(sc, atk, sc.seed)
    assert set(plans) == {i.request.request_id for i in atk if i.request.workload_class == "competitor"}
    acts = Counter(p.action for p in plans.values())
    n = sum(acts.values())
    assert abs(acts["cancel_after_chunks"] / n - 0.4) < 0.15 and abs(acts["timeout_after_s"] / n - 0.2) < 0.15
    assert all(p.retries == 0 for p in plans.values()) and len(ctl) == len(atk)
    sb = load_scenario(REPO / "experiments" / "v3" / "a8_retry_churn.yaml")
    a, c, _ = paired_traces(sb, sb.seed)
    pb = lifecycle_plans(sb, a, sb.seed)
    planned = [r for r, p in pb.items() if p.retries]
    twins = {i.request.request_id: i for i in c if i.request.request_id.endswith("-r1")}
    assert set(twins) == {f"{r}-r1" for r in planned}
    orig_c = {i.request.request_id: i for i in c}
    orig_a = {i.request.request_id: i for i in a}
    for r in planned:  # twin re-sends exactly its arm's original body, as the attack arm's retry does
        assert twins[f"{r}-r1"].request.prompt_text == orig_c[r].request.prompt_text
        assert twins[f"{r}-r1"].request.prompt_text != orig_a[r].request.prompt_text  # arms salted apart
        assert twins[f"{r}-r1"].request.arrival_time_s == pytest.approx(orig_a[r].request.arrival_time_s + 1.5)


def test_lifecycle_client_retry_bounds():
    sc = load_scenario(REPO / "experiments" / "v3" / "a8_retry_churn.yaml")
    atk, _, _ = paired_traces(sc, sc.seed)
    plans = lifecycle_plans(sc, atk, sc.seed)
    states: dict[str, EventType] = {}
    cl = LifecycleClient(atk, plans, states.get)
    rid = next(r for r, p in plans.items() if p.retries)
    states[rid] = EventType.TIMED_OUT
    first = cl.on_terminal(rid, 10.0)
    assert len(first) == 1 and first[0][0] == pytest.approx(10.5) and first[0][1].request.request_id == f"{rid}-r1"
    assert cl.on_terminal(rid, 11.0) == []                     # max_retries=1
    states[f"{rid}-r1"] = EventType.TIMED_OUT
    assert cl.on_terminal(f"{rid}-r1", 12.0) == []             # retries never retry
    done = next(r for r, p in plans.items() if p.retries and r != rid)
    states[done] = EventType.COMPLETED
    assert cl.on_terminal(done, 5.0) == [] and cl.retries_not_needed == 1
    nop = next(r for r, p in plans.items() if not p.retries)
    states[nop] = EventType.CANCELLED
    assert cl.on_terminal(nop, 5.0) == []
    assert cl.retries_fired == 1 <= sum(p.retries for p in plans.values())


@pytest.mark.parametrize("ci,thr,d,exp", [
    ((1.3, 1.6), 1.25, "increase", "supported"), ((0.9, 1.2), 1.25, "increase", "negative"),
    ((1.1, 1.4), 1.25, "increase", "inconclusive"), ((0.5, 0.7), 1.25, "two_sided", "supported"),
    ((0.85, 1.2), 1.25, "two_sided", "negative"), ((0.7, 1.1), 1.25, "two_sided", "inconclusive"),
    ((float("nan"), float("nan")), 1.25, "two_sided", "unavailable")])
def test_classification(ci, thr, d, exp):
    assert classify(ci, thr, d) == exp


def _rm(seed, arm, **kw):
    base = dict(run_dir="", scenario="s", arm=arm, seed=seed, synthetic_backend=True, victim_completed=1,
                victim_timed_out=0, victim_ttft_p50_ms=1, victim_ttft_p95_ms=1, victim_e2e_p50_ms=1,
                victim_e2e_p95_ms=1, competitor_requests=1, competitor_tokens=1)
    return RunMetrics(**(base | kw))


def test_energy_metric_unavailable_is_reported_not_substituted():
    a = [_rm(s, "attack", authorized_tokens=1000) for s in range(3)]
    c = [_rm(s, "control", authorized_tokens=1000) for s in range(3)]
    r = analyze_pair(a, c, metric="gpu_energy_per_1k_authorized_tokens", threshold=1.25, direction="two_sided")
    assert r["classification"] == "unavailable" and r["n_seeds_with_metric"] == 0
    a = [_rm(s, "attack", authorized_tokens=2000, gpu_dynamic_energy_j=400.0) for s in range(3)]
    c = [_rm(s, "control", authorized_tokens=2000, gpu_dynamic_energy_j=200.0) for s in range(3)]
    assert _metric_value(a[0], "gpu_energy_per_1k_authorized_tokens") == 200.0
    r = analyze_pair(a, c, metric="gpu_energy_per_1k_authorized_tokens", threshold=1.25, direction="two_sided")
    assert r["mean_ratio"] == pytest.approx(2.0) and r["classification"] == "insufficient_seeds"  # 3 < 5
    a = [_rm(s, "attack", authorized_tokens=2000, gpu_dynamic_energy_j=400.0) for s in range(5)]
    c = [_rm(s, "control", authorized_tokens=2000, gpu_dynamic_energy_j=200.0) for s in range(5)]
    r = analyze_pair(a, c, metric="gpu_energy_per_1k_authorized_tokens", threshold=1.25, direction="two_sided")
    assert r["classification"] == "supported"


def test_cost_accounting_energy_busy_and_unavailable():
    ts = [{"t_rel_s": t, "num_requests_running": r, "kv_cache_usage_perc": kv, "gpu_power_w": p}
          for t, r, kv, p in ((0, 0, 0.0, 100), (1, 2, 0.2, 200), (2, 1, 0.4, 200), (3, 0, 0.1, 100))]
    c = cost_accounting(ts, idle_power_w=100.0, authorized_tokens=10, competitor_authorized_tokens=5)
    assert c["engine_busy_s"] == 2.0 and c["kv_cache_usage_max"] == 0.4
    assert c["gpu_energy_j"] == pytest.approx(150 + 200 + 150) and c["gpu_dynamic_energy_j"] == pytest.approx(200)
    n = cost_accounting([{"t_rel_s": 0, "num_requests_running": 0}], idle_power_w=None, authorized_tokens=1,
                        competitor_authorized_tokens=0)
    assert n["gpu_energy_j"] is None and "unavailable" in n["gpu_energy_method"]


def test_v3_fields_rejected_outside_v3():
    d = load_scenario(REPO / "experiments" / "v3" / "a8_lifecycle_churn.yaml").model_dump()
    d["protocol_version"] = 2
    with pytest.raises(ValueError, match="requires protocol_version: 3"):
        type(load_scenario(REPO / "experiments" / "v3" / "a8_lifecycle_churn.yaml")).model_validate(d)


def test_classification_requires_preregistered_seed_count():
    from quotashift.evaluation.attack_effect import MIN_SEEDS_FOR_CLAIM

    assert MIN_SEEDS_FOR_CLAIM == 5  # design doc: >= 5 paired seeds
