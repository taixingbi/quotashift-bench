"""A7/A8/A9 end to end over HTTP against the CPU mock vLLM (simulator timings; plumbing only)."""

from __future__ import annotations

import json

import pytest

from quotashift.config import BackendConfig
from quotashift.instrumentation.cache_reset import reset_and_verify
from quotashift.local import LifecycleLeak, run_matched_pairs
from quotashift.runtime.runner import local_mock_server
from quotashift.scenario import ScenarioConfig
from quotashift.targets import TargetProfile

BASE = {
    "seed": 5, "model": "mock-model", "model_max_len": 4096, "runtime_seconds": 3, "protocol_version": 3,
    "endpoint": "http://localhost:8080", "victim_tenants": ["v00", "v01"], "competing_tenants": ["comp"],
    "safety": {"max_total_requests": 400, "max_global_inflight": 8, "max_requests_per_tenant": 200,
               "max_input_tokens_per_request": 512, "max_output_tokens_per_request": 128, "max_runtime_seconds": 30,
               "per_request_timeout_seconds": 30},
    "benign": {"rate_rps": 3.0, "request_shape": "mixed"},
}


def S(**kw) -> ScenarioConfig:
    return ScenarioConfig.model_validate(BASE | kw)


def summ(d):
    return json.loads((d / "metrics_summary.json").read_text())


@pytest.fixture(scope="module")
def target():
    with local_mock_server(BackendConfig(kind="mock_http", model="mock-model", time_scale=1.0)) as url:
        yield TargetProfile(name="mocklocal", kind="selfhost", backend_url=url, model="mock-model", max_model_len=4096)


def test_a7_cache_states_differ_and_reset_verified(tmp_path, target):
    sc = S(scenario_id="a7m", comparison={"primary_control": "prefix_unique", "effect_direction": "two_sided",
                                          "preregistered_threshold": 1.25, "repetitions": 2},
           phases=[{"name": "p", "duration_seconds": 3, "pattern": "steady", "request_shape": "context_heavy",
                    "rate_rps": 4}],
           prefix_cache={"victim_prefix_tokens": 64, "competitor_prefix_tokens": 256}, cache_reset="vllm_endpoint")
    pairs = run_matched_pairs(sc, tmp_path, reps=2, target=target)
    for s in pairs["seeds"]:
        assert all(v["verified"] for v in pairs["cache_resets"][s].values())
        ha = summ(pairs["attack"][s])["engine_counters"]["prefix_cache_hit_ratio"]
        hc = summ(pairs["control"][s])["engine_counters"]["prefix_cache_hit_ratio"]
        assert ha > hc + 0.1, (ha, hc)  # manipulation check: shared prefixes hit, unique ones do not
        pc = summ(pairs["attack"][s])["engine_counters"]["prefill_computed_tokens_est"]
        assert pc is not None and pc < summ(pairs["control"][s])["engine_counters"]["prefill_computed_tokens_est"]
        # per-request cached tokens (prompt_tokens_details), attributed per tenant by the gateway's labels
        ca, cc = summ(pairs["attack"][s])["cached_tokens"], summ(pairs["control"][s])["cached_tokens"]
        assert ca["any_reported"]
        comp_a, comp_c = ca["by_class"]["competitor"], cc["by_class"]["competitor"]
        assert comp_a["hit_ratio_reported"] > (comp_c["hit_ratio_reported"] or 0.0)  # shared vs unique prefixes
        assert comp_a["coverage"] == 1.0 and comp_a["zero_hit_reported"] >= 1  # cold request reports 0 (patched)
        assert ca["engine_reconciliation"]["residual"] == 0
        ec = summ(pairs["attack"][s])["engine_counters"]
        per_req = sum((t["cached_tokens_sum"] or 0) for t in ca["by_tenant"].values())
        assert per_req <= ec["prefix_cache_hits_total"] + 1e-6  # per-request hits never exceed the engine total


def test_reset_verification_fails_closed_on_missing_endpoint(target):
    r = reset_and_verify(target.backend_url, "mock-model", tag="x")
    assert r["verified"] is True
    bad = reset_and_verify("http://127.0.0.1:9", "mock-model", tag="y")
    assert bad["verified"] is False and "reason" in bad


