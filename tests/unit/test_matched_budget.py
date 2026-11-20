"""Matched-budget accounting and fail-closed verification for attack/control pairs."""

from __future__ import annotations

import pydantic
import pytest

from quotashift.budget import (
    BudgetMismatch,
    TraceBudget,
    budget_report,
    summarize_trace,
    verify_matched_budget,
)
from quotashift.scenario import Comparison, ScenarioConfig, load_scenario


def _cmp(**over) -> Comparison:
    d = dict(primary_control="uniform_arrivals", matched_request_budget=True,
             matched_token_budget=True, budget_tolerance=0.05)
    d.update(over)
    return Comparison.model_validate(d)


def test_summarize_counts_requested_and_realized(repo):
    sc = load_scenario(repo / "experiments" / "a1_burst_arrivals.yaml")
    trace = sc.build_trace()
    b = summarize_trace(trace)
    assert b.requests == len(trace)
    assert b.input_tokens == sum(it.request.input_token_count for it in trace)
    assert b.requested_output_tokens == sum(it.request.max_output_tokens for it in trace)
    assert b.realized_output_tokens <= b.requested_output_tokens  # realized never exceeds requested


def test_identical_budgets_match():
    b = TraceBudget(100, 5000, 2000, 1500)
    rep = budget_report(b, b, _cmp())
    assert rep["matched"] and rep["violations"] == []


def test_token_mismatch_beyond_tolerance_flagged():
    a = TraceBudget(100, 5000, 2000, 1500)  # total 7000
    c = TraceBudget(100, 4000, 2000, 1400)  # total 6000, ~14% low
    rep = budget_report(a, c, _cmp())
    assert "total_tokens" in rep["violations"] and not rep["matched"]


def test_matched_total_tolerates_input_output_resplit():
    # Same total tokens, redistributed input<->output: matched (A2/A3 design).
    a = TraceBudget(50, 6000, 1000, 800)   # total 7000
    c = TraceBudget(200, 1000, 6000, 5000)  # total 7000, request count free
    rep = budget_report(a, c, _cmp(matched_request_budget=False))
    assert rep["matched"]
    assert rep["dimensions"]["total_tokens"]["rel_delta"] == 0.0


def test_unmatched_dim_not_required_when_flag_off():
    a = TraceBudget(100, 5000, 2000, 1500)
    c = TraceBudget(50, 5000, 2000, 1500)  # half the requests
    rep = budget_report(a, c, _cmp(matched_request_budget=False))
    assert rep["matched"]  # request count not required
    assert rep["dimensions"]["requests"]["rel_delta"] == pytest.approx(0.5)


def test_within_tolerance_passes():
    a = TraceBudget(100, 5000, 2000, 1500)
    c = TraceBudget(100, 4800, 2000, 1500)  # 4% low, under 5%
    assert budget_report(a, c, _cmp())["matched"]


def test_verify_raises_on_violation():
    a = TraceBudget(100, 5000, 2000, 1500)
    c = TraceBudget(70, 5000, 2000, 1500)
    with pytest.raises(BudgetMismatch) as e:
        verify_matched_budget(a, c, _cmp())
    assert "requests" in e.value.report["violations"]


def test_verify_returns_report_on_pass():
    b = TraceBudget(10, 100, 50, 40)
    assert verify_matched_budget(b, b, _cmp())["matched"]


# ---- in-process controls are exactly budget-matched by construction ----


def test_uniform_arrivals_control_is_exact(repo):
    sc = load_scenario(repo / "experiments" / "a1_burst_arrivals.yaml")
    attack = summarize_trace(sc.build_trace())
    control, label = sc.control_trace()
    assert label == "uniform_arrivals"
    assert attack == summarize_trace(control)  # request count + all token budgets identical


def test_uniform_arrivals_changes_only_competitor_timing(repo):
    sc = load_scenario(repo / "experiments" / "a1_burst_arrivals.yaml")
    attack = sc.build_trace()
    control, _ = sc.control_trace()
    av = {i.request.request_id for i in attack if i.request.workload_class == "victim"}
    cv = {i.request.request_id for i in control if i.request.workload_class == "victim"}
    assert av == cv  # victim traffic untouched
    comp_a = sorted(i.request.arrival_time_s for i in attack if i.request.workload_class == "competitor")
    comp_c = sorted(i.request.arrival_time_s for i in control if i.request.workload_class == "competitor")
    assert comp_a != comp_c  # competitor arrivals re-timed


@pytest.mark.parametrize("name,ctrl,exact_count", [
    ("a2_prefill_heavy", "matched_total_short", False),
    ("a3_decode_heavy", "matched_total_short", False),
    ("a4_mixed_shapes", "homogeneous_mixture", True),
])
def test_shape_controls_match_total_tokens_every_seed(repo, name, ctrl, exact_count):
    sc = load_scenario(repo / "experiments" / f"{name}.yaml")
    assert sc.comparison.primary_control == ctrl
    for seed in (42, 7, 100, 5, 9):
        attack = summarize_trace(sc.build_trace(seed=seed))
        control, label = sc.control_trace(seed=seed)
        rep = budget_report(attack, summarize_trace(control), sc.comparison)
        assert rep["matched"], (name, seed, rep["violations"])
        if exact_count:
            assert rep["dimensions"]["requests"]["abs_delta"] == 0
        # victim traffic identical in attack and control
        av = {i.request.request_id for i in sc.build_trace(seed=seed) if i.request.workload_class == "victim"}
        cv = {i.request.request_id for i in control if i.request.workload_class == "victim"}
        assert av == cv


def test_shape_control_bodies_are_consistent(repo):
    # resized/regenerated competitor requests keep prompt length == input_token_count
    # (the mock backend recounts the payload).
    sc = load_scenario(repo / "experiments" / "a4_mixed_shapes.yaml")
    control, _ = sc.control_trace()
    for it in control:
        r = it.request
        if r.prompt_token_ids is not None:
            assert len(r.prompt_token_ids) == r.input_token_count
        assert it.oracle.realized_output_tokens <= r.max_output_tokens


def test_shuffled_phase_control_is_exact(repo):
    sc = load_scenario(repo / "experiments" / "stateful_sequences.yaml")
    attack = summarize_trace(sc.build_trace())
    control, label = sc.control_trace()
    assert label == "shuffled_phase_order"
    assert attack == summarize_trace(control)


def test_a1_budget_gate_passes(repo):
    sc = load_scenario(repo / "experiments" / "a1_burst_arrivals.yaml")
    control, _ = sc.control_trace()
    rep = verify_matched_budget(summarize_trace(sc.build_trace()), summarize_trace(control), sc.comparison)
    assert rep["matched"]


def test_shuffled_control_rejects_control_scenario_field(repo):
    base = load_scenario(repo / "experiments" / "stateful_sequences.yaml").model_dump()
    base["control_scenario"] = "somewhere.yaml"
    with pytest.raises((pydantic.ValidationError, ValueError), match="generated in-process"):
        ScenarioConfig.model_validate(base)
