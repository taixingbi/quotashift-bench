"""Scenario schema validation and the private-endpoint allowlist."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from quotashift.scenario import ScenarioConfig, endpoint_is_private, load_scenario

REPO_EXPERIMENTS = ("smoke.yaml", "baseline.yaml", "stateful_sequences.yaml")


def _base(**over) -> dict:
    d = dict(
        schema_version=1, scenario_id="t", seed=1, model="m", model_max_len=4096,
        runtime_seconds=20, endpoint="http://localhost:8080",
        victim_tenants=["victim_a"], competing_tenants=["comp"],
        safety=dict(max_total_requests=150, max_global_inflight=4, max_requests_per_tenant=60,
                    max_input_tokens_per_request=1024, max_output_tokens_per_request=256,
                    max_runtime_seconds=240),
        comparison=dict(primary_control="shuffled_phase_order"),
        benign=dict(rate_rps=0.5),
        phases=[dict(name="p1", duration_seconds=20, pattern="steady", request_shape="short", rate_rps=1.0)],
    )
    d.update(over)
    return d


def test_shipped_scenarios_are_valid(repo):
    for name in REPO_EXPERIMENTS:
        sc = load_scenario(repo / "experiments" / name)
        assert len(sc.schedule_hash()) == 64


@pytest.mark.parametrize("url,ok", [
    ("http://localhost:8080", True),
    ("http://127.0.0.1:8000", True),
    ("http://10.0.1.5:8000", True),
    ("http://gateway.quotashift.internal:8080", True),
    ("http://svc.internal", True),
    ("http://evil.example.com", False),
    ("https://api.openai.com/v1", False),
    ("http://8.8.8.8:8000", False),
    ("ftp://localhost", False),
])
def test_endpoint_allowlist(url, ok):
    assert endpoint_is_private(url)[0] is ok


def test_rejects_public_endpoint():
    with pytest.raises(ValueError, match="endpoint rejected"):
        ScenarioConfig.model_validate(_base(endpoint="http://malicious.example.com:8080"))


def test_cannot_disable_private_requirement():
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(_base(safety={**_base()["safety"], "require_private_endpoint": False}))


def test_cannot_enable_external_target():
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(_base(safety={**_base()["safety"], "allow_external_target": True}))


def test_phase_sum_must_equal_runtime():
    with pytest.raises(ValueError, match="phase durations"):
        ScenarioConfig.model_validate(_base(phases=[dict(name="p1", duration_seconds=5, rate_rps=1.0)]))


def test_victim_competitor_overlap_rejected():
    with pytest.raises(ValueError, match="both victim and competitor"):
        ScenarioConfig.model_validate(_base(victim_tenants=["x"], competing_tenants=["x"]))


def test_token_caps_exceed_model_len_rejected():
    s = {**_base()["safety"], "max_input_tokens_per_request": 4000, "max_output_tokens_per_request": 4000}
    with pytest.raises(ValueError, match="model_max_len"):
        ScenarioConfig.model_validate(_base(safety=s))


def test_per_tenant_budget_overflow_rejected():
    # 10 rps * 20 s = 200 expected > max_requests_per_tenant 60
    with pytest.raises(ValueError, match="max_requests_per_tenant"):
        ScenarioConfig.model_validate(_base(phases=[dict(name="p1", duration_seconds=20, rate_rps=10.0)]))


def test_unknown_key_rejected():
    with pytest.raises(ValidationError):
        ScenarioConfig.model_validate(_base(mystery_field=1))


def test_runtime_exceeds_safety_rejected():
    with pytest.raises(ValueError, match="max_runtime_seconds"):
        ScenarioConfig.model_validate(_base(runtime_seconds=9999,
                                            phases=[dict(name="p1", duration_seconds=9999, rate_rps=0.001)]))


def test_competitors_without_phases_rejected():
    with pytest.raises(ValueError, match="no phases"):
        ScenarioConfig.model_validate(_base(phases=[]))
