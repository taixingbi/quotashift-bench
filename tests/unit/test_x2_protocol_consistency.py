"""X2 rev 2 protocol / instrumentation spec text <-> implementation constants, and separation from X1/v5."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import build_x2 as bx  # noqa: E402
import pin_x2  # noqa: E402
import x2_analysis as xa  # noqa: E402

from quotashift.x2 import qualification as q  # noqa: E402
from quotashift.x2 import snapshot as sn  # noqa: E402

DOC = (REPO / "docs" / "PROTOCOL_X2_DRAFT.md").read_text()
SPEC = (REPO / "docs" / "X2_INSTRUMENTATION_SPEC.md").read_text()


def test_status_is_candidate_not_frozen():
    assert "rev 2, FREEZE CANDIDATE" in DOC and "Not frozen" in DOC
    assert not (REPO / "experiments" / "x2" / "FROZEN_SHA256.json").exists()


def test_platforms_and_revisions():
    for p in bx.PLATFORMS.values():
        assert p["revision"] in DOC
    assert set(bx.PLATFORMS) == {"g0m0", "g0m1", "g1m0", "g1m1"} and "full 2 × 2" in DOC


def test_hypotheses_blocks_and_threshold():
    assert "**exceeds 1.25**" in DOC and bx.THRESHOLD == 1.25
    assert [(b, c, cap, n) for b, c, cap, n, _ in bx.BLOCKS] == [
        ("X2a", "decode_vs_short", 8, 24), ("X2b", "aa_ind", 8, 24), ("X2c", "decode_vs_short", None, 10),
        ("X2d", "decode_vs_short", 32, 10)]
    for frag in ("X2a, 24", "X2b A/A-ind, 24", "X2c, 10", "X2d, 10", "Holm over 4 platforms", "Holm over 8 = 4 × H2 + 4 × H3",
                 "REPLICATES** iff ≥ 3 of 4 platforms replicate"):
        assert frag in DOC, frag
    assert xa.PLATFORMS == tuple(bx.PLATFORMS)


def test_calibration_and_seeds():
    for frag in ("0.30, 0.40, 0.50, 0.60, 0.75 and 0.90", "closest to 0.43", "ρ_ctl ≥ 0.40 with control SLO ≥ 0.95",
                 "22000–22002", "23000–23023", "20990", "21000–21039 / 21900–21902", "21100–21139"):
        assert frag in DOC, frag
    assert bx.RHO_TARGETS == (0.30, 0.40, 0.50, 0.60, 0.75, 0.90) and (bx.RHO_LOW, bx.RHO_LOW_MIN, bx.CTL_SLO_MIN) == (0.43, 0.40, 0.95)
    assert (bx.CAL_A_SEED0, bx.CAL_A_REPS, bx.MAIN_SEED0, bx.SMOKE_SEED) == (22000, 3, 23000, 20990)
    assert q.prompt_seeds()[0] == 21000 and q.prompt_seeds()[-1] == 21039 and q.WARMUP_SEEDS == (21900, 21901, 21902)


def test_qualification_design_text():
    for frag in ("**K = 64**", "**M = 40**", "**95% t-interval**", "T1s", "max(1 ms, 2% × the N median)", "16 pairs"):
        assert frag in DOC, frag
    for frag in ("K = **64**", "**M = 40**", "**95%** t-interval", "15 s", "0.5 s", "K0 = 16"):
        assert frag in SPEC, frag
    assert (q.K_PAIRS, q.M_PER_SEGMENT, q.K0_PAIRS, q.CI_LEVEL, q.TEST) == (64, 40, 16, 0.95, "T1s")
    assert sn.GUARD_S == q.GUARD_S == 15.0


def test_flag_thresholds_text():
    for frag in ("Host mean busy ≥ 80%", "API server mean ≥ 0.85 core", "MemAvailable < 2 GiB", "< 1 GiB"):
        assert frag in SPEC, frag
    assert (sn.HOST_MEAN_FLAG, sn.API_MEAN_FLAG, sn.RAM_FLAG_BYTES, sn.RAM_FAIL_BYTES) == (0.80, 0.85, 2 * 2**30, 2**30)


def test_x2_never_touches_x1_or_v5_records():
    for f in pin_x2.FILES:
        assert not f.startswith(("experiments/x1/", "experiments/v5/", "experiments/v4"))
        assert f not in json.loads((REPO / "experiments/x1/FROZEN_SHA256.json").read_text())["files"]
        assert f not in json.loads((REPO / "experiments/v5/FROZEN_SHA256.json").read_text())["files"]
    assert pin_x2.x1_problems() == [] and pin_x2.v5_dependency_problems() == []
