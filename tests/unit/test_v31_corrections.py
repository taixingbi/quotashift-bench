"""Protocol v3.1 / ADR-Q16-Q17 corrections: tokenizer sizing, metric labels, TTFT definitions, validity gates."""

from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from quotashift.evaluation.attack_effect import (
    METRIC_INFO,
    ReportLabelMismatch,
    RunMetrics,
    analyze_pair,
    check_report_labels,
    run_metrics,
    secondary_endpoints,
    write_report,
)
from quotashift.evaluation.validity import apply_gates, validity_gates
from quotashift.schema import OracleInfo, Request, TraceItem
from quotashift.workload.isolation import NONCE_VOCAB
from quotashift.workload.tokenize import (
    TokenizedContextInvalid,
    WhitespaceTokenizer,
    calibrate_trace,
    verify_trace,
)


def _item(rid: str, n_words: int, planned: int, max_out: int = 16, cls: str = "competitor") -> TraceItem:
    text = " ".join(["[req", f"{rid}]", *(["the"] * (n_words - 2))])
    r = Request(request_id=rid, tenant_id="comp", arrival_time_s=0.0, prompt_text=text, input_token_count=planned,
                max_output_tokens=max_out, workload_class=cls, slo_type="interactive", ttft_deadline_ms=2000.0,
                e2e_deadline_ms=30000.0, priority_weight=1.0, seed=1, trace_id="t")
    return TraceItem(request=r, oracle=OracleInfo(request_id=rid, realized_output_tokens=1))


def tag_counter(texts):  # like Qwen: the "[req <id>]" tag is 16 tokens, every filler word 1 token
    return [len(t.split()) - 2 + 16 for t in texts]


def test_calibration_hits_planned_count_exactly_and_keeps_budget():
    items = [_item(f"r{i}", 40 + i, planned=60 + i) for i in range(5)]
    out, rep = calibrate_trace(items, tag_counter)
    assert tag_counter([it.request.prompt_text for it in out]) == [60 + i for i in range(5)]
    assert [it.request.input_token_count for it in out] == [60 + i for i in range(5)]  # budget unchanged
    assert rep["edited"] == 5
    assert all(w in NONCE_VOCAB or w.startswith("[req") or w.endswith("]")
               for it in out for w in it.request.prompt_text.split())


def test_calibration_is_keyed_on_text_so_identical_prompts_stay_identical():
    a, b = _item("x", 10, planned=40), _item("x", 10, planned=40)
    b = TraceItem(request=b.request.model_copy(update={"request_id": "x-retry"}), oracle=b.oracle)
    out, _ = calibrate_trace([a, b], tag_counter)
    assert out[0].request.prompt_text == out[1].request.prompt_text


def test_calibration_fails_closed_when_tag_alone_exceeds_plan():
    with pytest.raises(TokenizedContextInvalid):
        calibrate_trace([_item("r", 10, planned=8)], tag_counter)


def test_verify_trace_fails_on_context_overflow_and_on_mismatch():
    ok = [_item("a", 100, planned=100, max_out=256)]
    assert verify_trace(ok, WhitespaceTokenizer(), max_model_len=4096, exact=True)["ok"]
    with pytest.raises(TokenizedContextInvalid, match="exceed"):
        verify_trace([_item("b", 3900, planned=3900, max_out=256)], WhitespaceTokenizer(), max_model_len=4096, exact=False)
    with pytest.raises(TokenizedContextInvalid, match="different length"):
        verify_trace([_item("c", 100, planned=90)], WhitespaceTokenizer(), max_model_len=4096, exact=True)


def test_historical_long_context_trace_overflows_on_a_real_token_ratio(repo):
    """The audited defect: whitespace-planned long-context prompts (~2.1 real tokens/word) exceed 4096."""
    from quotashift.local import paired_traces
    from quotashift.scenario import load_scenario

    sc = load_scenario(repo / "experiments/v3/a9_tok_longctx.yaml")
    atk, _, _ = paired_traces(sc, 42)
    qwen_like = lambda ts: [int(round(2.03 * len(t.split()))) for t in ts]  # noqa: E731  measured ratio
    with pytest.raises(TokenizedContextInvalid):
        verify_trace(atk, qwen_like, max_model_len=4096, exact=False)


def test_amended_long_context_scenarios_fit_and_match_offline(repo):
    from quotashift.local import paired_traces
    from quotashift.scenario import load_scenario

    for f in ("a9_tok_longctx_v31", "a9_rate_longctx_v31"):
        sc = load_scenario(repo / f"experiments/v3_1/{f}.yaml")
        assert sc.prompt_token_unit == "tokenizer"
        atk, ctl, _ = paired_traces(sc, sc.seed)
        for tr in (atk, ctl):
            rep = verify_trace(tr, WhitespaceTokenizer(), max_model_len=sc.model_max_len, exact=True)
            assert rep["ok"] and rep["max_context_tokens"] <= sc.model_max_len
            filler = [w for it in tr for w in it.request.prompt_text.split()[6:]]
            assert set(filler) <= set(NONCE_VOCAB)


