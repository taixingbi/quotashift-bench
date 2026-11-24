"""Protocol v5 stage driver (scripts/v5_stage.py, wrapped by scripts/run_v5.sh): ordering, stop and rerun rules,
server identity during execution, live refusals. Mock / injected runners only — nothing is sent to a GPU."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import v5_stage as vs  # noqa: E402


def fake_runner(fail: set[str] | None = None, start: str = "1.0", wall_s: float = 1.0):
    calls: list[str] = []

    def run(src: Path, *, mode, report, results_root, target=None):  # noqa: ANN001, ARG001
        calls.append(report.name)
        bad = report.name in (fail or set())
        return {"file": str(src), "report": str(report), "rc": 5 if bad else 0, "wall_s": wall_s,
                "failed_gates": ["arrival_coverage"] if bad else [], "server_start": [start],
                "status": "failed" if bad else "passed", "reason": "rc 5" if bad else None}
    run.calls = calls  # type: ignore[attr-defined]
    return run


def _stage(tmp: Path, stage: str, runner, **kw) -> int:  # noqa: ANN001
    return vs.run_stage(stage, mode="mock", reports=tmp / "reports" / vs.STAGES[stage][0], results_root=tmp / "res",
                        work=tmp / "y", runner=runner, **kw)


def _log(tmp: Path, stage: str) -> dict:
    return json.loads((tmp / "reports" / vs.STAGES[stage][0] / "STAGE_LOG.json").read_text())


def test_smoke_stage_runs_end_to_end_on_the_mock(tmp_path):
    assert _stage(tmp_path, "smoke", vs.run_block, shorten=10) == 0
    log = _log(tmp_path, "smoke")
    assert log["status"] == "completed" and len(log["blocks"]) == 4
    for sid, b in log["blocks"].items():
        assert b["status"] == "passed" and (tmp_path / "reports" / "smoke" / sid / "manifest.json").exists()
        assert ("--path direct" in b["command"]) == sid.endswith("_direct")


def test_stage_order_is_enforced(tmp_path):
    assert _stage(tmp_path, "A", fake_runner()) == 3                    # A before the smokes
    assert _stage(tmp_path, "smoke", fake_runner()) == 0
    assert _stage(tmp_path, "A", fake_runner(fail={"v5_aa_ind_L200_C8"})) == 4
    assert _stage(tmp_path, "B", fake_runner()) == 3                    # B after a stopped A


def test_stop_resume_and_single_rerun(tmp_path):
    _stage(tmp_path, "smoke", fake_runner())
    bad = "v5_decode_vs_short_L200_C16"
    r1 = fake_runner(fail={bad})
    assert _stage(tmp_path, "A", r1) == 4
    assert r1.calls[-1] == bad and _log(tmp_path, "A")["status"] == "stopped"   # stops at the first failure
    assert _stage(tmp_path, "A", fake_runner()) == 3                                 # no plain resume
    assert _stage(tmp_path, "A", fake_runner(), rerun="v5_aa_ind_L200_C8", reason="x") == 3  # not a failed block
    assert _stage(tmp_path, "A", fake_runner(), rerun=bad) == 3                      # reason required
    r2 = fake_runner()
    assert _stage(tmp_path, "A", r2, rerun=bad, reason="harness fix abc123") == 0
    assert r2.calls[0] == f"{bad}__r2" and bad not in r2.calls                       # completed blocks never rerun
    log = _log(tmp_path, "A")
    assert log["status"] == "completed" and log["blocks"][bad]["status"] == "failed"  # the failure is kept
    assert "harness fix abc123" in log["blocks"][f"{bad}__r2"]["reason"]
    assert _stage(tmp_path, "A", fake_runner(), rerun=bad, reason="again") == 3       # at most one rerun


def test_second_failure_stops_for_owner_review(tmp_path):
    _stage(tmp_path, "smoke", fake_runner())
    bad = "v5_aa_ind_L200_C16"
    _stage(tmp_path, "A", fake_runner(fail={bad}))
    assert _stage(tmp_path, "A", fake_runner(fail={f"{bad}__r2"}), rerun=bad, reason="r") == 4
    assert _stage(tmp_path, "A", fake_runner(), rerun=bad, reason="r") == 3


def test_server_identity_checked_before_and_after_every_block(tmp_path):
    _stage(tmp_path, "smoke", fake_runner())
    starts = iter([1.0, 1.0, 2.0])   # restart detected before block 3
    rc = _stage(tmp_path, "A", fake_runner(start="1.0"), server_start_fn=lambda: next(starts))
    log = _log(tmp_path, "A")
    assert rc == 4 and "server_identity" in log["stopped_reason"] and len(log["blocks"]) == 2
    t2 = tmp_path / "b"
    _stage(t2, "smoke", fake_runner())
    rc = _stage(t2, "A", fake_runner(start="9.0"), server_start_fn=lambda: 1.0)   # manifest disagrees after block 1
    assert rc == 4 and "manifest server start" in _log(t2, "A")["stopped_reason"]


def test_budget_rule_stops_live_stage(tmp_path):
    (tmp_path / "reports" / "smoke").mkdir(parents=True)
    (tmp_path / "reports" / "smoke" / "STAGE_LOG.json").write_text(json.dumps({"status": "completed"}))
    est = sum(vs.estimate_min(f) for f in vs.block_files("A"))
    rc = vs.run_stage("A", mode="live", reports=tmp_path / "reports" / "stage_a", results_root=tmp_path / "r",
                      runner=fake_runner(wall_s=est * 60 * 1.31))
    assert rc == 4 and "budget" in _log(tmp_path, "A")["stopped_reason"]


def test_live_refuses_in_the_current_repository_state(tmp_path, monkeypatch):
    """Today (after P1 passed, before the freeze): not frozen, no FROZEN_TRACES.json, no approval — each is reported;
    the committed P1 host record itself passes the gate."""
    monkeypatch.delenv(vs.APPROVAL_ENV, raising=False)
    p = vs.live_problems("smoke", REPO / "reports" / "v5" / "smoke", interactive_ok=False)
    text = "\n".join(p)
    for needle in ("QUOTASHIFT_APPROVED", "interactively", "not frozen", "FROZEN_TRACES.json"):
        assert needle in text, (needle, p)
    assert vs.HOST_RECORD.exists() and vs.host_record_problems(json.loads(vs.HOST_RECORD.read_text())) == []
    r = subprocess.run(["bash", str(REPO / "scripts" / "run_v5.sh"), "smoke", "--live"], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, cwd=REPO)
    assert r.returncode == 3 and "REFUSED" in r.stderr


def test_mock_output_never_lands_in_the_repository():
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "v5_stage.py"), "smoke", "--mock", "--out-root",
                        str(REPO / "reports" / "v5")], capture_output=True, text=True)
    assert r.returncode == 3 and "outside the repository" in r.stderr


def test_raw_output_paths_are_git_ignored():
    assert vs.ignored_problems(REPO / "reports" / "v5" / "stage_a") == []


@pytest.mark.parametrize("rec,needle", [
    ({"vllm_version": "0.17.1", "launch_command": "vllm serve ...", "max_num_seqs": 256, "max_num_batched_tokens": 2048,
      "verified_by": "owner", "verified_utc": "2026-11-24T00:00:00Z", "model_snapshot_sha": "abc",
      "max_num_seqs_source": "argv", "model_snapshot_evidence_level": "verified_direct"}, None),
    ({"vllm_version": "0.17.1", "launch_command": "x", "max_num_seqs": 32, "max_num_batched_tokens": 2048,
      "verified_by": "o", "verified_utc": "t", "model_snapshot_sha": "abc"}, "max_num_seqs 32"),
    ({"vllm_version": "0.17.1", "launch_command": "x", "max_num_seqs": 32, "c32_dropped": True,
      "max_num_batched_tokens": 2048, "verified_by": "o", "verified_utc": "t", "model_snapshot_sha": "abc",
      "max_num_seqs_source": "argv", "model_snapshot_evidence_level": "verified_direct"}, None),
    ({"vllm_version": "0.18.0", "launch_command": "x", "max_num_seqs": 256, "max_num_batched_tokens": 2048,
      "verified_by": "o", "verified_utc": "t", "model_revision_waiver": "signed"}, "0.18.0"),
    ({"vllm_version": "0.17.1", "launch_command": "x", "max_num_seqs": 256, "max_num_batched_tokens": 2048,
      "verified_by": "o", "verified_utc": "t"}, "model snapshot"),
])
def test_host_record_rules(rec, needle):
    p = vs.host_record_problems(rec)
    assert (p == []) if needle is None else any(needle in x for x in p), p
