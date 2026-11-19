from quotashift.instrumentation.prom import hist_delta, parse_prometheus_text, resolve

V1_TEXT = """
# HELP vllm:num_requests_running Number of requests in model execution batches.
# TYPE vllm:num_requests_running gauge
vllm:num_requests_running{engine="0",model_name="Qwen/Qwen3-4B"} 3.0
vllm:num_requests_waiting{engine="0",model_name="Qwen/Qwen3-4B"} 7.0
vllm:kv_cache_usage_perc{engine="0",model_name="Qwen/Qwen3-4B"} 0.42
vllm:num_preemptions_total{engine="0",model_name="Qwen/Qwen3-4B"} 5.0
vllm:time_to_first_token_seconds_bucket{engine="0",le="0.1",model_name="m"} 2.0
vllm:time_to_first_token_seconds_bucket{engine="0",le="+Inf",model_name="m"} 4.0
vllm:time_to_first_token_seconds_sum{engine="0",model_name="m"} 1.5
vllm:time_to_first_token_seconds_count{engine="0",model_name="m"} 4.0
garbage line that should be ignored {
"""

LEGACY_TEXT = """
vllm:gpu_cache_usage_perc{model_name="m"} 0.9
vllm:num_requests_running{model_name="m"} 1
"""


def test_parse_and_resolve_v1_names():
    snap = resolve(parse_prometheus_text(V1_TEXT))
    assert snap.values["num_requests_running"] == 3.0
    assert snap.values["kv_cache_usage_perc"] == 0.42
    assert snap.resolved_names["kv_cache_usage_perc"] == "vllm:kv_cache_usage_perc"
    assert snap.histograms["ttft_seconds"] == [(0.1, 2.0), (float("inf"), 4.0)]
    assert snap.histogram_sums["ttft_seconds"] == (1.5, 4.0)


def test_fallback_and_missing_are_explicit():
    snap = resolve(parse_prometheus_text(LEGACY_TEXT))
    assert snap.values["kv_cache_usage_perc"] == 0.9
    assert snap.resolved_names["kv_cache_usage_perc"] == "vllm:gpu_cache_usage_perc"
    assert snap.values["num_preemptions_total"] is None
    assert "num_preemptions_total" in snap.missing
    assert snap.values["num_requests_waiting"] is None  # never invented


def test_empty_scrape():
    snap = resolve(parse_prometheus_text(""))
    assert all(v is None for v in snap.values.values())


def test_hist_delta_and_reset():
    a = [(0.1, 5.0), (float("inf"), 9.0)]
    b = [(0.1, 2.0), (float("inf"), 3.0)]
    assert hist_delta(a, b) == [(0.1, 3.0), (float("inf"), 6.0)]
    assert hist_delta(b, a) == b  # counter reset => fresh
    assert hist_delta(a, None) == a
