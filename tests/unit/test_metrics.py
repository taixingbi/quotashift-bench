import math

import numpy as np
import pandas as pd
import pytest

from risksched.evaluation.metrics import (
    derive_request_metrics,
    histogram_quantile,
    jain_index,
    percentile,
    summarize,
)


def row(rid, tenant="A", status="completed", t_off=0.0, t_sent=0.0, t_ft=0.1, t_end=1.0, out=10,
        ttft_dl=500.0, tpot=200.0, e2e=None, arrival=1.0, w=1.0):
    return dict(request_id=rid, tenant_id=tenant, terminal_status=status, t_offered=t_off, t_sent=t_sent,
                t_first_token=t_ft, t_terminal=t_end, output_tokens=out, ttft_deadline_ms=ttft_dl,
                tpot_target_ms=tpot, e2e_deadline_ms=e2e, trace_arrival_s=arrival, priority_weight=w,
                input_token_count=5, max_output_tokens=100)


def test_percentile_linear():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([], 95) is None
    assert percentile([None, float("nan"), 3.0], 50) == 3.0
    assert percentile(range(101), 99) == pytest.approx(99.0)


def test_ttft_includes_gateway_queue_and_tpot_definition():
    df = pd.DataFrame([row("r", t_off=0.0, t_sent=0.3, t_ft=0.5, t_end=1.4, out=10)])
    d = derive_request_metrics(df).iloc[0]
    assert d.gateway_queue_ms == pytest.approx(300)
    assert d.ttft_ms == pytest.approx(500)
    assert d.backend_ttft_ms == pytest.approx(200)
    assert d.tpot_ms == pytest.approx(900 / 9)
    assert d.e2e_ms == pytest.approx(1400)


def test_tpot_undefined_for_single_token():
    d = derive_request_metrics(pd.DataFrame([row("r", out=1)])).iloc[0]
    assert math.isnan(d.tpot_ms)
    assert d.slo_met  # TPOT bound vacuous for 1-token outputs


def test_slo_logic():
    df = pd.DataFrame([
        row("ok"),
        row("ttft_miss", t_ft=0.6),
        row("tpot_miss", t_end=5.0),
        row("e2e_miss", e2e=500.0),
        row("rej", status="rejected", t_ft=None, t_sent=None, t_end=0.0, out=None),
    ])
    d = derive_request_metrics(df).set_index("request_id")
    assert d.slo_met.to_dict() == {"ok": True, "ttft_miss": False, "tpot_miss": False, "e2e_miss": False, "rej": False}


def test_offered_denominator_counts_failures():
    df = pd.DataFrame([row("a"), row("b", status="rejected", t_ft=None, t_sent=None, out=None),
                       row("c", status="timed_out", t_ft=None, out=None), row("d", status="backend_error", t_ft=None, out=None),
                       row("e", status="cancelled", t_ft=None, out=None)])
    s = summarize(df, window_s=10.0)
    assert s["offered"] == 5 and s["slo_met"] == 1
    assert s["offered_success_fraction"] == pytest.approx(0.2)
    assert s["slo_goodput_rps"] == pytest.approx(0.1)
    assert s["accounting_conserved"]


def test_non_terminal_breaks_conservation():
    df = pd.DataFrame([row("a"), row("b", status=None)])
    assert not summarize(df, window_s=10)["accounting_conserved"]


def test_warmup_exclusion_reported():
    df = pd.DataFrame([row("a", arrival=0.5), row("b", arrival=2.0), row("c", arrival=20.0)])
    s = summarize(df, window_s=10.0, warmup_s=1.0)
    assert s["offered"] == 1 and s["excluded_outside_window"] == 2


def test_jain_and_worst_tenant():
    assert jain_index([1, 1, 1]) == pytest.approx(1.0)
    assert jain_index([1, 0, 0]) == pytest.approx(1 / 3)
    assert jain_index([]) is None
    df = pd.DataFrame([row("a1", "A"), row("a2", "A"), row("b1", "B", t_ft=0.9), row("b2", "B")])
    s = summarize(df, window_s=10)
    assert s["per_tenant"]["B"]["slo_attainment"] == 0.5
    assert s["worst_tenant_slo_attainment"] == 0.5
    assert s["jain_slo_attainment"] == pytest.approx((1.5**2) / (2 * (1 + 0.25)))


def test_histogram_quantile_matches_prometheus_semantics():
    b = [(0.1, 10), (0.5, 30), (1.0, 40), (float("inf"), 40)]
    assert histogram_quantile(0.5, b) == pytest.approx(0.1 + 0.4 * (20 - 10) / 20)
    assert histogram_quantile(0.25, b) == pytest.approx(0.1 * 10 / 10)
    assert histogram_quantile(0.99, [(1.0, 10), (float("inf"), 20)]) == 1.0  # lands in +Inf => highest finite
    assert histogram_quantile(0.5, []) is None
    assert histogram_quantile(0.5, [(1.0, 0), (float("inf"), 0)]) is None


def test_histogram_quantile_against_samples():
    rng = np.random.default_rng(0)
    x = rng.exponential(0.3, 20000)
    les = [0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, float("inf")]
    b = [(le, float((x <= le).sum())) for le in les]
    assert histogram_quantile(0.5, b) == pytest.approx(np.median(x), rel=0.1)
