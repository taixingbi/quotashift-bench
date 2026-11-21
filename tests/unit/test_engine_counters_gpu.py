"""Engine counter deltas (resets, unrelated traffic, cache-hit ratio) and GPU telemetry parsing."""

from __future__ import annotations

import pytest

from quotashift.instrumentation.engine_counters import counter_deltas, engine_state
from quotashift.instrumentation.gpu import (
    GpuSampler,
    exporter_metrics_text,
    parse_exporter_text,
    parse_smi_csv,
)
from quotashift.instrumentation.prom import parse_prometheus_text, resolve

BASE = """vllm:num_requests_running{engine="0"} RUN
vllm:num_requests_waiting{engine="0"} 0
vllm:prompt_tokens_total{engine="0"} P
vllm:generation_tokens_total{engine="0"} G
vllm:prefix_cache_queries_total{engine="0"} Q
vllm:prefix_cache_hits_total{engine="0"} H
vllm:time_to_first_token_seconds_sum{engine="0"} TS
vllm:time_to_first_token_seconds_count{engine="0"} TC
vllm:time_to_first_token_seconds_bucket{engine="0",le="+Inf"} TC
vllm:cache_config_info{block_size="16",enable_prefix_caching="True",engine="0"} 1.0
"""


def snap(run=0, p=0, g=0, q=0, h=0, ts=0.0, tc=0):
    t = BASE
    for k, v in (("RUN", run), ("TS", ts), ("TC", tc), ("P", p), ("G", g), ("Q", q), ("H", h)):
        t = t.replace(f" {k}\n", f" {v}\n")
    return resolve(parse_prometheus_text(t))


def test_deltas_hit_ratio_and_attribution_ok():
    d = counter_deltas(snap(p=1000, g=100, q=1000, h=200, ts=1.0, tc=10),
                       snap(p=3000, g=600, q=3000, h=300, ts=5.0, tc=30),
                       client_prompt_tokens=2000, client_generation_tokens=500)
    assert d["prompt_tokens_total"] == 2000 and d["prefix_cache_hit_ratio"] == pytest.approx(0.05)
    assert d["ttft_seconds_count"] == 20 and d["ttft_seconds_mean"] == pytest.approx(0.2)
    assert d["unrelated_traffic_suspected"] is False
    assert d["engine_state_at_start"]["prefix_caching_enabled"] is True


def test_counter_reset_detected():
    d = counter_deltas(snap(p=5000, q=5000, tc=50, ts=9.0), snap(p=100, q=100, tc=2, ts=0.1))
    assert d["prompt_tokens_total"] == "reset" and d["ttft_seconds_count"] == "reset"
    assert d["prefix_cache_hit_ratio"] is None and d["unrelated_traffic_suspected"] is True


def test_unrelated_traffic_detected():
    d = counter_deltas(snap(p=0), snap(p=5000), client_prompt_tokens=2000)
    assert d["unrelated_traffic_suspected"] and "exceed" in d["attribution_notes"][0]
    busy = counter_deltas(snap(run=3), snap(run=0))
    assert busy["unrelated_traffic_suspected"] and "busy" in busy["attribution_notes"][0]


def test_missing_snapshots_and_state():
    assert counter_deltas(None, snap())["available"] is False
    assert engine_state(None) == {"available": False}


def test_smi_parse_with_clocks_and_na():
    r = parse_smi_csv("87, 18000, 24576, 66, 1695, 9751, 280.5\n")
    assert r == {"gpu_util_perc": 87.0, "mem_used_mib": 18000.0, "mem_total_mib": 24576.0, "temp_c": 66.0,
                 "sm_clock_mhz": 1695.0, "mem_clock_mhz": 9751.0, "power_w": 280.5}
    assert parse_smi_csv("[N/A], 1, 2, 3, [N/A], 5, 6")["gpu_util_perc"] is None


def test_dcgm_and_own_exporter_parse():
    d = parse_exporter_text('DCGM_FI_DEV_GPU_UTIL{gpu="0",UUID="x"} 77\nDCGM_FI_DEV_FB_USED{gpu="0"} 12000\n'
                            'DCGM_FI_DEV_FB_FREE{gpu="0"} 12576\nDCGM_FI_DEV_GPU_UTIL{gpu="1"} 5\n')
    assert d == {"gpu_util_perc": 77.0, "mem_used_mib": 12000.0, "mem_free_mib": 12576.0, "mem_total_mib": 24576.0}

    class Fake(GpuSampler):
        def sample(self):
            return {"gpu_util_perc": 50.0, "power_w": 200.0, "sm_clock_mhz": None}

    text = exporter_metrics_text(Fake(source="none"))
    assert parse_exporter_text(text) == {"gpu_util_perc": 50.0, "power_w": 200.0}
    assert "quotashift_gpu_sample_ok 1" in text


