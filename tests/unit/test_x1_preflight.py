"""X1 preflight rules (src/quotashift/x1/preflight.py; draft rev 4 section 9). Synthetic inputs only."""

from __future__ import annotations

import pytest

from quotashift.x1 import preflight as pf

GIB = pf.GIB
OK_LOAD = dict(healthy=True, startup_complete=True, models_lists_pinned_revision=True, weight_hash_ok=True,
               argv_matches_template=True, smoke_generation_ok=True, startup_s=600.0)


# ------------------------------------------------------------------ model loading: warnings never fail
def test_healthy_instance_with_warnings_passes():
    # WARNING-level lines (dtype casts, FlashInfer unavailable) are not even passed in: they never matter.
    assert pf.model_load_check(**OK_LOAD)["status"] == "pass"


def test_error_lines_on_a_healthy_instance_only_flag_for_review():
    r = pf.model_load_check(**OK_LOAD, log_error_lines=["ERROR ... optional kernel autotune failed"])
    assert r["status"] == "flag" and "owner review" in r["reasons"][0]


@pytest.mark.parametrize("field", ["healthy", "startup_complete", "models_lists_pinned_revision", "weight_hash_ok",
                                   "argv_matches_template", "smoke_generation_ok"])
def test_observable_failures_fail(field):
    assert pf.model_load_check(**(OK_LOAD | {field: False}))["status"] == "fail"


def test_load_timeout_and_slow_load():
    assert pf.model_load_check(**(OK_LOAD | {"startup_s": 1801.0}))["status"] == "fail"
    assert pf.model_load_check(**(OK_LOAD | {"startup_s": None}))["status"] == "fail"
    assert pf.model_load_check(**OK_LOAD, g0_startup_s=200.0)["status"] == "flag"      # 600 > 2 x 200
    assert pf.model_load_check(**OK_LOAD, g0_startup_s=400.0)["status"] == "pass"


# ------------------------------------------------------------------ KV capacity (preserved)
def test_kv_capacity():
    assert pf.KV_MIN_TOKENS == 20480
    assert pf.kv_capacity_check(20479)["status"] == "fail"
    assert pf.kv_capacity_check(30000)["status"] == "pass"
    assert pf.kv_capacity_check(30000, observed_direct_peak_tokens=8000)["status"] == "flag"
    assert pf.kv_capacity_check(46080, observed_direct_peak_tokens=8000)["status"] == "pass"


# ------------------------------------------------------------------ RAM (preserved: >= 1 GiB, zero OOM kills)
def _mem(vals, oom=(0, 0), swp=(0, 0)):
    n = len(vals)
    return [{"mem_available": v, "oom_kill": oom[0] if i < n - 1 else oom[1],
             "pswpin": swp[0] if i < n - 1 else swp[1]} for i, v in enumerate(vals)]


def test_ram_rules():
    assert pf.ram_check(_mem([3 * GIB, 2.5 * GIB]))["status"] == "pass"
    assert pf.ram_check(_mem([3 * GIB, 0.9 * GIB]))["status"] == "fail"
    assert pf.ram_check(_mem([3 * GIB, 3 * GIB], oom=(4, 5)))["status"] == "fail"
    assert pf.ram_check(_mem([3 * GIB, 1.5 * GIB]))["status"] == "flag"
    assert pf.ram_check(_mem([3 * GIB, 3 * GIB], swp=(10, 12)))["status"] == "flag"
    assert pf.ram_check([])["status"] == "fail"


# ------------------------------------------------------------------ CPU
def _cpu(host, api):
    return [{"host_busy": h, "api_cpu": a} for h, a in zip(host, api, strict=True)]


def test_cpu_preflight_fail_and_per_arm_flag_only():
    hot = _cpu([0.97] * 2 + [0.3] * 8, [0.2] * 10)             # 20% of samples >= 95%
    assert pf.cpu_check(hot, preflight=True)["status"] == "fail"
    assert pf.cpu_check(hot, preflight=False)["status"] == "flag"   # per-arm gate never fails a block


