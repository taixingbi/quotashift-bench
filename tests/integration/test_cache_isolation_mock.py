"""End-to-end over HTTP against the CPU mock vLLM (prefix-cache *counters* emulated):
protocol v1 reproduces the historical cross-arm carry-over; v2 removes it and counterbalances.
Mock timings are simulator outputs — this checks plumbing and cache accounting, not GPU behaviour."""

from __future__ import annotations

import json

import pytest

from quotashift.config import BackendConfig
from quotashift.local import run_matched_pairs
from quotashift.runtime.runner import local_mock_server
from quotashift.scenario import ScenarioConfig
from quotashift.targets import TargetProfile

BASE = {
    "scenario_id": "iso", "seed": 3, "model": "mock-model", "model_max_len": 4096, "runtime_seconds": 3,
    "endpoint": "http://localhost:8080", "victim_tenants": ["victim_a", "victim_b"], "competing_tenants": ["comp"],
    "budget_class": "total_requests",
    "safety": {"max_total_requests": 400, "max_global_inflight": 8, "max_requests_per_tenant": 200,
               "max_input_tokens_per_request": 256, "max_output_tokens_per_request": 16, "max_runtime_seconds": 30,
               "per_request_timeout_seconds": 30},
    "comparison": {"primary_control": "shuffled_phase_order", "repetitions": 2},
    "benign": {"rate_rps": 4.0, "request_shape": "mixed"},
    "phases": [{"name": "p1", "duration_seconds": 1.5, "pattern": "steady", "request_shape": "short", "rate_rps": 4},
               {"name": "p2", "duration_seconds": 1.5, "pattern": "steady", "request_shape": "mixed", "rate_rps": 4}],
}


def _ec(run_dir) -> dict:
    return json.loads((run_dir / "metrics_summary.json").read_text())["engine_counters"]


@pytest.fixture(scope="module")
def target():
    with local_mock_server(BackendConfig(kind="mock_http", model="mock-model", time_scale=1.0)) as url:
        yield TargetProfile(name="mocklocal", kind="selfhost", backend_url=url, model="mock-model", max_model_len=4096)


def test_v1_carry_over_vs_v2_isolation(tmp_path, target):
    v1 = run_matched_pairs(ScenarioConfig.model_validate(BASE | {"scenario_id": "iso_v1"}), tmp_path, reps=2,
                           target=target)
    v2 = run_matched_pairs(ScenarioConfig.model_validate(BASE | {"scenario_id": "iso_v2", "protocol_version": 2}),
                           tmp_path, reps=2, target=target)
    # v1: control runs second and replays identical prompts -> warm cache (historical bias reproduced)
    for s in v1["seeds"]:
        assert v1["arm_order"][s] == ["attack", "control"]
        assert _ec(v1["attack"][s])["prefix_cache_hit_ratio"] < 0.05
        assert _ec(v1["control"][s])["prefix_cache_hit_ratio"] > 0.5
    # v2: salted per-arm nonce -> no cross-arm or cross-request prefix reuse; order counterbalanced
    assert v2["arm_order"][v2["seeds"][0]] == ["attack", "control"]
    assert v2["arm_order"][v2["seeds"][1]] == ["control", "attack"]
    for s in v2["seeds"]:
        for arm in ("attack", "control"):
            ec = _ec(v2[arm][s])
            assert ec["available"] and ec["prefix_cache_hit_ratio"] == 0.0, (arm, s, ec["prefix_cache_hit_ratio"])
            assert ec["unrelated_traffic_suspected"] is False, ec["attribution_notes"]
    m = json.loads((v2["attack"][v2["seeds"][0]] / "manifest.json").read_text())["run_context"]
    assert m["path"] == "gateway" and m["prefix_caching_enabled"] is True
    assert m["actual_counts"]["requests_completed"] == m["actual_counts"]["requests_offered"]


def test_direct_path_bypasses_gateway_controls(tmp_path, target):
    sc = ScenarioConfig.model_validate(BASE | {"scenario_id": "iso_direct", "protocol_version": 2})
    pairs = run_matched_pairs(sc, tmp_path, reps=1, target=target, path="direct")
    m = json.loads((pairs["attack"][sc.seed] / "manifest.json").read_text())["run_context"]
    assert m["path"] == "direct" and m["queue_caps"]["max_queue_wait_s"] is None
    s = json.loads((pairs["attack"][sc.seed] / "metrics_summary.json").read_text())
    assert s["accounting_conserved"] and s["event_validation_ok"]
