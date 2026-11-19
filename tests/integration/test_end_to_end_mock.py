"""End-to-end local mock run: well-formed manifest, events, summary; failures kept."""

from __future__ import annotations

import json

from quotashift.local import run_scenario_local
from quotashift.scenario import load_scenario


def test_run_local_smoke_outputs(repo, tmp_path):
    sc = load_scenario(repo / "experiments" / "smoke.yaml")
    out = run_scenario_local(sc, tmp_path)

    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["synthetic_backend"] is True
    assert "MOCK BACKEND" in manifest["integrity_note"]
    assert len(manifest["trace_sha256"]) == 64

    summary = json.loads((out / "metrics_summary.json").read_text())
    assert summary["event_validation_ok"] is True
    assert summary["accounting_conserved"] is True
    # every declared tenant appears in the per-tenant breakdown
    for t in [*sc.victim_tenants, *sc.competing_tenants]:
        assert t in summary["per_tenant"]

    assert (out / "events.parquet").exists()
    assert (out / "requests.parquet").exists()
    assert (out / "trace.jsonl").exists()


def test_run_local_baseline_has_no_competitor(repo, tmp_path):
    sc = load_scenario(repo / "experiments" / "baseline.yaml")
    out = run_scenario_local(sc, tmp_path)
    summary = json.loads((out / "metrics_summary.json").read_text())
    assert set(summary["per_tenant"]) == set(sc.victim_tenants)


def test_status_counts_conserved(repo, tmp_path):
    sc = load_scenario(repo / "experiments" / "smoke.yaml")
    out = run_scenario_local(sc, tmp_path)
    summary = json.loads((out / "metrics_summary.json").read_text())
    offered = summary["offered"]
    assert sum(summary["status_counts"].values()) == offered  # nothing silently dropped
