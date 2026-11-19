"""Deterministic schedule generation and replay (plan acceptance §7)."""

from __future__ import annotations

from quotashift.scenario import load_scenario
from quotashift.workload.generator import read_trace_jsonl, write_trace_jsonl


def _smoke(repo):
    return load_scenario(repo / "experiments" / "smoke.yaml")


def test_same_seed_same_hash(repo):
    sc = _smoke(repo)
    assert sc.schedule_hash(seed=7) == sc.schedule_hash(seed=7)


def test_different_seed_changes_hash(repo):
    sc = _smoke(repo)
    assert sc.schedule_hash(seed=7) != sc.schedule_hash(seed=8)


def test_control_order_changes_hash(repo):
    sc = load_scenario(repo / "experiments" / "stateful_sequences.yaml")
    names = [p.name for p in sc.phases]
    assert sc.schedule_hash() != sc.schedule_hash(phase_order=list(reversed(names)))


def test_schedule_within_total_cap(repo):
    sc = _smoke(repo)
    assert len(sc.build_trace()) <= sc.safety.max_total_requests


def test_request_shapes_respect_caps(repo):
    sc = _smoke(repo)
    for it in sc.build_trace():
        r = it.request
        assert r.input_token_count <= sc.safety.max_input_tokens_per_request
        assert r.max_output_tokens <= sc.safety.max_output_tokens_per_request
        assert it.oracle.realized_output_tokens <= r.max_output_tokens


def test_trace_roundtrips_from_disk(repo, tmp_path):
    sc = _smoke(repo)
    items = sc.build_trace()
    h = write_trace_jsonl(items, tmp_path / "trace.jsonl")
    back = read_trace_jsonl(tmp_path / "trace.jsonl")
    assert len(back) == len(items)
    assert [i.request.request_id for i in back] == [i.request.request_id for i in items]
    assert h == sc.schedule_hash()


def test_victim_traffic_identical_across_control(repo):
    sc = load_scenario(repo / "experiments" / "stateful_sequences.yaml")
    names = [p.name for p in sc.phases]
    base = {i.request.request_id for i in sc.build_trace() if i.request.workload_class == "victim"}
    ctrl = {i.request.request_id for i in sc.build_trace(phase_order=list(reversed(names)))
            if i.request.workload_class == "victim"}
    assert base == ctrl
