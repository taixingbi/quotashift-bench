"""Per-request cached tokens: null = missing telemetry (never 0); reported-only ratio + coverage."""

import pandas as pd

from quotashift.evaluation.cache_hits import cached_token_summary
from quotashift.serving.openai_backend import cached_tokens_of


def test_cached_tokens_of_null_handling():
    # shapes observed on vLLM 0.17.1 with --enable-prompt-tokens-details (2026-11-21)
    assert cached_tokens_of({"prompt_tokens": 569, "prompt_tokens_details": None}) is None  # cold request
    assert cached_tokens_of({"prompt_tokens": 569, "prompt_tokens_details": {"cached_tokens": 560}}) == 560
    assert cached_tokens_of({"prompt_tokens": 540, "completion_tokens": 4}) is None  # field absent
    assert cached_tokens_of({"prompt_tokens_details": {"cached_tokens": 0}}) == 0  # explicit 0 is kept
    assert cached_tokens_of({"prompt_tokens_details": {"cached_tokens": None}}) is None
    assert cached_tokens_of(None) is None


def _df(rows):
    return pd.DataFrame(rows, columns=["tenant_id", "workload_class", "terminal_status",
                                       "prompt_tokens_reported", "cached_tokens_reported"])


def test_summary_reported_only_with_coverage():
    df = _df([
        ("v1", "victim", "completed", 1000, None),   # cold: missing, excluded from ratio
        ("v1", "victim", "completed", 1000, 992),
        ("v1", "victim", "completed", 1000, 992),
        ("v1", "victim", "timed_out", 1000, 992),     # not completed -> not counted
        ("c1", "competitor", "completed", 500, None),
    ])
    s = cached_token_summary(df)
    v = s["by_tenant"]["v1"]
    assert v["completed"] == 3 and v["reporting"] == 2 and abs(v["coverage"] - 2 / 3) < 1e-9
    assert v["hit_ratio_reported"] == 992 * 2 / 2000  # NOT 1984/3000 (nulls are not zeros)
    c = s["by_class"]["competitor"]
    assert c["coverage"] == 0 and c["hit_ratio_reported"] is None  # nothing reported -> unavailable
    assert s["any_reported"] is True


def test_summary_without_column_is_unavailable():
    df = pd.DataFrame({"tenant_id": ["a"], "workload_class": ["victim"], "terminal_status": ["completed"],
                       "prompt_tokens_reported": [10]})
    s = cached_token_summary(df)
    assert s["by_tenant"]["a"]["coverage"] is None and s["any_reported"] is False


def test_zero_hits_are_observations_token_weighted():
    """Owner's live validation on the patched server (2026-11-21): cold A = 0, cold B = 16 (shared template block)."""
    rows = [("A", "victim", "completed", 1080, c) for c in (0, 1072, 1072)]
    rows += [("B", "competitor", "completed", 931, c) for c in (16, 928, 928)]
    s = cached_token_summary(_df(rows))
    a, b = s["by_tenant"]["A"], s["by_tenant"]["B"]
    assert a["coverage"] == 1.0 and a["reporting"] == 3 and a["zero_hit_reported"] == 1  # 0 counted, not missing
    assert a["hit_ratio_reported"] == 2144 / 3240  # token-weighted
    per_req_mean = (0 + 1072 / 1080 + 1072 / 1080) / 3
    assert abs(a["hit_ratio_reported"] - per_req_mean) < 1e-12  # equal-length prompts: weights coincide
    assert b["hit_ratio_reported"] == 1872 / 2793 and b["zero_hit_reported"] == 0


def test_token_weighting_not_mean_of_ratios():
    df = _df([("t", "victim", "completed", 100, 0), ("t", "victim", "completed", 1000, 1000)])
    r = cached_token_summary(df)["by_tenant"]["t"]["hit_ratio_reported"]
    assert r == 1000 / 1100 and r != 0.5  # mean of per-request ratios would be 0.5


def test_noncompleted_counted_separately_and_excluded():
    df = _df([("t", "victim", "completed", 100, 0), ("t", "victim", "cancelled", 100, None),
              ("t", "victim", "timed_out", 100, 50)])  # a value on a non-completed row is still not used
    t = cached_token_summary(df)["by_tenant"]["t"]
    assert t["completed"] == 1 and t["noncompleted"] == 2 and t["coverage"] == 1.0 and t["hit_ratio_reported"] == 0.0


def test_engine_reconciliation_derives_zero_only_when_exact():
    from quotashift.evaluation.cache_hits import engine_reconciliation

    df = _df([("v", "victim", "completed", 100, None), ("v", "victim", "completed", 100, 80),
              ("c", "competitor", "completed", 200, None)])
    exact = {"prefix_cache_hits_total": 80.0, "attribution_mode": "exact", "unrelated_traffic_suspected": False}
    s = cached_token_summary(df)
    rec = engine_reconciliation(s, df, exact)
    assert rec["residual"] == 0 and rec["nulls_implied_zero"]
    assert s["by_tenant"]["v"]["hit_ratio_reported"] == 0.8  # observation-only value unchanged
    assert s["by_tenant"]["v"]["hit_ratio_all_completed_reconciled"] == 80 / 200
    assert s["by_class"]["competitor"]["hit_ratio_all_completed_reconciled"] == 0.0
    for eng in ({**exact, "prefix_cache_hits_total": 96.0},  # residual 16 -> some null request had hits
                {**exact, "attribution_mode": "bounded"},    # A8-style arms: not exact
                {**exact, "unrelated_traffic_suspected": True}, {}):
        s2 = cached_token_summary(df)
        assert not engine_reconciliation(s2, df, eng)["nulls_implied_zero"]
        assert "hit_ratio_all_completed_reconciled" not in s2["by_tenant"]["v"]



def test_mock_mirrors_patched_target_and_can_emulate_stock():
    from quotashift.config import EngineParams
    from quotashift.serving.mock_server import MockVLLM

    m = MockVLLM(EngineParams())
    assert m.zero_hit_details_endpoints == frozenset({"chat", "completions"})  # target as of 2026-11-21 08:45
    assert m.observe_prefix(["w"] * 32) == 0  # cold: 0 hit tokens (reported as cached_tokens 0 when patched)
    assert m.observe_prefix(["w"] * 32) == 32  # warm repeat: two 16-token blocks