def _rm(arm, seed, *, energy=1000.0, auth=10000, ttft=100.0, **kw) -> RunMetrics:
    base = RunMetrics(run_dir=f"/x/{arm}/{seed}", scenario="s", arm=arm, seed=seed, synthetic_backend=True,
                      victim_completed=50, victim_timed_out=0, victim_ttft_p50_ms=ttft, victim_ttft_p95_ms=ttft,
                      victim_e2e_p50_ms=ttft, victim_e2e_p95_ms=ttft, competitor_requests=20, competitor_tokens=1000,
                      authorized_tokens=auth, gpu_dynamic_energy_j=energy, victim_offered=50, victim_admitted=50,
                      victim_sent=50, victim_rejected=0, victim_backend_error=0, victim_cancelled=0,
                      victim_slo_success_offered=1.0, victim_censored_fraction=0.0, competitor_offered=20,
                      competitor_admitted=20, competitor_sent=20, competitor_backend_error=0, competitor_http_400=0,
                      competitor_cancelled=0, competitor_timed_out=0, requests_offered=70, requests_sent=70,
                      backend_error_total=0, http_400_total=0, max_context_tokens_completed=1000.0,
                      token_count_mismatch_completed=0, token_count_reported_completed=70, requests_completed=70)
    return replace(base, **kw)


def test_energy_report_is_labelled_by_metric_not_as_victim_slowdown(tmp_path):
    m = "gpu_energy_per_1k_authorized_tokens"
    attack = [_rm("attack", s, energy=500.0) for s in range(5)]
    control = [_rm("control", s, energy=1000.0) for s in range(5)]
    a = analyze_pair(attack, control, metric=m, threshold=1.25, direction="two_sided")
    assert a["metric_label"] == "GPU Dynamic Energy per 1,000 Authorized Tokens"
    assert a["per_seed"][0]["attack_value"] == pytest.approx(50.0)  # J per 1k authorized tokens
    pairs = {"control_label": "rate_matched_short", "seeds": list(range(5)),
             "attack": {s: f"/a/{s}" for s in range(5)}, "control": {s: f"/c/{s}" for s in range(5)},
             "budgets": {s: {"matched": True} for s in range(5)}}
    sec = secondary_endpoints(attack, control, threshold=1.25)
    write_report("s", pairs, a, attack, control, tmp_path, commands=["c"], secondary=sec)
    md = (tmp_path / "summary.md").read_text()
    assert "GPU Dynamic Energy per 1,000 Authorized Tokens" in md and "J per 1,000 authorized tokens" in md
    low = md.lower()
    assert "victim slowdown" not in low and "attack ms" not in low and "(ms)" not in low.split("victim request")[0]
    assert "not a victim-performance effect" in md
    man = json.loads((tmp_path / "manifest.json").read_text())
    assert man["metric_unit"] == "J per 1,000 authorized tokens"
    assert (tmp_path / "figure_ratio.png").exists() and not (tmp_path / "figure_victim_latency.png").exists()


def test_label_check_fails_closed():
    with pytest.raises(ReportLabelMismatch):
        check_report_labels("| seed | attack ms | control ms | GPU Dynamic Energy per 1,000 Authorized Tokens",
                            "gpu_energy_per_1k_authorized_tokens")
    with pytest.raises(ReportLabelMismatch):
        check_report_labels("nothing", "user_ttft_p95")
    assert set(METRIC_INFO) >= {"ttft_p95", "user_ttft_p95", "backend_ttft_p95", "victim_slo_success_offered"}


def _write_run(tmp_path, rows):
    d = tmp_path / "run"
    d.mkdir()
    pd.DataFrame(rows).to_parquet(d / "requests.parquet")
    (d / "metrics_summary.json").write_text(json.dumps({"warmup_s": 0.0, "engine_counters": {}, "cost_accounting": {}}))
    return d


def _row(i, cls, status, off, sent, ft, end, detail=None):
    return {"request_id": f"r{i}", "tenant_id": "v00" if cls == "victim" else "comp", "workload_class": cls,
            "trace_arrival_s": float(i), "t_offered": off, "t_accepted": off, "t_sent": sent, "t_first_token": ft,
            "t_terminal": end, "terminal_status": status, "terminal_detail": detail, "input_token_count": 10,
            "max_output_tokens": 8, "output_tokens": 4 if status == "completed" else 0,
            "prompt_tokens_reported": 10.0 if status == "completed" else np.nan, "cached_tokens_reported": np.nan,
            "ttft_deadline_ms": 2000.0, "tpot_target_ms": np.nan, "e2e_deadline_ms": 30000.0}


