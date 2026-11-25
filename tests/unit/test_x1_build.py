"""X1 scenario generator (scripts/build_x1.py): determinism, seeds, n, salts, reruns, rate rule. Offline only."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import build_x1 as bx  # noqa: E402

from quotashift.scenario import load_scenario  # noqa: E402

RATES = {"low": 200, "high": 400, "low_feasible": True}


def test_grid_and_speed_factor():
    assert bx.grid(1.0) == [120, 160, 200, 260, 330, 420]
    g = bx.grid(0.37)
    assert g == sorted(set(g)) and all(r % 5 == 0 and r >= 5 for r in g)
    with pytest.raises(ValueError):
        bx.grid(0)


def test_choose_rates_rule_closest_ties_lower_and_infeasible():
    cal = {120: {"rho_ctl": 0.25, "slo_ctl": 1.0}, 200: {"rho_ctl": 0.43, "slo_ctl": 1.0},
           260: {"rho_ctl": 0.55, "slo_ctl": 1.0}, 330: {"rho_ctl": 0.70, "slo_ctl": 1.0},
           420: {"rho_ctl": 0.74, "slo_ctl": 0.97}}
    r = bx.choose_rates(cal)
    assert (r["low"], r["high"], r["low_feasible"]) == (200, 330, True)      # 0.70 and 0.74 tie at 0.02 -> lower
    bad = {k: {"rho_ctl": v["rho_ctl"] * 0.5, "slo_ctl": v["slo_ctl"]} for k, v in cal.items()}
    assert bx.choose_rates(bad)["low_feasible"] is False
    with pytest.raises(SystemExit, match="infeasible"):
        bx.build_main("g0m0", {"low": 1, "high": 2, "low_feasible": False})


def test_main_cells_seeds_n_and_salts(tmp_path):
    files = bx.with_reruns(bx.build_main("g1m1", RATES))
    bx.write(files, tmp_path)
    main = sorted((tmp_path / "g1m1" / "main").glob("x1_*.yaml"))
    assert [p.stem.split("_")[2] for p in main] == ["Xa", "Xb", "Xc", "Xd", "Xe", "Xf"]
    for p in main:
        sc = load_scenario(p)
        block = p.stem.split("_")[2]
        n = {"Xa": 24, "Xd": 24}.get(block, 10)
        assert (sc.seed, sc.comparison.repetitions) == (8000, n)
        assert sc.model == "mistralai/Mistral-7B-Instruct-v0.3" and sc.protocol_version == 5
        assert sc.isolation_salt == f"x1-g1m1-{p.stem}-r1" and sc.comparison.preregistered_threshold == 1.25
        assert sc.safety.max_global_inflight == {"Xb": 32}.get(block, 8)
        r2 = load_scenario(tmp_path / "g1m1" / "main" / "reruns" / f"{p.stem}__r2.yaml")
        assert r2.scenario_id == f"{p.stem}__r2" and r2.isolation_salt.endswith("-r2") and r2.seed == sc.seed
    xc = yaml.safe_load((tmp_path / "g1m1" / "main" / "x1_g1m1_Xc_decode_vs_short_low_direct.yaml").read_text())
    assert xc["phases"][0]["request_count"] == bx.count("D", 200)


def test_calibration_seed_sets_are_disjoint_from_main():
    a = bx.build_cal_a("g0m0", 1.0)
    b = bx.build_cal_b("g0m0", RATES)
    seeds = set()
    for text in (*a.values(), *b.values()):
        d = yaml.safe_load(text)
        seeds |= set(range(d["seed"], d["seed"] + d["comparison"]["repetitions"]))
    assert seeds == set(range(7000, 7008)) and not seeds & set(range(8000, 8024))
    assert len(a) == 6 and len(b) == 4


def test_generation_is_deterministic():
    one = bx.digest(bx.with_reruns(bx.build_main("g0m0", RATES)))
    two = bx.digest(bx.with_reruns(bx.build_main("g0m0", RATES)))
    assert one == two and one != bx.digest(bx.with_reruns(bx.build_main("g0m1", RATES)))
