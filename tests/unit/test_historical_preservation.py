"""Historical A1–A5 definitions and results must not change (docs/HISTORICAL_ARCHIVE.md)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from quotashift.cli import main
from quotashift.scenario import load_scenario

REPO = Path(__file__).resolve().parents[2]
FIX = REPO / "tests" / "fixtures" / "historical_results.sha256"

# schedule_sha256 values published in docs/RESULTS_selfhost.md for the historical runs
HISTORICAL_SCHEDULES = {
    "a1_burst_arrivals.yaml": "a0f2380a189fecd7d9256d4ff37280b14ccc4f518a0535740be369a344736798",
    "a2_prefill_heavy.yaml": "2f84df2ce943b2bc7aa6335bb7f11caab88d7ff23fdaa67650eaf35a6c848b5a",
    "a3_decode_heavy.yaml": "9c2645961cf004bfcc63ee810f6bc86c27ff37285fb51645617d5467025c9ad4",
    "a4_mixed_shapes.yaml": "0d9bb522873974baeb456a93307b32bef764a277055c398e69ce08b1d470d8ad",
    "stateful_sequences.yaml": "d5f2ab6f07799a4cc42a2057955cecbf98931f49c6d344da8738c0fd3534f9e4",
}


@pytest.mark.parametrize("fn,sha", HISTORICAL_SCHEDULES.items())
def test_historical_schedule_hashes_unchanged(fn, sha):
    sc = load_scenario(REPO / "experiments" / fn)
    assert sc.protocol_version == 1 and sc.gateway is None
    assert sc.schedule_hash() == sha


def test_historical_thresholds_unchanged():
    for fn in HISTORICAL_SCHEDULES:
        c = load_scenario(REPO / "experiments" / fn).comparison
        assert c.preregistered_threshold == 1.5 and c.degradation_metric == "ttft_p95" and c.budget_tolerance == 0.05


def test_historical_result_files_unchanged():
    if not (REPO / "results").exists() or not any((REPO / "results").iterdir()):
        pytest.skip("historical results not present locally (restore from the archive)")
    bad, missing = [], 0
    for line in FIX.read_text().splitlines():
        digest, rel = line.split("  ", 1)
        p = REPO / rel
        if not p.exists():
            missing += 1
            continue
        if hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            bad.append(rel)
    assert not bad, f"historical files modified: {bad[:5]}"
    assert missing == 0, f"{missing} historical files missing (restore from docs/HISTORICAL_ARCHIVE.md)"


def test_experiment_refuses_to_overwrite_existing_report(tmp_path, capsys):
    out = tmp_path / "rep"
    out.mkdir()
    (out / "manifest.json").write_text("{}")
    rc = main(["experiment", str(REPO / "experiments" / "a1_burst_arrivals.yaml"), "--reps", "1", "--mock",
               "--out", str(out), "--results-root", str(tmp_path / "res")])
    assert rc == 3 and "refusing to overwrite" in capsys.readouterr().err
    assert (out / "manifest.json").read_text() == "{}"