def test_cpu_flags():
    assert pf.cpu_check(_cpu([0.3] * 20, [0.9] + [0.2] * 19), preflight=True)["status"] == "flag"   # api 5%
    assert pf.cpu_check(_cpu([0.85] * 2 + [0.3] * 18, [0.2] * 20), preflight=True)["status"] == "flag"  # host 10%
    assert pf.cpu_check(_cpu([0.3] * 20, [0.2] * 20), preflight=True)["status"] == "pass"
    r = pf.cpu_check(_cpu([0.3] * 5, [None] * 5), preflight=False)
    assert r["status"] == "flag" and "not found" in r["reasons"][0]


# ------------------------------------------------------------------ tokenization: isolated vs burst
def test_isolated_latency_rule():
    fast = [2.0] * 199 + [3.0]
    assert pf.tokenization_check(isolated_ms=fast, peak_request_rps=5)["status"] == "pass"
    slow = [2.0] * 190 + [30.0] * 10                            # p99 = 30 ms
    assert pf.tokenization_check(isolated_ms=slow, peak_request_rps=5)["status"] == "fail"


def test_utilisation_rule_is_the_10x_headroom():
    iso = [10.0] * 200                                           # 10 ms service time
    assert pf.tokenization_check(isolated_ms=iso, peak_request_rps=10)["rho_at_peak"] == pytest.approx(0.1)
    assert pf.tokenization_check(isolated_ms=iso, peak_request_rps=10)["status"] == "pass"
    assert pf.tokenization_check(isolated_ms=iso, peak_request_rps=11)["status"] == "fail"


def test_burst_queueing_is_judged_separately_from_isolated_latency():
    iso = [2.0] * 200
    ok = pf.tokenization_check(isolated_ms=iso, peak_request_rps=5, burst_offered_rps=50, burst_achieved_rps=49.9,
                               burst_ms=[2.5] * 1000)
    assert ok["status"] == "pass" and ok["burst_excess_p99_ms"] == pytest.approx(0.5)
    q = pf.tokenization_check(isolated_ms=iso, peak_request_rps=5, burst_offered_rps=50, burst_achieved_rps=50,
                              burst_ms=[2.0] * 980 + [9.0] * 20)
    assert q["status"] == "flag"                                 # 7 ms excess
    bad = pf.tokenization_check(isolated_ms=iso, peak_request_rps=5, burst_offered_rps=50, burst_achieved_rps=50,
                                burst_ms=[2.0] * 980 + [20.0] * 20)
    assert bad["status"] == "fail"                               # 18 ms excess
    short = pf.tokenization_check(isolated_ms=iso, peak_request_rps=5, burst_offered_rps=50, burst_achieved_rps=40,
                                  burst_ms=[2.0] * 1000)
    assert short["status"] == "fail"                             # could not sustain the burst
    low = pf.tokenization_check(isolated_ms=iso, peak_request_rps=5, burst_offered_rps=20, burst_achieved_rps=20,
                                burst_ms=[2.0] * 600)
    assert low["status"] == "fail"                               # burst below 10 x peak


def test_relative_flag_against_g0():
    iso = [6.0] * 200
    assert pf.tokenization_check(isolated_ms=iso, peak_request_rps=1, g0_isolated_p99_ms=2.0)["status"] == "flag"
    assert pf.tokenization_check(isolated_ms=iso, peak_request_rps=1, g0_isolated_p99_ms=5.5)["status"] == "pass"


def test_sampler_overhead_rule():
    assert pf.sampler_overhead_check({"overhead_core_frac": 0.002})["status"] == "pass"
    assert pf.sampler_overhead_check({"overhead_core_frac": 0.02})["status"] == "fail"
    assert pf.sampler_overhead_check({})["status"] == "fail"


def test_combine():
    assert pf.combine({"status": "pass"}, {"status": "flag"}) == "flag"
    assert pf.combine({"status": "flag"}, {"status": "fail"}) == "fail"


def test_sampler_equivalence():
    assert pf.sampler_equivalence_check([82.0] * 20, [81.5] * 20)["status"] == "pass"     # 0.5 ms
    assert pf.sampler_equivalence_check([85.0] * 20, [82.0] * 20)["status"] == "fail"     # 3 ms and 3.7%
    assert pf.sampler_equivalence_check([301.5] * 20, [300.0] * 20)["status"] == "pass"   # 1.5 ms but 0.5%
    assert pf.sampler_equivalence_check([], [1.0])["status"] == "fail"