def test_run_metrics_both_ttft_definitions_outcomes_and_slo(tmp_path):
    rows = [_row(i, "victim", "completed", 0.0, 1.0, 1.1, 1.2) for i in range(4)]  # 1 s gateway queue each
    rows.append(_row(4, "victim", "timed_out", 0.0, np.nan, np.nan, 60.0, "gateway_queue_timeout"))
    rows.append(_row(5, "competitor", "backend_error", 0.0, 0.0, np.nan, 0.01, "http_400:{context}"))
    rows.append(_row(6, "competitor", "completed", 0.0, 0.0, 0.05, 0.1))
    m = run_metrics(_write_run(tmp_path, rows), "s", "attack", 1)
    assert m.victim_ttft_p95_ms == pytest.approx(100.0)            # historical key = backend TTFT
    assert m.victim_backend_ttft_p95_ms == pytest.approx(100.0)
    assert m.victim_user_ttft_p95_ms == pytest.approx(1100.0)      # includes the 1 s gateway queue
    assert m.victim_gateway_queue_p95_ms == pytest.approx(1000.0)
    assert (m.victim_offered, m.victim_completed, m.victim_timed_out, m.victim_rejected) == (5, 4, 1, 0)
    assert m.victim_slo_success_offered == pytest.approx(4 / 5)    # the timeout counts against the arm
    assert m.victim_censored_fraction == pytest.approx(1 / 5)
    assert (m.competitor_http_400, m.http_400_total, m.backend_error_total) == (1, 1, 1)
    assert m.token_count_mismatch_completed == 0


def test_gates_invalidate_a_block_whose_competitor_was_rejected():
    attack = [_rm("attack", s, competitor_requests=1, competitor_backend_error=19, competitor_http_400=19,
                  backend_error_total=19, http_400_total=19) for s in range(5)]
    control = [_rm("control", s) for s in range(5)]
    a = analyze_pair(attack, control, metric="gpu_energy_per_1k_authorized_tokens", threshold=1.25, direction="two_sided")
    v = validity_gates(attack, control, a, max_model_len=4096, synthetic=True)
    failed = {c["name"] for c in v["checks"] if not c["passed"]}
    assert not v["passed"] and {"http_400_rate", "backend_error_rate", "competitor_completion"} <= failed
    g = apply_gates(a, v)
    assert g["classification"] == "invalid" and g["classification_unvalidated"] == a["classification"]


def test_gates_pass_clean_and_censoring_fails_only_latency_primary():
    attack = [_rm("attack", s, victim_censored_fraction=0.2) for s in range(5)]
    control = [_rm("control", s) for s in range(5)]
    for metric, expect in (("gpu_energy_per_1k_authorized_tokens", True), ("user_ttft_p95", False)):
        a = analyze_pair(attack, control, metric=metric, threshold=1.25, direction="two_sided")
        v = validity_gates(attack, control, a, max_model_len=4096, synthetic=True)
        assert v["passed"] is expect
    clean = [_rm("attack", s) for s in range(5)]
    a = analyze_pair(clean, control, metric="ttft_p95", threshold=1.25)
    assert validity_gates(clean, control, a, max_model_len=4096, synthetic=True)["passed"]


def test_gates_require_provenance_and_tokenization_on_live_runs():
    attack = [_rm("attack", s, synthetic_backend=False) for s in range(5)]
    control = [_rm("control", s, synthetic_backend=False) for s in range(5)]
    a = analyze_pair(attack, control, metric="ttft_p95", threshold=1.25)
    v = validity_gates(attack, control, a, max_model_len=4096, synthetic=False)
    assert not v["passed"]
    dirty = {"git_sha": ["abc"], "git_dirty": ["True"], "server_start": ["1.0"], "vllm_version": ['{"v": 1}'],
             "model_revision_status": "server reports None", "missing": []}
    tok = {"per_seed": {0: {"attack": {"ok": True}, "control": {"ok": True}}}}
    v = validity_gates(attack, control, a, max_model_len=4096, provenance=dirty, tokenization=tok)
    assert [c["detail"] for c in v["checks"] if c["name"] == "provenance"][0].startswith("dirty")
    clean = {**dirty, "git_dirty": ["False"]}
    assert validity_gates(attack, control, a, max_model_len=4096, provenance=clean, tokenization=tok)["passed"]
