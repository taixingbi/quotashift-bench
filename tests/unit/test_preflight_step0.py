"""PLAN step 0: by-source prefill counter, sleep state, restart detection, fail-closed engine preflight,
cross-arm restart stop, per-suite target snapshot. Metric lines are the real vLLM 0.17.1 format (.173)."""

from __future__ import annotations

import asyncio
import json

import pytest

from quotashift.instrumentation.engine_counters import counter_deltas
from quotashift.instrumentation.prom import parse_prometheus_text, resolve

L = 'engine="0",model_name="Qwen/Qwen2.5-7B-Instruct"'


def snap(*, start=1795268683.89, compute=100.0, cache_hit=20.0, prompt=120.0, hits=20.0, running=0, waiting=0,
         awake=1.0):
    text = f"""
process_start_time_seconds {start}
vllm:num_requests_running{{{L}}} {running}
vllm:num_requests_waiting{{{L}}} {waiting}
vllm:engine_sleep_state{{{L},sleep_state="awake"}} {awake}
vllm:engine_sleep_state{{{L},sleep_state="weights_offloaded"}} 0.0
vllm:prompt_tokens_total{{{L}}} {prompt}
vllm:prefix_cache_queries_total{{{L}}} {prompt}
vllm:prefix_cache_hits_total{{{L}}} {hits}
vllm:prompt_tokens_by_source_total{{{L},source="local_compute"}} {compute}
vllm:prompt_tokens_by_source_total{{{L},source="local_cache_hit"}} {cache_hit}
vllm:prompt_tokens_by_source_total{{{L},source="external_kv_transfer"}} 0.0
"""
    return resolve(parse_prometheus_text(text))


def test_labelled_metrics_resolved():
    s = snap()
    assert s.values["prompt_tokens_local_compute_total"] == 100.0
    assert s.values["prompt_tokens_local_cache_hit_total"] == 20.0  # not summed with other sources
    assert s.values["engine_awake"] == 1.0 and s.values["process_start_time_seconds"] == 1795268683.89
    assert resolve(parse_prometheus_text("vllm:num_requests_running 0\n")).values["engine_awake"] is None


def test_measured_prefill_beside_estimate_and_restart_detection():
    d = counter_deltas(snap(), snap(compute=1100.0, cache_hit=520.0, prompt=1620.0, hits=520.0),
                       client_prompt_tokens=1500)
    assert d["prefill_computed_tokens_measured"] == 1000.0 and d["prefill_computed_tokens_est"] == 1000.0
    assert d["prefill_est_minus_measured"] == 0.0 and d["server_restarted"] is False
    r = counter_deltas(snap(), snap(start=1795270000.0, compute=150.0, cache_hit=30.0, prompt=180.0, hits=30.0))
    assert r["server_restarted"] is True and r["unrelated_traffic_suspected"] is True
    assert "process_start_time_seconds" in r["resets"]


class FakeBe:
    def __init__(self, seq):
        self.seq, self.i = seq, 0

    async def scrape_metrics(self):
        v = self.seq[min(self.i, len(self.seq) - 1)]
        self.i += 1
        return v


def test_preflight_waits_then_fails_closed():
    from quotashift.runtime.runner import EngineNotReady, preflight_engine_ready

    st = asyncio.run(preflight_engine_ready(FakeBe([snap(running=2), snap(waiting=1), snap()]), interval_s=0.0))
    assert st["num_requests_running"] == 0 and st["engine_awake"] == 1.0
    with pytest.raises(EngineNotReady):
        asyncio.run(preflight_engine_ready(FakeBe([snap(running=1)]), timeout_s=0.05, interval_s=0.01))
    with pytest.raises(EngineNotReady):  # sleeping engine is not ready
        asyncio.run(preflight_engine_ready(FakeBe([snap(awake=0.0)]), timeout_s=0.05, interval_s=0.01))
    with pytest.raises(EngineNotReady):  # no /metrics at all -> not assumed ready
        asyncio.run(preflight_engine_ready(FakeBe([None]), timeout_s=0.05, interval_s=0.01))