def test_gpu_sampler_sources(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    assert GpuSampler().available is False and GpuSampler().sample() == {}  # historical default, no GPU here
    assert GpuSampler(source="none").static_info()["available"] is False
    with pytest.raises(ValueError):
        GpuSampler(source="exporter")
    with pytest.raises(ValueError, match="rejected"):
        GpuSampler(source="exporter", exporter_url="http://8.8.8.8:9835/metrics")
    assert GpuSampler(source="nvidia-smi", smi_prefix=["ssh", "h"]).available is True


def test_noncompleted_requests_bounded_not_flagged():
    # cancelled requests were prefilled/decoded but report no usage -> bounded, not "unrelated traffic"
    d = counter_deltas(snap(p=0, g=0), snap(p=2500, g=600), client_prompt_tokens=2000, client_generation_tokens=500,
                       noncompleted_prompt_upper=600.0, noncompleted_generation_upper=256.0)
    assert d["unrelated_traffic_suspected"] is False and d["attribution_mode"] == "bounded"
    d2 = counter_deltas(snap(p=0), snap(p=5000), client_prompt_tokens=2000, noncompleted_prompt_upper=600.0)
    assert d2["unrelated_traffic_suspected"] is True
    d3 = counter_deltas(snap(p=0), snap(p=2500), client_prompt_tokens=2000, noncompleted_prompt_upper=None)
    assert d3["attribution_mode"] == "unverifiable" and d3["unrelated_traffic_suspected"] is True


def test_nvidia_gpu_exporter_parse_real_scrape():
    """Lines captured from nvidia_gpu_exporter v2.0.0 on the self-hosted RTX 3090 (2026-11-21, idle)."""
    from pathlib import Path

    text = (Path(__file__).parents[1] / "fixtures" / "nvidia_gpu_exporter_rtx3090.prom").read_text()
    d = parse_exporter_text(text, 0)
    assert 5.0 < d["power_w"] < 350.0  # board power, W
    assert d["mem_total_mib"] == 2.5769803776e10 / 2**20  # 24 GiB card
    assert 0.0 <= d["gpu_util_perc"] <= 100.0  # ratio -> percent
    assert d["sm_clock_mhz"] is not None and d["sm_clock_mhz"] < 3000  # Hz -> MHz
    assert parse_exporter_text(text, 1) == {}  # other index: nothing assumed


def test_nvidia_gpu_exporter_unknown_uuid_ignored():
    text = 'nvidia_smi_power_draw_watts{uuid="zzz"} 200\n'  # no gpu_info line -> index unknown
    assert parse_exporter_text(text, 0) == {}


def test_idle_settled_rejects_hot_gpu():
    from quotashift.instrumentation.gpu import idle_settled

    hot = [{"power_w": p, "gpu_util_perc": 0} for p in (216, 180, 140, 100, 70, 50)]  # decaying after an arm
    assert not idle_settled(hot)
    busy = [{"power_w": 30, "gpu_util_perc": u} for u in (0, 0, 0, 0, 0, 12)]
    assert not idle_settled(busy)
    assert idle_settled([{"power_w": p, "gpu_util_perc": 0} for p in (31, 30, 30, 29.5, 30.2, 30)])
    # measured 3090 plateau: util 0, power stable ~130 W, but SM clock still at load level -> NOT idle
    plateau = [{"power_w": p, "gpu_util_perc": 0, "sm_clock_mhz": 1725} for p in (131, 131, 130.8, 130.6, 130.4, 130.1)]
    assert not idle_settled(plateau)
    assert idle_settled([{"power_w": p, "gpu_util_perc": 0, "sm_clock_mhz": 210} for p in (32, 31.5, 40.6, 31.8, 31.7, 31.6)])
    transition = [{"power_w": p, "gpu_util_perc": 0, "sm_clock_mhz": 210} for p in (77.2, 35.6, 40.9, 33.3, 32.0, 32.2)]
    assert not idle_settled(transition)  # P-state transition still in the window
    assert not idle_settled([{"power_w": 30}] * 3)  # window not yet full


def test_settle_idle_power_waits_then_times_out():
    import asyncio

    from quotashift.instrumentation.gpu import settle_idle_power

    class Fake:
        def __init__(self, seq):
            self.seq, self.i = seq, 0

        async def asample(self):
            v = self.seq[min(self.i, len(self.seq) - 1)]
            self.i += 1
            return {"power_w": v, "gpu_util_perc": 0}

    r = asyncio.run(settle_idle_power(Fake([216, 150, 90, 40, 31, 30, 30, 30, 30, 30, 30]), interval_s=0.0))
    assert r["settled"] and 29 < r["idle_power_w"] < 32 and r["first_power_w"] == 216
    from quotashift.instrumentation.gpu import trapezoid_j

    assert trapezoid_j([(0.0, 100.0), (1.0, 100.0), (3.0, 50.0)]) == 100.0 + 150.0
    assert trapezoid_j([(0.0, 1.0)]) is None
    class Busy(Fake):
        async def asample(self):
            return {"power_w": 30, "gpu_util_perc": 7}  # stable power but GPU in use (e.g. another process)

    r = asyncio.run(settle_idle_power(Busy([]), interval_s=0.01, timeout_s=0.1))
    assert not r["settled"] and r["idle_power_w"] is None  # not idle within timeout -> no baseline, never guessed
