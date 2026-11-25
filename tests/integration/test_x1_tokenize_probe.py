"""X1 tokenization probe against the LOCAL MOCK server only (no GPU, no real target)."""

from __future__ import annotations

import pytest

from quotashift.config import BackendConfig
from quotashift.runtime.runner import local_mock_server
from quotashift.x1 import preflight as pf
from quotashift.x1.tokenize_probe import run_probe

PROMPTS = ["probe alpha beta gamma " * 8, "probe delta epsilon " * 30]


def test_phase1_isolated_and_phase2_burst_on_mock():
    with local_mock_server(BackendConfig(kind="mock_http", model="mock-model", time_scale=1.0)) as url:
        p1 = run_probe(url, "mock-model", PROMPTS, peak_request_rps=None, repeats=50)
        assert "burst" not in p1 and len(p1["isolated_ms"]) == 50
        p2 = run_probe(url, "mock-model", PROMPTS, peak_request_rps=3.0, repeats=50, burst_seconds=2.0)
    b = p2["burst"]
    assert b["sent"] == 60 and b["errors"] == 0 and b["completed"] == 60
    r = pf.tokenization_check(isolated_ms=p2["isolated_ms"], peak_request_rps=3.0, burst_offered_rps=b["offered_rps"],
                              burst_achieved_rps=b["achieved_rps"], burst_ms=b["latencies_ms"])
    assert r["status"] in ("pass", "flag"), r
    assert r["isolated_p99_ms"] < pf.TOK_ISOLATED_P99_FAIL_MS


def test_probe_refuses_public_targets():
    with pytest.raises(ValueError, match="non-private"):
        run_probe("http://example.com:8000", "m", PROMPTS, peak_request_rps=None, repeats=1)
