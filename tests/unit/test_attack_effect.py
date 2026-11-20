"""Phase 5 attack-effect analysis: ratios, success rate, bootstrap CI, report."""

from __future__ import annotations

import json

import numpy as np
import pytest

from quotashift.evaluation.attack_effect import (
    RunMetrics,
    analyze_pair,
    bootstrap_ci,
    run_metrics,
    write_report,
)


def _rm(arm, seed, ttft, e2e=100.0, timed_out=0, tokens=1000, reqs=10) -> RunMetrics:
    return RunMetrics(
        run_dir=f"/x/{arm}/{seed}", scenario="s", arm=arm, seed=seed, synthetic_backend=True,
        victim_completed=50, victim_timed_out=timed_out,
        victim_ttft_p50_ms=ttft * 0.8, victim_ttft_p95_ms=ttft,
        victim_e2e_p50_ms=e2e * 0.8, victim_e2e_p95_ms=e2e,
        competitor_requests=reqs, competitor_tokens=tokens,
    )


def test_bootstrap_ci_deterministic_and_ordered():
    vals = [1.2, 1.5, 1.4, 1.8, 1.3]
    a = bootstrap_ci(vals, seed=0)
    b = bootstrap_ci(vals, seed=0)
    assert a == b
    assert a[0] <= np.mean(vals) <= a[1]


def test_bootstrap_ci_degenerate():
    assert bootstrap_ci([]) != bootstrap_ci([])  # both nan, nan != nan
    lo, hi = bootstrap_ci([2.0])
    assert lo == hi == 2.0


def test_ratio_and_success_rate():
    attack = [_rm("attack", s, ttft=t) for s, t in zip((1, 2, 3, 4), (200, 160, 90, 180), strict=True)]
    control = [_rm("control", s, ttft=100.0) for s in (1, 2, 3, 4)]
    a = analyze_pair(attack, control, metric="ttft_p95", threshold=1.5)
    assert a["n_seeds"] == 4
    assert [round(r["ratio"], 2) for r in a["per_seed"]] == [2.0, 1.6, 0.9, 1.8]
    # 3 of 4 cross 1.5x
    assert a["attack_success_rate"] == pytest.approx(0.75)
    assert a["mean_ratio"] == pytest.approx(1.575)


def test_pairs_only_on_shared_seeds():
    attack = [_rm("attack", 1, 150.0), _rm("attack", 2, 150.0)]
    control = [_rm("control", 1, 100.0)]  # seed 2 missing
    a = analyze_pair(attack, control, metric="ttft_p95", threshold=1.5)
    assert a["n_seeds"] == 1 and a["per_seed"][0]["seed"] == 1


def test_budget_normalized_effect_present():
    attack = [_rm("attack", s, ttft=150.0, tokens=2000, reqs=20) for s in (1, 2)]
    control = [_rm("control", s, ttft=100.0) for s in (1, 2)]
    a = analyze_pair(attack, control, metric="ttft_p95", threshold=1.5)
    # slowdown 0.5 over 2000 tokens -> 0.25 per 1k
    assert a["slowdown_per_1k_competitor_tokens"] == pytest.approx(0.25, rel=1e-6)
    assert a["slowdown_per_100_competitor_requests"] == pytest.approx(2.5, rel=1e-6)


def test_write_report_emits_all_artifacts(tmp_path):
    attack = [_rm("attack", s, ttft=200.0) for s in (1, 2, 3)]
    control = [_rm("control", s, ttft=100.0) for s in (1, 2, 3)]
    analysis = analyze_pair(attack, control, metric="ttft_p95", threshold=1.5)
    pairs = {
        "control_label": "matched_total_short", "seeds": [1, 2, 3],
        "attack": {1: "/a/1", 2: "/a/2", 3: "/a/3"},
        "control": {1: "/c/1", 2: "/c/2", 3: "/c/3"},
        "budgets": {1: {"matched": True}, 2: {"matched": True}, 3: {"matched": True}},
        "budget_tolerance": 0.05,
    }
    out = write_report("s", pairs, analysis, attack, control, tmp_path, commands=["cmd"])
    assert (tmp_path / "summary.csv").exists()
    md = (tmp_path / "summary.md").read_text()
    assert "attack-effect report" in md and "Pre-registered threshold" in md
    assert "100%" in md  # all 3 cross 2.0x >= 1.5x
    man = json.loads((tmp_path / "manifest.json").read_text())
    assert man["control_label"] == "matched_total_short"
    assert man["analysis"]["attack_success_rate"] == 1.0
    assert "per_seed" not in man["analysis"]  # per-seed kept out of the compact analysis block
    assert set(out) >= {"csv", "md", "manifest", "figures"}


def test_run_metrics_reads_a_real_run(repo, tmp_path):
    # Build a tiny run via the mock and read it back.
    from quotashift.local import run_scenario_local
    from quotashift.scenario import load_scenario

    sc = load_scenario(repo / "experiments" / "a1_burst_arrivals.yaml")
    run_dir = run_scenario_local(sc, tmp_path, experiment_id="a1__attack", seed=sc.seed)
    m = run_metrics(run_dir, sc.scenario_id, "attack", sc.seed)
    assert m.arm == "attack" and m.synthetic_backend is True
    assert m.victim_completed > 0
    assert np.isfinite(m.victim_ttft_p95_ms) and np.isfinite(m.victim_e2e_p95_ms)
    assert m.competitor_requests > 0 and m.competitor_tokens > 0