def test_matched_pairs_stop_on_server_restart(tmp_path, monkeypatch):
    import quotashift.local as local
    from quotashift.scenario import ScenarioConfig

    sc = ScenarioConfig.model_validate({
        "scenario_id": "rs", "seed": 1, "model": "m", "model_max_len": 4096, "runtime_seconds": 2,
        "protocol_version": 2, "endpoint": "http://localhost:8080", "victim_tenants": ["v"],
        "competing_tenants": ["c"],
        "safety": {"max_total_requests": 50, "max_global_inflight": 4, "max_requests_per_tenant": 40,
                   "max_input_tokens_per_request": 256, "max_output_tokens_per_request": 64,
                   "max_runtime_seconds": 10, "per_request_timeout_seconds": 10},
        "benign": {"rate_rps": 2.0, "request_shape": "mixed"},
        "phases": [{"name": "p", "duration_seconds": 2, "pattern": "steady", "request_shape": "mixed", "rate_rps": 2}],
        "comparison": {"primary_control": "matched_total_short", "repetitions": 2,
                       "matched_request_budget": False}})
    starts = iter([100.0, 100.0, 100.0, 200.0])

    def fake_run(scenario, root, **kw):
        d = tmp_path / f"{kw['experiment_id']}_{kw['seed']}"
        d.mkdir()
        (d / "metrics_summary.json").write_text(json.dumps({"engine_counters": {
            "engine_state_at_start": {"process_start_time_seconds": next(starts)}}, "cleanup_checks": {}}))
        return d

    monkeypatch.setattr(local, "run_scenario_local", fake_run)
    with pytest.raises(local.ServerRestarted):
        local.run_matched_pairs(sc, tmp_path, reps=2)


def test_target_snapshot_written_against_mock(tmp_path):
    from quotashift.config import BackendConfig
    from quotashift.runtime.runner import local_mock_server
    from quotashift.targets import TargetProfile, write_target_snapshot

    with local_mock_server(BackendConfig(kind="mock_http", model="mock-model", time_scale=1.0)) as url:
        prof = TargetProfile(name="mocklocal", kind="selfhost", backend_url=url, model="mock-model", max_model_len=4096)
        rec = write_target_snapshot(prof, tmp_path / "target_snapshot")
    out = tmp_path / "target_snapshot"
    assert (out / "target_check.json").exists() and (out / "models.json").exists()
    assert all(ln.startswith(("vllm:", "process_start_time_seconds"))
               for ln in (out / "metrics_vllm.prom").read_text().splitlines() if ln)
    assert rec["check"]["reachable"] is True


def test_warm_cache_rerun_detected_only_for_same_trace_and_server_start(tmp_path):
    from quotashift.local import warm_cache_reruns
    from quotashift.scenario import ScenarioConfig
    from quotashift.workload.generator import trace_hash

    sc = ScenarioConfig.model_validate({
        "scenario_id": "w", "seed": 3, "model": "m", "model_max_len": 4096, "runtime_seconds": 2,
        "endpoint": "http://localhost:8080", "victim_tenants": ["v"], "competing_tenants": ["c"],
        "phases": [{"name": "p", "duration_seconds": 2, "pattern": "steady", "request_shape": "mixed", "rate_rps": 2}],
        "safety": {"max_total_requests": 50, "max_global_inflight": 4, "max_requests_per_tenant": 40,
                   "max_input_tokens_per_request": 256, "max_output_tokens_per_request": 64,
                   "max_runtime_seconds": 10, "per_request_timeout_seconds": 10},
        "benign": {"rate_rps": 2.0, "request_shape": "mixed"},
        "comparison": {"primary_control": "matched_total_short", "repetitions": 2, "matched_request_budget": False}})
    tr = sc.build_trace(seed=3)
    d = tmp_path / "w__attack" / "20261121T000000Z_fcfs_3"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"trace_sha256": trace_hash(tr)}))
    (d / "metrics_summary.json").write_text(json.dumps(
        {"engine_counters": {"engine_state_at_start": {"process_start_time_seconds": 100.0}}}))
    assert warm_cache_reruns(tmp_path, "w__attack", tr, 100.0) == [d]
    assert warm_cache_reruns(tmp_path, "w__attack", tr, 200.0) == []  # server restarted since: cold cache
    assert warm_cache_reruns(tmp_path, "w__attack", sc.build_trace(seed=4), 100.0) == []  # different prompts
    assert warm_cache_reruns(tmp_path, "w__attack", tr, None) == []
