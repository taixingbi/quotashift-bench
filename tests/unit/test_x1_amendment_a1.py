"""X1 Amendment A1 (candidate): paired-segment TOST for sampler on/off equivalence. Not frozen; not wired in."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quotashift.x1 import preflight as pf
from quotashift.x1 import sampler_equivalence_a1 as a1

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(("p", "df", "ref"), [(0.95, 23, 1.713872), (0.975, 23, 2.068658), (0.95, 9, 1.833113),
                                              (0.975, 39, 2.022691), (0.95, 39, 1.684875), (0.05, 7, -1.894579)])
def test_t_quantiles_match_tables(p, df, ref):
    assert a1.t_ppf(p, df) == pytest.approx(ref, abs=1e-5)


def test_tolerance_and_alpha_are_the_rev4_values():
    assert (a1.DELTA_ABS_MS, a1.DELTA_REL) == (pf.SAMPLER_EQ_ABS_MS, pf.SAMPLER_EQ_REL) == (1.0, 0.02)
    assert a1.ALPHA == 0.05 and (a1.K_PAIRS, a1.M_PER_SEGMENT, a1.WARMUP) == (24, 80, 3)
    assert len(a1.PROMPT_SEEDS) == a1.M_PER_SEGMENT and not set(a1.WARMUP_SEEDS) & set(a1.PROMPT_SEEDS)


def test_order_is_balanced_and_cancels_linear_drift():
    o = a1.segment_order()
    assert len(o) == 2 * a1.K_PAIRS
    first = [arm for i, (k, arm) in enumerate(o) if i % 2 == 0]
    assert first.count("on") == first.count("off") == a1.K_PAIRS // 2
    pos = {arm: sum(i for i, (_, a) in enumerate(o) if a == arm) for arm in ("on", "off")}
    assert pos["on"] == pos["off"]                       # equal mean position -> a linear drift cancels in the mean


def segs(on_shift: float, k: int = a1.K_PAIRS, m: int = a1.M_PER_SEGMENT, base: float = 58.0, jitter: float = 0.3):
    out = []
    for j in range(k):
        w = jitter * ((j * 7) % 5 - 2) / 2
        for arm, sh in (("off", 0.0), ("on", on_shift + w)):
            out.append({"pair": j, "arm": arm, "ttft_ms": [base + sh + 0.01 * i for i in range(m)],
                        "reset_verified": True, "sampler_state_ok": True})
    return out


def test_pass_when_clearly_equivalent_and_fail_beyond_delta():
    r = a1.equivalence_a1(segs(0.0))
    assert r["status"] == "pass" and r["delta_ms"] == pytest.approx(1.16, abs=0.01)
    assert a1.equivalence_a1(segs(1.5))["status"] == "fail"
    assert a1.equivalence_a1(segs(-1.5))["status"] == "fail"


def test_one_ms_floor_applies_on_fast_platforms():
    assert a1.equivalence_a1(segs(0.0, base=20.0))["delta_ms"] == 1.0


def test_incomplete_or_unverified_segments_fail_closed():
    s = segs(0.0)
    assert a1.equivalence_a1(s[:-1])["status"] == "fail"
    s2 = segs(0.0)
    s2[3]["reset_verified"] = False
    assert "reset not verified" in " ".join(a1.equivalence_a1(s2)["reasons"])
    s3 = segs(0.0)
    s3[0]["ttft_ms"] = s3[0]["ttft_ms"][:-1]
    assert a1.equivalence_a1(s3)["status"] == "fail"


def test_failed_attempts_are_not_reclassified():
    """Attempts 1 and 2 were judged by the frozen rev 4 rule and stay FAIL; A1 cannot evaluate their 20 + 20 design."""
    for f, diff in (("HOST_VERIFICATION.attempt1.json", -9.342750010546297), ("HOST_VERIFICATION.json", 1.2319580418989062)):
        rec = json.loads((REPO / "experiments" / "x1" / "g0m0" / f).read_text())["preflight"]["phase1"]
        se = rec["checks"]["sampler_equivalence"]
        assert rec["status"] == "fail" and se["status"] == "fail" and se["diff_ms"] == pytest.approx(diff)
    legacy = [{"pair": 0, "arm": a, "ttft_ms": [58.0] * 20, "reset_verified": True, "sampler_state_ok": True}
              for a in ("off", "on")]
    assert a1.equivalence_a1(legacy)["status"] == "fail"
