"""X1-H5 predictor parameters are exactly the owner-approved values and inherit the frozen v5 settings."""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import v5_fcfs_predictions as v5p  # noqa: E402
import x1_predictions as xp  # noqa: E402


def test_rng_mc_and_loso_parameters():
    assert xp.RNG_ENTROPY == 81000
    assert xp.MC_DRAWS == v5p.MC == 200
    assert xp.LOSO_DRAWS == 50 and "draws=50" in inspect.getsource(v5p.loso_validation)   # same as v5 LOSO
    assert (xp.TAU_ABS_FLOOR_MS, xp.RHO_OBS_MIN_MS, xp.RHO_MIN_RUNS) == (5.0, 5.0, 3)
    assert xp.PREDICTED == {"Xa": "low", "Xb": "low", "Xe": "high"}


def test_fallback_is_the_frozen_v5_value_with_provenance():
    v5 = json.loads((REPO / "experiments" / "v5" / "FCFS_PREDICTIONS.json").read_text())
    assert xp.V5_RHO_FALLBACK == v5["tolerances"]["rho_rel"]
    src = inspect.getsource(xp.loso)
    assert '"v5_fallback"' in src and '"rho_source"' in src
    assert '"rho_fallback_source": "experiments/v5/FCFS_PREDICTIONS.json"' in inspect.getsource(xp.build)


def test_loso_rule_on_synthetic_runs(monkeypatch):
    import numpy as np
    rows = []

    def fake_predict(arr, vic, pool, cap, rng, horizon, draws):  # noqa: ANN001, ARG001
        assert draws == xp.LOSO_DRAWS and cap == 8
        return {"victim_queue_mean_ms": 10.0}
    monkeypatch.setattr(xp.v5p, "predict", fake_predict)
    monkeypatch.setattr(xp.v5p, "pool_of", lambda lst, exclude_seed=None: {})
    import pandas as pd

    def fake_holds(run):  # noqa: ANN001
        obs = float(run.name)
        return pd.DataFrame({"t_sent": [obs / 1000], "t_offered": [0.0], "t_terminal": [1.0], "workload_class": ["victim"]})
    monkeypatch.setattr(xp.v5p, "holds", fake_holds)
    runs = {("low", "decode_vs_short", "attack"): [(7003 + i, Path(str(o))) for i, o in enumerate((2, 3, 4, 1, 2))]}
    t = xp.loso(runs, np.random.default_rng(0))
    assert t["rho_source"] == "v5_fallback" and t["rho_rel"] == xp.V5_RHO_FALLBACK and t["n_obs_ge_5ms"] == 0
    runs = {("low", "decode_vs_short", "attack"): [(7003 + i, Path(str(o))) for i, o in enumerate((8, 12, 20, 9, 11))]}
    t = xp.loso(runs, np.random.default_rng(0))
    assert t["rho_source"] == "loso" and t["n_obs_ge_5ms"] == 5 and t["tau_abs_ms"] >= 5.0
    del rows
