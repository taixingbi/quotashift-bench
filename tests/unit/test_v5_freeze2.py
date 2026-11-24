"""Protocol v5 Freeze Commit 2: FROZEN_TRACES.json matches its pin, and Freeze Commit 1 artifacts are untouched."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import pin_v5  # noqa: E402

PINS2 = REPO / "experiments" / "v5" / "FROZEN_SHA256_COMMIT2.json"


def test_frozen_traces_match_commit2_pin():
    pins = json.loads(PINS2.read_text())
    for p, h in pins["files"].items():
        assert hashlib.sha256((REPO / p).read_bytes()).hexdigest() == h, p
    assert list(pins["files"]) == ["experiments/v5/FROZEN_TRACES.json"]


def test_commit1_artifacts_unchanged_and_traces_cover_every_scenario():
    assert pin_v5.check() == []
    traces = json.loads((REPO / "experiments" / "v5" / "FROZEN_TRACES.json").read_text())
    assert len(traces["scenarios"]) == 46 and traces["tokenizer"]["process_start_time_seconds"] == 1795268683.89
    assert traces["git_sha"] == json.loads(PINS2.read_text())["freeze_commit_1"]
