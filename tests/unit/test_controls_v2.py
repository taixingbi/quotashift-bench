"""New patterns/shapes/controls and the controlled-dimension contract."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from quotashift.scenario import CONTROL_DIMENSIONS, Comparison, ScenarioConfig, load_scenario
from quotashift.schema import ArrivalProcess
from quotashift.workload.generator import sample_arrivals

REPO = Path(__file__).resolve().parents[2]


def test_every_control_declares_dimensions():
    ctrls = Comparison.model_fields["primary_control"].annotation.__args__
    assert set(ctrls) == set(CONTROL_DIMENSIONS)
    for v in CONTROL_DIMENSIONS.values():
        assert "victim_traffic" in v["controlled"] and v["varies"]


def test_constant_arrivals_deterministic_spacing():
    t = sample_arrivals(ArrivalProcess(process="constant", rate_rps=2.0), 10.0, np.random.default_rng(0))
    assert len(t) == 20 and np.allclose(np.diff(t), 0.5)


def test_rate_matched_short_exact_count_and_arrivals():
    sc = load_scenario(REPO / "experiments" / "eseries" / "e3_noisy_neighbor.yaml")
    for seed in range(5):
        atk = sc.build_trace(seed)
        ctl, label = sc.control_trace(seed)
        assert label == "rate_matched_short"
        ca = sorted(i.request.arrival_time_s for i in atk if i.request.workload_class == "competitor")
        cc = sorted(i.request.arrival_time_s for i in ctl if i.request.workload_class == "competitor")
        assert ca == cc
        assert all(i.request.input_token_count == 64 for i in ctl if i.request.workload_class == "competitor")
        assert [i.request for i in atk if i.request.workload_class == "victim"] == \
               [i.request for i in ctl if i.request.workload_class == "victim"]


def test_long_context_shape_and_tenant_scaling():
    sc = load_scenario(REPO / "experiments" / "eseries" / "e6_kv_pressure.yaml")
    lc = [i.request for i in sc.build_trace(0) if i.request.workload_class == "competitor"]
    assert np.median([r.input_token_count for r in lc]) > 2500 and all(r.max_output_tokens == 256 for r in lc)
    totals = {}
    for n in (3, 10, 30):
        s = load_scenario(REPO / "experiments" / "eseries" / f"e5_scaling_{n}t.yaml")
        tr = s.build_trace(0)
        assert len({i.request.tenant_id for i in tr}) == n
        totals[n] = len(tr)
    assert max(totals.values()) / min(totals.values()) < 1.15  # total offered load held ~constant


def test_matched_flags_must_match_control_dimensions():
    d = load_scenario(REPO / "experiments" / "eseries" / "e3_noisy_neighbor.yaml").model_dump()
    d["comparison"]["matched_token_budget"] = True  # rate_matched_short does not control total tokens
    with pytest.raises(ValidationError, match="does not control total tokens"):
        ScenarioConfig.model_validate(d)


def test_expect_prefix_caching_yaml_bool_coercion():
    d = load_scenario(REPO / "experiments" / "v2" / "a2_prefill_heavy_v2.yaml").model_dump()
    d["expect_prefix_caching"] = False
    assert ScenarioConfig.model_validate(d).expect_prefix_caching == "off"
