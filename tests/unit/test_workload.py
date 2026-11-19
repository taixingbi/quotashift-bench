import numpy as np

from quotashift.schema import LengthDist, WorkloadConfig
from quotashift.workload.generator import (
    generate_trace,
    read_trace_jsonl,
    sample_arrivals,
    tenant_rng,
    trace_hash,
    write_trace_jsonl,
)
from tests.conftest import tenant


def test_same_seed_identical(small_workload):
    assert trace_hash(generate_trace(small_workload, 11)) == trace_hash(generate_trace(small_workload, 11))


def test_different_seed_differs(small_workload):
    assert trace_hash(generate_trace(small_workload, 11)) != trace_hash(generate_trace(small_workload, 12))


def test_tenant_streams_independent(small_workload):
    """Changing tenant B's output distribution must not perturb A's or B's arrivals/prompts."""
    base = generate_trace(small_workload, 7)
    b2 = small_workload.tenants[1].model_copy(update={"sim_output_tokens": LengthDist(dist="fixed", value=5, max=256)})
    alt_cfg = small_workload.model_copy(update={"tenants": [small_workload.tenants[0], b2, small_workload.tenants[2]]})
    alt = generate_trace(alt_cfg, 7)

    def key(items, t):
        return [(i.request.arrival_time_s, i.request.input_token_count, i.request.prompt_text)
                for i in items if i.request.tenant_id == t]

    for t in "ABC":
        assert key(base, t) == key(alt, t)
    # and removing tenant C leaves A untouched
    no_c = small_workload.model_copy(update={"tenants": small_workload.tenants[:2]})
    assert key(generate_trace(no_c, 7), "A") == key(base, "A")


def test_requested_vs_realized_bounds(small_workload):
    for it in generate_trace(small_workload, 3):
        r = it.request
        assert 0 <= it.oracle.realized_output_tokens <= r.max_output_tokens
        assert r.input_token_count + r.max_output_tokens <= small_workload.max_model_len or r.max_output_tokens == 1


def test_arrivals_sorted_and_in_window(small_workload):
    items = generate_trace(small_workload, 5)
    ts = [i.request.arrival_time_s for i in items]
    assert ts == sorted(ts)
    assert all(0 <= t < small_workload.duration_s for t in ts)
    assert len({i.request.request_id for i in items}) == len(items)


def test_poisson_rate_close():
    t = tenant("A", rate=10.0)
    arr = sample_arrivals(t.arrival, 2000, tenant_rng(1, "A", "arrivals"))
    assert abs(len(arr) / 2000 - 10.0) < 0.3


def test_onoff_is_burstier_than_poisson():
    on = tenant("C", rate=0.2, process="onoff", burst_rate_rps=8.0, mean_on_s=5, mean_off_s=20).arrival
    arr = sample_arrivals(on, 4000, tenant_rng(2, "C", "arrivals"))
    counts = np.histogram(arr, bins=np.arange(0, 4001, 1.0))[0]
    assert counts.var() / counts.mean() > 2.0  # index of dispersion >> 1 (Poisson = 1)


def test_jsonl_roundtrip(tmp_path, small_workload):
    items = generate_trace(small_workload, 9)
    h = write_trace_jsonl(items, tmp_path / "t.jsonl")
    back = read_trace_jsonl(tmp_path / "t.jsonl")
    assert trace_hash(back) == h


def test_token_id_prompts():
    cfg = WorkloadConfig(workload_id="ids", duration_s=5, prompt_mode="token_ids", tenants=[tenant("A", 2.0)])
    for it in generate_trace(cfg, 1):
        assert it.request.prompt_text is None
        assert len(it.request.prompt_token_ids) == it.request.input_token_count
