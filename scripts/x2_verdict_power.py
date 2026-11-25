"""X2 verdict power: P(REPLICATES) for the X2 per-platform conjunction H1 & H2 & H3 & H4 (offline; planning only).

    uv run python scripts/x2_verdict_power.py       # -> reports/x2/VERDICT_POWER.json

Same inputs and noise model as the X1 P0 power study (reports/x1/P0_POWER.md, v5 estimates): per-seed log ratio for
D vs S at C = 8 ~ N(log r + tau z_p, 0.330 k), n = 24; C = 32 ~ N(0, 0.023 k), direct ~ N(0, 0.021 k), n = 10; backend
log ratio ~ N(-0.0054, 0.0138 k), n = 24 (engine queue assumed negligible, as in v5). Decision rules are the FROZEN v5
functions (p_superiority, p_tost, holm, mean_ci, t_cdf), applied exactly as scripts/x2_analysis.py does.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import v5_analysis as va  # noqa: E402

OUT = REPO / "reports" / "x2" / "VERDICT_POWER.json"
SEED, REPS = 23990, 1000
PLATS = ("g0m0", "g0m1", "g1m0", "g1m1")


def backend_holds(lr: np.ndarray) -> bool:
    ci = va.mean_ci(list(lr))
    lo, hi = math.log(0.9), math.log(1.1)
    p = max(1.0 - va.t_cdf((ci.mean - lo) / ci.se, ci.n - 1), va.t_cdf((ci.mean - hi) / ci.se, ci.n - 1))
    return p < va.ALPHA


def one(rng: np.random.Generator, r: float, tau: float, k: float, n_effect: int = 4) -> int:
    p1, p23, h4 = {}, {}, {}
    for i, p in enumerate(PLATS):
        mu = math.log(r) + tau * rng.standard_normal() if i < n_effect else 0.0
        p1[p] = va.p_superiority(list(rng.normal(mu, 0.330 * k, 24)))
        p23[f"H2_{p}"] = va.p_tost(list(rng.normal(0.0, 0.021 * k, 10)))
        p23[f"H3_{p}"] = va.p_tost(list(rng.normal(0.0, 0.023 * k, 10)))
        h4[p] = backend_holds(rng.normal(-0.0054, 0.0138 * k, 24))
    h1, h23 = va.holm(p1), va.holm(p23)
    return sum(bool(h1[p] and h23[f"H2_{p}"] and h23[f"H3_{p}"] and h4[p]) for p in PLATS)


def main() -> int:
    rng = np.random.default_rng(SEED)
    rows = []
    for r in (1.4, 1.565, 1.8):
        for tau in (0.0, 0.2):
            for k in (1.0, 1.5):
                ks = [one(rng, r, tau, k) for _ in range(REPS)]
                rows.append({"ratio": r, "tau": tau, "sd_mult": k, "P_REPLICATES": float(np.mean([x >= 3 for x in ks])),
                             "P_at_least_1": float(np.mean([x >= 1 for x in ks]))})
                print(rows[-1], flush=True)
    false = [one(rng, 1.8, 0.0, 1.0, n_effect=2) for _ in range(REPS)]
    out = {"seed": SEED, "reps": REPS, "rows": rows,
           "false_replication_effect_on_2_of_4": float(np.mean([x >= 3 for x in false]))}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print("false replication (effect on 2 of 4):", out["false_replication_effect_on_2_of_4"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