def test_a8_cancel_timeout_cleanup_and_retry_bounds(tmp_path, target):
    common = dict(comparison={"primary_control": "lifecycle_normal", "repetitions": 1, "preregistered_threshold": 1.25},
                  phases=[{"name": "p", "duration_seconds": 3, "pattern": "steady", "request_shape": "decode_heavy",
                           "rate_rps": 4}], metrics_interval_s=0.25)
    a = S(scenario_id="a8m", lifecycle={"cancel_fraction": 0.5, "cancel_after_chunks": 4, "timeout_fraction": 0.3,
                                        "timeout_after_s": 0.15}, **common)
    pairs = run_matched_pairs(a, tmp_path, reps=1, target=target)
    sa, sc_ = summ(pairs["attack"][5]), summ(pairs["control"][5])
    for s in (sa, sc_):
        assert s["cleanup_checks"]["leak_detected"] is False, s["cleanup_checks"]
        assert s["cleanup_checks"]["engine_running_after_drain"] == 0
    det = sa["lifecycle"]["terminal_detail_counts"]
    assert det.get("planned_client_cancel", 0) > 0 and sa["lifecycle"]["cancel_close_s_p95"] is not None
    assert sa["actual_counts"]["requests_offered"] == sc_["actual_counts"]["requests_offered"]  # offered matched
    assert sa["actual_counts"]["output_tokens"] < sc_["actual_counts"]["output_tokens"]       # realized work differs

    b = S(scenario_id="a8bm", lifecycle={"timeout_fraction": 0.6, "timeout_after_s": 0.1, "retry_on": ["timeout"],
                                         "max_retries": 1, "retry_backoff_s": 0.05, "control_preschedule_retries": True},
          **common)
    pb = run_matched_pairs(b, tmp_path, reps=1, target=target)
    lb = summ(pb["attack"][5])["lifecycle"]
    planned = sum(1 for _ in lb["planned_actions"] if _ == "timeout_after_s") and lb["planned_actions"]["timeout_after_s"]
    assert 0 < lb["retries_fired"] <= planned
    assert lb["retries_fired"] + lb["retries_not_needed"] == planned
    assert summ(pb["attack"][5])["cleanup_checks"]["leak_detected"] is False


def test_leak_stops_experiment(tmp_path, target, monkeypatch):
    import quotashift.local as L

    real = L.run_scenario_local

    def leaky(*a, **kw):
        out = real(*a, **kw)
        s = summ(out)
        s["cleanup_checks"]["leak_detected"] = True
        (out / "metrics_summary.json").write_text(json.dumps(s))
        return out

    monkeypatch.setattr(L, "run_scenario_local", leaky)
    sc = S(scenario_id="leak", comparison={"primary_control": "identical_workload", "repetitions": 2,
                                           "preregistered_threshold": 1.25},
           phases=[{"name": "p", "duration_seconds": 3, "pattern": "steady", "request_shape": "short", "rate_rps": 2}])
    with pytest.raises(LifecycleLeak):
        run_matched_pairs(sc, tmp_path, reps=2, target=target)


def test_a9_cost_accounting_recorded(tmp_path, target):
    sc = S(scenario_id="a9m", comparison={"primary_control": "matched_total_short", "matched_request_budget": False,
                                          "repetitions": 1, "degradation_metric": "gpu_energy_per_1k_authorized_tokens",
                                          "effect_direction": "two_sided", "preregistered_threshold": 1.25},
           phases=[{"name": "p", "duration_seconds": 3, "pattern": "steady", "request_shape": "context_heavy",
                    "rate_rps": 2}])
    pairs = run_matched_pairs(sc, tmp_path, reps=1, target=target)
    ca = summ(pairs["attack"][5])["cost_accounting"]
    assert ca["authorized_tokens"] > ca["competitor_authorized_tokens"] > 0
    assert ca["gpu_energy_j"] is None and "unavailable" in ca["gpu_energy_method"]  # no GPU on CPU runner
    assert ca["engine_busy_s"] is not None and ca["kv_cache_usage_max"] is not None


def test_lifecycle_refuses_in_process_simulator(tmp_path):
    from quotashift.runtime.runner import SafetyError

    sc = S(scenario_id="a8sim", comparison={"primary_control": "lifecycle_normal", "repetitions": 1,
                                            "preregistered_threshold": 1.25},
           phases=[{"name": "p", "duration_seconds": 3, "pattern": "steady", "request_shape": "decode_heavy",
                    "rate_rps": 2}], lifecycle={"cancel_fraction": 0.5})
    with pytest.raises(SafetyError, match="HTTP backend"):
        run_matched_pairs(sc, tmp_path, reps=1, target=None)
