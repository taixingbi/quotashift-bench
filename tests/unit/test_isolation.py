"""Protocol v2 prefix-cache isolation: per-arm nonce properties, budget preservation, v1 unchanged."""

from __future__ import annotations

from pathlib import Path

import pytest

from quotashift.budget import budget_report, summarize_trace
from quotashift.local import paired_traces
from quotashift.scenario import load_scenario
from quotashift.workload.isolation import NONCE_VOCAB, apply_arm_nonce, nonce_words

REPO = Path(__file__).resolve().parents[2]
V2 = sorted((REPO / "experiments" / "v2").glob("*.yaml"))


def _first_block(text: str) -> str:
    return " ".join(text.split(" ")[:16])


def test_vocab_unique():
    assert len(set(NONCE_VOCAB)) == len(NONCE_VOCAB) >= 128


def test_first_word_always_differs_between_arms():
    for seed in range(20):
        for i in range(200):
            rid = f"victim_a-benign-{seed}-{i:06d}"
            a = nonce_words(rid, arm="attack", scenario_id="s", seed=seed)
            c = nonce_words(rid, arm="control", scenario_id="s", seed=seed)
            assert a[0] != c[0]


@pytest.mark.parametrize("path", V2, ids=lambda p: p.stem)
def test_v2_nonce_preserves_planned_budgets_exactly(path):
    sc = load_scenario(path)
    for seed in (sc.seed, sc.seed + 1):
        atk, ctl, _ = paired_traces(sc, seed)
        raw_atk = sc.build_trace(seed)
        raw_ctl, _ = sc.control_trace(seed)
        for new, old in ((atk, raw_atk), (ctl, raw_ctl)):
            assert [i.request.request_id for i in new] == [i.request.request_id for i in old]
            for n, o in zip(new, old, strict=True):
                assert n.request.input_token_count == o.request.input_token_count
                assert len(n.request.prompt_text.split(" ")) == len(o.request.prompt_text.split(" "))
                assert n.request.max_output_tokens == o.request.max_output_tokens
                assert n.request.arrival_time_s == o.request.arrival_time_s
        # matched-budget report identical before and after nonces (revalidated)
        assert (budget_report(summarize_trace(atk), summarize_trace(ctl), sc.comparison)
                == budget_report(summarize_trace(raw_atk), summarize_trace(raw_ctl), sc.comparison))


@pytest.mark.parametrize("path", V2, ids=lambda p: p.stem)
def test_v2_no_shared_first_block_within_or_across_arms(path):
    sc = load_scenario(path)
    atk, ctl, _ = paired_traces(sc, sc.seed)
    blocks_a = [_first_block(i.request.prompt_text) for i in atk]
    blocks_c = [_first_block(i.request.prompt_text) for i in ctl]
    assert len(set(blocks_a)) == len(blocks_a)
    assert len(set(blocks_c)) == len(blocks_c)
    assert not set(blocks_a) & set(blocks_c)
    # identical victim work otherwise: only the 4 nonce words differ between arms
    va = {i.request.request_id: i.request.prompt_text for i in atk if i.request.workload_class == "victim"}
    vc = {i.request.request_id: i.request.prompt_text for i in ctl if i.request.workload_class == "victim"}
    assert va.keys() == vc.keys()
    for rid in va:
        assert va[rid].split(" ")[4:] == vc[rid].split(" ")[4:]


def test_v1_historical_traces_untouched_and_carry_over_reproducible():
    sc = load_scenario(REPO / "experiments" / "a2_prefill_heavy.yaml")
    assert sc.protocol_version == 1
    atk, ctl, _ = paired_traces(sc, sc.seed)
    assert [i.request for i in atk] == [i.request for i in sc.build_trace(sc.seed)]
    va = {i.request.request_id: i.request.prompt_text for i in atk if i.request.workload_class == "victim"}
    vc = {i.request.request_id: i.request.prompt_text for i in ctl if i.request.workload_class == "victim"}
    assert va == vc  # the historical byte-identical victim prompts (root cause of the carry-over)


def test_salt_changes_nonce_and_token_id_mode():
    a1 = nonce_words("r", arm="attack", scenario_id="s", seed=1, salt="rep1")
    a2 = nonce_words("r", arm="attack", scenario_id="s", seed=1, salt="rep2")
    assert a1 != a2
    from quotashift.schema import OracleInfo, Request, SLOType, TraceItem
    req = Request(request_id="r", tenant_id="t", arrival_time_s=0, prompt_token_ids=tuple(range(10)), input_token_count=10,
                  max_output_tokens=4, workload_class="victim", slo_type=SLOType.INTERACTIVE, ttft_deadline_ms=1, seed=1,
                  trace_id="x")
    it = TraceItem(request=req, oracle=OracleInfo(request_id="r", realized_output_tokens=4))
    a = apply_arm_nonce([it], arm="attack", scenario_id="s", seed=1)[0].request.prompt_token_ids
    c = apply_arm_nonce([it], arm="control", scenario_id="s", seed=1)[0].request.prompt_token_ids
    assert len(a) == len(c) == 10 and a[0] != c[0] and a[4:] == c[4:] == tuple(range(4, 10))
