"""X1 P0 planning only: Monte-Carlo power of the X1 "mechanism generalises" verdict (3 of 4 platforms) under Holm.

    uv run python scripts/x1_power.py            # -> reports/x1/P0_POWER.{json,md}

Not an analysis of any data. Uses the FROZEN v5 decision functions by import (p_superiority, p_tost, holm, t_cdf;
scripts/v5_analysis.py is not modified) and v5 Stage A per-seed moments as planning inputs only.

Verdict simulated (docs/PROTOCOL_X1_CROSS_PLATFORM_DRAFT.md rev 2, §5):
  GENERALISES iff  #platforms with X1-H1 Holm-rejected (family of 4, one-sided t vs log 1.25)  >= 3
               and #platforms with X1-H2 equivalent  (TOST [0.8,1.25]; Holm family of 8 = 4 x H2 + 4 x H3)  >= 3
               and #platforms with X1-H4 holding     (TOST on log backend ratio, band [0.9, 1.1])            >= 3
Per-platform true log effect for X-a: mu + N(0, tau^2) (platform heterogeneity). Per-seed noise: Normal, or
"empirical" = resampled standardized v5 residuals (heavier right tail: v5 seed 5006). SDs scaled by k for the
unknown variability on L4 / Mistral.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import v5_analysis as va  # noqa: E402  (frozen; imported read-only)

OUT = REPO / "reports" / "x1"
REPS = 1000
SEED = 20261124


def v5_moments() -> dict:
    cells = json.loads((REPO / "reports" / "v5" / "analysis_A.json").read_text())["cells"]

    def col(c: str, f) -> np.ndarray:  # noqa: ANN001
        return np.array([f(s) for s in sorted(cells[c]["per_seed"], key=lambda s: s["seed"])])
    xa = col("v5_decode_vs_short_L200_C8", lambda s: s["log_ratio"])
    xb = col("v5_decode_vs_short_L200_C32", lambda s: s["log_ratio"])
    xc = col("v5_decode_vs_short_L200_direct", lambda s: s["log_ratio"])
    be = col("v5_decode_vs_short_L200_C8",
             lambda s: math.log(s["attack"]["backend_ttft_mean_ms"] / s["control"]["backend_ttft_mean_ms"]))
    z = (xa - xa.mean()) / xa.std(ddof=1)
    return {"xa_mu": xa.mean(), "xa_sd": xa.std(ddof=1), "xb_mu": xb.mean(), "xb_sd": xb.std(ddof=1),
            "xc_mu": xc.mean(), "xc_sd": xc.std(ddof=1), "be_mu": be.mean(), "be_sd": be.std(ddof=1),
            "xa_resid": z}


def p_tost_band(x: np.ndarray, lo: float, hi: float) -> float:
    n = len(x)
    m, se = float(np.mean(x)), float(np.std(x, ddof=1)) / math.sqrt(n)
    if se == 0:
        return 0.0 if lo < m < hi else 1.0
    return max(1 - va.t_cdf((m - lo) / se, n - 1), va.t_cdf((m - hi) / se, n - 1))


def draw(rng: np.random.Generator, n: int, mu: float, sd: float, resid: np.ndarray | None) -> np.ndarray:
    if resid is None:
        return rng.normal(mu, sd, n)
    return mu + sd * rng.choice(resid, n, replace=True)


def simulate(mo: dict, *, mu_ratio: float, tau: float, k: float, n_xa: int, n_other: int, noise: str,
             null_platforms: int = 0, reps: int = REPS) -> dict:
    rng = np.random.default_rng([SEED, int(mu_ratio * 1000), int(tau * 100), int(k * 10), n_xa, null_platforms,
                                 0 if noise == "normal" else 1])
    resid = mo["xa_resid"] if noise == "empirical" else None
    c_h1 = c_h2 = c_h4 = c_all = 0
    per_platform_h1 = 0
    for _ in range(reps):
        mus = math.log(mu_ratio) + rng.normal(0, tau, 4)
        if null_platforms:
            mus[:null_platforms] = 0.0                       # mechanism absent on these platforms
        p1, p2, h4 = {}, {}, 0
        for i in range(4):
            xa = draw(rng, n_xa, mus[i], mo["xa_sd"] * k, resid)
            p1[f"P{i}"] = va.p_superiority(list(xa))
            xb = rng.normal(mo["xb_mu"], mo["xb_sd"] * k, n_other)
            xc = rng.normal(mo["xc_mu"], mo["xc_sd"] * k, n_other)
            p2[f"H2_P{i}"] = va.p_tost(list(xb))
            p2[f"H3_P{i}"] = va.p_tost(list(xc))
            be = rng.normal(mo["be_mu"], mo["be_sd"] * k, n_xa)
            h4 += p_tost_band(be, math.log(0.9), math.log(1.1)) < 0.05
        r1 = va.holm(p1)
        r2 = va.holm(p2)
        n1 = sum(r1.values())
        n2 = sum(r2[f"H2_P{i}"] for i in range(4))
        per_platform_h1 += sum(r1.values())
        ok1, ok2, ok4 = n1 >= 3, n2 >= 3, h4 >= 3
        c_h1 += ok1
        c_h2 += ok2
        c_h4 += ok4
        c_all += ok1 and ok2 and ok4
    return {"mu_ratio": mu_ratio, "tau": tau, "k": k, "n_xa": n_xa, "n_other": n_other, "noise": noise,
            "null_platforms": null_platforms, "reps": reps,
            "P_H1_ge3": c_h1 / reps, "P_H2_ge3": c_h2 / reps, "P_H4_ge3": c_h4 / reps,
            "P_generalises": c_all / reps, "per_platform_H1_power": per_platform_h1 / (4 * reps)}


def _run(kw: dict) -> dict:
    return simulate(v5_moments(), **kw)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    mo = v5_moments()
    from concurrent.futures import ProcessPoolExecutor
    grid = [dict(mu_ratio=mu, tau=tau, k=k, n_xa=n, n_other=10, noise=noise)
            for noise in ("normal", "empirical") for mu in (1.4, 1.565, 1.8) for tau in (0.0, 0.2)
            for k in (1.0, 1.5) for n in (10, 16, 20, 24)]
    # false-generalisation check: mechanism absent on 2 of 4 platforms (the verdict must not say "generalises")
    grid += [dict(mu_ratio=1.8, tau=0.0, k=1.0, n_xa=n, n_other=10, noise="normal", null_platforms=2)
             for n in (16, 24)]
    with ProcessPoolExecutor() as ex:
        rows = list(ex.map(_run, grid))
    meta = {k: (float(v) if not isinstance(v, np.ndarray) else None) for k, v in mo.items()}
    (OUT / "P0_POWER.json").write_text(json.dumps({"inputs_v5": meta, "reps": REPS, "seed": SEED, "rows": rows},
                                                  indent=1) + "\n")
    lines = ["# X1 P0 power simulation (planning only; generated by scripts/x1_power.py)", "",
             f"v5 inputs: X-a log-ratio mean {mo['xa_mu']:.3f} SD {mo['xa_sd']:.3f}; X-b SD {mo['xb_sd']:.3f}; "
             f"X-c SD {mo['xc_sd']:.3f}; backend log ratio mean {mo['be_mu']:.4f} SD {mo['be_sd']:.4f}. "
             f"{REPS} replicates per row.", "",
             "| noise | true X-a ratio | τ | SD × k | n(X-a) | P(H1 ≥3/4) | P(H2 ≥3/4) | P(H4 ≥3/4) | **P(generalises)** | per-platform H1 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["null_platforms"]:
            continue
        lines.append(f"| {r['noise']} | {r['mu_ratio']} | {r['tau']} | {r['k']} | {r['n_xa']} | {r['P_H1_ge3']:.3f} | "
                     f"{r['P_H2_ge3']:.3f} | {r['P_H4_ge3']:.3f} | **{r['P_generalises']:.3f}** | "
                     f"{r['per_platform_H1_power']:.3f} |")
    lines += ["", "False-generalisation check (true X-a ratio 1.8 on 2 platforms, 1.0 on the other 2):", "",
              "| n(X-a) | P(generalises) — should be ≈ 0 |", "|---|---|"]
    lines += [f"| {r['n_xa']} | {r['P_generalises']:.4f} |" for r in rows if r["null_platforms"]]
    (OUT / "P0_POWER.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
