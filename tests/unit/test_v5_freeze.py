"""Protocol v5 Freeze Commit 1: every frozen artifact matches its SHA-256 pin; no frozen file is added or missing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import pin_v5  # noqa: E402


def test_all_frozen_artifacts_match_their_pins():
    assert pin_v5.check() == []


def test_pins_cover_protocol_configs_predictions_and_host_record():
    pins = json.loads(pin_v5.MANIFEST.read_text())["files"]
    for must in ("docs/PROTOCOL_V5.md", "experiments/v5/HOST_VERIFICATION.json", "experiments/v5/FROZEN_SCHEDULE.json",
                 "experiments/v5/FCFS_PREDICTIONS.json", "scripts/v5_analysis.py"):
        assert must in pins
    assert sum(p.endswith(".yaml") for p in pins) == 46
    assert "experiments/v5/FROZEN_TRACES.json" not in pins   # added by Freeze Commit 2


def test_protocol_is_marked_frozen_for_the_live_driver():
    assert "**Status:** FROZEN" in (REPO / "docs" / "PROTOCOL_V5.md").read_text()
    assert not (REPO / "docs" / "PROTOCOL_V5_DRAFT.md").exists()
