"""Pre-freeze consistency (owner request, rev 3): the Protocol v5 text, the frozen JSON artifacts, the generated
YAMLs, the decision-rule constants and the driver/gate constants agree. Any later edit to one side fails here."""

from __future__ import annotations

import inspect
import json
import math
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import build_v5 as B  # noqa: E402
import v5_analysis as A  # noqa: E402
import v5_stage as S  # noqa: E402

from quotashift.evaluation import occupancy as O  # noqa: E402

TXT = (REPO / "docs" / "PROTOCOL_V5.md").read_text()
PRED = json.loads((REPO / "experiments" / "v5" / "FCFS_PREDICTIONS.json").read_text())


def _num(x: str) -> float:
    return float(x.replace(",", "").strip("*"))


def test_fcfs_table_matches_frozen_predictions():
    rows = {"D vs S, L200": "decode_vs_short_L200", "P vs S, L200": "prefill_vs_short_L200",
            "A/A-ind, L200": "aa_ind_L200", "D vs S, L400": "decode_vs_short_L400", "A/A-ind, L400": "aa_ind_L400"}
    for label, cell in rows.items():
        line = next(ln for ln in TXT.splitlines() if ln.startswith(f"| {label} |"))
        cols = [c.strip() for c in line.strip("|").split("|")]
        for C, col in zip((8, 16, 32), cols[1:4], strict=True):
            atk, ctl = (re.findall(r"[\d,]+(?:\.\d+)?", part)[0] for part in col.split(" / ")[:2])
            ent = PRED["cells"][f"v5_{cell}_C{C}"]
            for shown, key in ((atk, "attack"), (ctl, "control")):
                v = ent[f"{key}_cell_victim_queue_mean_ms"]
                dec = len(shown.split(".")[1]) if "." in shown else 0
                assert _num(shown) == round(v, dec), (label, C, key, shown, v)
        assert ("validated" if PRED["cells"][f"v5_{cell}_C8"]["validated_envelope"] else "extrapolated") in cols[4]


def test_tolerances_and_loso_match_text():
    t, v = PRED["tolerances"], PRED["validation_c8_loso"]
    assert f"τ_abs = **{t['tau_abs_ms']:.2f} ms**" in TXT and f"ρ = **{t['rho_rel']:.3f}**" in TXT
    row = (f"| {v['n_runs']} | {v['mae_ms']:.1f} ms | {v['bias_ms']:.1f} ms | {v['rmse_ms']:.1f} ms | "
           f"{v['abs_err_q95_ms']:.2f} ms | {v['rel_abs_err_q95_obs_ge_5ms']:.3f} | {v['pi90_coverage']:.2f} |")
    assert row.replace("-", "−") in TXT
    assert f"(0–{v['obs_range_ms'][1]:.0f} ms)" in TXT


def test_decision_constants_match_text():
    assert A.THRESHOLD == 1.25 and math.isclose(A.EQ_LO, math.log(0.8)) and math.isclose(A.EQ_HI, math.log(1.25))
    assert A.ALPHA == 0.05 and "Holm at α = 0.05" in TXT
    assert A.SLO_BASELINE_MIN == 0.95 and "victim offered-load SLO success is ≥ 0.95" in TXT
    assert (A.COMPLETION_MIN, A.CENSOR_MAX) == (0.95, 0.05) and "completion is ≥ 0.95 **and** victim censoring is ≤ 0.05" in TXT
    assert A.SPEARMAN_MIN == 0.6 and "Spearman ρ ≥ 0.6" in TXT
    assert inspect.signature(A.engine_queue_negligible).parameters["mean_max_s"].default == 0.010
    assert "histogram mean ≤ 10 ms **and** every observation in the le = 0.3 s bucket" in TXT
    assert "log 1.25 > 2× the A/A-ind 95% half-width" in TXT
    assert O.MIN_RECON_EXACT_FRACTION == 0.90 and "≥ 90% of the time" in TXT
    assert O.MAX_ALIGNMENT_LAG_S == 0.05 and "within ±0.05 s" in TXT
    assert S.BUDGET_FACTOR == 1.3 and "exceeds 1.3× the stage estimate" in TXT
    assert S.ARM_MIN_PER_120S == 2.6 and "2.6 min of wall time per 120 s arm" in TXT
    assert S.MIN_MAX_NUM_SEQS == 64 and "`max_num_seqs` < 64" in TXT


def test_rule_shapes_match_text():
    """H4(b) and H2a use max(p_t, p_perm); F1 = {H1, H2a, H2b}; F2 = H6 at three caps; 10 seeds 5000..5009."""
    for fn in (A.h4b_queue_reduction, A.h2a_dose_response):
        src = inspect.getsource(fn)
        assert "max(p_t, p_perm)" in src and "sign_flip_p" in src
    assert "p_H4b = max(p_t, p_perm)" in TXT and "p_H2a = max(p_t, p_perm)" in TXT
    src = inspect.getsource(A.analyse)
    assert 'f1_p["H1"]' in src and 'f1_p["H2a"]' in src and 'f1_p["H2b"]' in src and "holm(f2_p)" in src
    assert (B.SEED0, B.REPS, B.CAPS) == (5000, 10, (8, 16, 32)) and "**10 per cell, 5000–5009**" in TXT
    assert "sign-symmetry assumption" in TXT


def test_yaml_counts_and_shapes_match_text():
    assert "decode 64/256 ×75" in TXT and "short 64/64 ×188" in TXT and "prefill 1024/32 ×23" in TXT and "short ×190" in TXT
    for f in sorted((REPO / "experiments" / "v5").rglob("*.yaml")):
        d = yaml.safe_load(f.read_text())
        c = d["comparison"]
        assert (c["preregistered_threshold"], c["degradation_metric"], c["effect_direction"]) == (1.25, "user_ttft_mean", "two_sided")
        assert d["benign"] == {"rate_rps": 0.3, "request_shape": "short", "ttft_deadline_ms": 2000, "e2e_deadline_ms": 30000}
        if "smoke" not in f.stem:
            assert (d["seed"], c["repetitions"], d["runtime_seconds"]) == (5000, 10, 120), f
