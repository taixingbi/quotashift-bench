"""Operational driver helpers (ADR-X1-G0M0-P1-RECOVERY)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import x1_preflight as xp  # noqa: E402

from quotashift.x1 import preflight as pf  # noqa: E402


def test_overhead_prefers_the_final_summary():
    s = [{"t": 1.0}, {"overhead": {"overhead_core_frac": 0.002}}, {"summary": {"overhead_core_frac": 0.003}}]
    assert xp.overhead(s)["overhead_core_frac"] == 0.003
    assert pf.sampler_overhead_check(xp.overhead(s))["status"] == "pass"


def test_overhead_daemon_line_and_missing():
    assert xp.overhead([{"overhead": {"overhead_core_frac": 0.004}}])["overhead_core_frac"] == 0.004
    assert pf.sampler_overhead_check(xp.overhead([{"t": 1.0}]))["status"] == "fail"


def test_phase1_sampler_covers_a_periodic_report():
    assert xp.SAMPLER_PHASE1_S >= 60
