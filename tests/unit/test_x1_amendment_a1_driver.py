"""Amendment A1: separate pin manifest, the Phase 1 run gate, and the A1 measurement loop (mocked server/host)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import pin_x1_amendment as pa  # noqa: E402
import x1_preflight as xp  # noqa: E402

from quotashift.x1 import sampler_equivalence_a1 as a1  # noqa: E402


def test_check_reports_missing_manifest(tmp_path):
    assert "has not been pinned" in pa.check(tmp_path / "none.json")[0]


def test_write_refused_without_token(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "QUOTASHIFT_APPROVED"}
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "pin_x1_amendment.py"), "--write"], env=env,
                       capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 3 and "x1_amend_a1" in r.stderr


def test_check_detects_a_changed_file(tmp_path):
    files = {"scripts/pin_x1_amendment.py": pa.sha_file(REPO / "scripts/pin_x1_amendment.py")}
    m = tmp_path / "m.json"
    m.write_text(json.dumps({"files": files, "freeze1_manifest_sha256": pa.sha_file(pa.pin_x1.MANIFEST)}))
    assert pa.check(m) == []
    m.write_text(json.dumps({"files": {k: "0" * 64 for k in files},
                             "freeze1_manifest_sha256": pa.sha_file(pa.pin_x1.MANIFEST)}))
    assert any("changed since the A1 pin" in x for x in pa.check(m))


def test_pinned_set_covers_rule_driver_and_failed_records():
    for f in ("src/quotashift/x1/sampler_equivalence_a1.py", "scripts/x1_preflight.py", "docs/PROTOCOL_X1_AMENDMENT_A1.md",
              "experiments/x1/g0m0/HOST_VERIFICATION.attempt1.json", "experiments/x1/g0m0/HOST_VERIFICATION.attempt2.json"):
        assert f in pa.FILES


def _gate(tmp_path, rec: dict | None, copies: dict | None = None, token: str = "x1_preflight_a1_g0m0") -> list[str]:
    d = tmp_path / "g0m0"
    d.mkdir(exist_ok=True)
    if rec is not None:
        (d / "HOST_VERIFICATION.json").write_text(json.dumps(rec))
    for name, body in (copies or {}).items():
        (d / name).write_text(body)
    return [x for x in xp.a1_problems("g0m0", root=tmp_path, env={"QUOTASHIFT_APPROVED": token})
            if not x.startswith("Amendment A1 pin")]


def test_gate_token_single_run_and_preservation(tmp_path):
    old = {"preflight": {"phase1": {"status": "fail"}}}
    assert any("not preserved" in x for x in _gate(tmp_path, old))
    assert _gate(tmp_path, old, {"HOST_VERIFICATION.attempt2.json": json.dumps(old)}) == []
    assert any("must be x1_preflight_a1_g0m0" in x for x in _gate(tmp_path, old, token="x1_local_restart"))
    done = {"preflight": {"phase1": {"amendment": {"id": "A1"}}}}
    assert any("one amended run only" in x for x in _gate(tmp_path, done))


def test_a1_measure_loop_feeds_the_rule(tmp_path, monkeypatch):
    state = {"running": False}

    def fake_ssh(host, cmd, stdin=None, timeout=900):
        if cmd.startswith("pgrep"):
            return "123\n" if state["running"] else ""
        if "pkill" in cmd:
            state["running"] = False
        if "setsid nohup" in cmd:
            state["running"] = True
        return ""
    sent = []

    def fake_completion(base, model, prompt, max_tokens, *, stream=False):
        sent.append((prompt, state["running"]))
        return {"ttft_ms": 58.0 + (0.2 if state["running"] else 0.0) + (len(sent) % 7) * 0.1, "chunks": 8}

    def fake_stop(host, tag, dst):
        state["running"] = False
        import time
        return [{"ts": time.time()}]
    monkeypatch.setattr(xp, "ssh", fake_ssh)
    monkeypatch.setattr(xp, "completion", fake_completion)
    monkeypatch.setattr(xp, "sampler_stop", fake_stop)
    monkeypatch.setattr(xp, "reset_and_verify", lambda *a, **k: {"verified": True})
    monkeypatch.setattr(xp, "ttft_hist", lambda base: {"sum_s": 0.0, "count": 0.0})
    monkeypatch.setattr(xp.time, "sleep", lambda s: None)
    segs = xp.a1_measure("h", "http://x", "m", "g0m0", tmp_path)
    assert [(s["pair"], s["arm"]) for s in segs] == a1.segment_order()
    assert len(sent) == 2 * a1.K_PAIRS * (a1.M_PER_SEGMENT + a1.WARMUP)
    assert all(s["sampler_state_ok"] and s["reset_verified"] and len(s["ttft_ms"]) == a1.M_PER_SEGMENT for s in segs)
    on_flags = {s["arm"]: s["sampler_running_before"] for s in segs}
    assert on_flags == {"on": True, "off": False}
    r = a1.equivalence_a1(segs)
    assert r["status"] == "pass" and abs(r["mean_diff_ms"] - 0.2) < 0.15
    rows = json.loads((tmp_path / "a1_requests.json").read_text())
    assert sum(r["kind"] == "measured" for r in rows) == 2 * a1.K_PAIRS * a1.M_PER_SEGMENT
