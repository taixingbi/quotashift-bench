"""Rev 4 protocol text <-> implementation constants (owner-approved rev 4 is the source of truth; code must match)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import build_x1 as bx  # noqa: E402
import x1_analysis as xa  # noqa: E402
import x1_predictions as xp  # noqa: E402

from quotashift.x1 import preflight as pf  # noqa: E402

DOC = (REPO / "docs" / "PROTOCOL_X1_CROSS_PLATFORM_DRAFT.md").read_text()


def test_status_is_frozen_by_freeze_commit_1():
    assert "**Status:** FROZEN — X1 Freeze Commit 1 (owner approval `x1_freeze1`" in DOC
    assert (REPO / "experiments" / "x1" / "FROZEN_SHA256.json").exists()


def test_cells_seeds_and_n():
    for frag in ("| X-a | D vs S | low | C = 8 | **24** | 8000–8023 |", "| X-b | D vs S | low | C = 32 | 10 | 8000–8009 |",
                 "| X-c | D vs S | low | direct | 10 | 8000–8009 |", "| X-d | A/A-ind | low | C = 8 | **24** | 8000–8023 |",
                 "| X-e | D vs S | high | C = 8 | 10 | 8000–8009 |", "| X-f | A/A-ind | high | C = 8 | 10 | 8000–8009 |"):
        assert frag in DOC, frag
    assert [(b, c, p, cap, n) for b, c, p, cap, n in bx.BLOCKS] == [
        ("Xa", "decode_vs_short", "low", 8, 24), ("Xb", "decode_vs_short", "low", 32, 10),
        ("Xc", "decode_vs_short", "low", None, 10), ("Xd", "aa_ind", "low", 8, 24),
        ("Xe", "decode_vs_short", "high", 8, 10), ("Xf", "aa_ind", "high", 8, 10)]
    assert bx.MAIN_SEED0 == 8000
    assert "Seeds 7000–7002" in DOC and (bx.CAL_A_SEED0, bx.CAL_A_REPS) == (7000, 3)
    assert "**7003–7007**" in DOC and (bx.CAL_B_SEED0, bx.CAL_B_REPS) == (7003, 5)


def test_load_normalisation_targets():
    for frag in ("closest to 0.43", "closest to 0.72", "ρ_ctl ≥ 0.40 with control SLO ≥ 0.95", "6-rate grid"):
        assert frag in DOC, frag
    assert (bx.RHO_LOW, bx.RHO_HIGH, bx.RHO_LOW_MIN, bx.CTL_SLO_MIN) == (0.43, 0.72, 0.40, 0.95)
    assert len(bx.GRID_BASE) == 6


def test_hypotheses_thresholds_and_families():
    assert "**exceeds 1.25**" in DOC and bx.THRESHOLD == 1.25
    assert "[0.9, 1.1] × control" in DOC
    assert math.isclose(math.exp(xa.BACKEND_LO), 0.9) and math.isclose(math.exp(xa.BACKEND_HI), 1.1)
    assert "Holm over 4 platforms" in DOC and "Holm over 8 = 4 × H2 + 4 × H3" in DOC
    assert "≥ 3 of 4 platforms" in DOC
    assert xp.PREDICTED == {"Xa": "low", "Xb": "low", "Xe": "high"}
    assert "(low, C = 8), (low, C = 32) and (high, C = 8)" in DOC


def test_preflight_constants_match_the_text():
    for frag in ("KV < **20,480** tokens", "MemAvailable < **1 GiB**", "p99 > **25 ms**", "ρ > **0.10**",
                 "**10 × peak**", "> **10 ms**", "host CPU ≥ 95% for ≥ 10% of samples",
                 "API server ≥ 85% of a core for ≥ 5% of samples", "within 30 min"):
        assert frag in DOC, frag
    assert pf.KV_MIN_TOKENS == 20480 and pf.RAM_FAIL_BYTES == 2**30 and pf.RAM_FLAG_BYTES == 2 * 2**30
    assert pf.TOK_ISOLATED_P99_FAIL_MS == 25.0 and pf.TOK_UTIL_MAX == 0.10 and pf.TOK_BURST_MULT == 10.0
    assert pf.TOK_BURST_EXCESS_FAIL_MS == 10.0 and pf.TOK_BURST_EXCESS_FLAG_MS == 5.0
    assert (pf.CPU_FAIL_HOST, pf.CPU_FAIL_FRAC, pf.CPU_FLAG_API, pf.CPU_FLAG_API_FRAC) == (0.95, 0.10, 0.85, 0.05)
    assert pf.LOAD_TIMEOUT_S == 1800 and pf.SAMPLER_MAX_CORE_FRAC == 0.01


def test_models_and_revisions():
    for p in bx.PLATFORMS.values():
        assert p["revision"] in DOC and p["model"].split("/")[1] in DOC
