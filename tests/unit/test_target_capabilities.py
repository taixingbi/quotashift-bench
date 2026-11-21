"""Read-only self-host capability parsing (dev-mode reset, prefix caching, exporter power)."""

from pathlib import Path

from quotashift.targets import parse_capabilities

METRICS = (
    'vllm:cache_config_info{block_size="16",enable_prefix_caching="True",engine="0",gpu_memory_utilization="0.8",'
    'num_gpu_blocks="4662"} 1.0\n'
    "process_start_time_seconds 1.79525912933e+09\n"
    'vllm:num_requests_running{engine="0"} 0.0\nvllm:num_requests_waiting{engine="0"} 0.0\n'
)


def test_capabilities_from_live_shaped_inputs():
    exporter = (Path(__file__).parents[1] / "fixtures" / "nvidia_gpu_exporter_rtx3090.prom").read_text()
    c = parse_capabilities(["/v1/models", "/reset_prefix_cache"], METRICS, exporter)
    assert c["reset_prefix_cache_listed"] is True and c["prefix_caching"] is True
    assert c["gpu_memory_utilization"] == 0.8 and c["num_gpu_blocks"] == 4662 and c["engine_idle"] is True
    assert c["gpu_exporter"]["power_w_ok"] is True


def test_capabilities_missing_parts_are_unknown_not_assumed():
    c = parse_capabilities(["/v1/models"], None, None)
    assert c == {"reset_prefix_cache_listed": False}
    c = parse_capabilities(None, "vllm:num_requests_running 2\nvllm:num_requests_waiting 0\n", None)
    assert c["prefix_caching"] is None and c["engine_idle"] is False
