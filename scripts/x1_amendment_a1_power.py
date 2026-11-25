"""X1 Amendment A1: offline power / sample-size simulation for the paired-segment sampler-equivalence test.

    uv run python scripts/x1_amendment_a1_power.py            # -> reports/x1/AMENDMENT_A1_POWER.json (+ printed tables)

Offline only (no server, no GPU). Noise model = attempt 2 of g0m0 Phase 1 (the only clean, cache-cold per-request idle
TTFT sample: 20 OFF + 20 ON, experiments/x1/g0m0/HOST_VERIFICATION.json, committed 9427ddf). Each arm is centred on its
own nearest-rank median, so the observed +1.23 ms does not leak into the null; residuals are resampled with replacement.

Selection criteria (fixed in this file before it was first run):
  C1  base scenario (clean pool, scale 1.0, segment sd 0.25 ms, delta = 1.0 ms): P(pass | theta = 0) >= 0.95
  C2  pessimistic  (clean pool, scale 1.5, segment sd 0.50 ms, delta = 1.0 ms): P(pass | theta = 0) >= 0.80
  C3  P(pass | theta = +-delta) <= alpha (+ 2 Monte-Carlo SE) in every scenario (test size at the boundary)
  Choose the smallest total measured requests 2*K*M with K even >= 8 meeting C1 and C2; then confirm C3 at 20,000 draws.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from quotashift.x1.sampler_equivalence_a1 import t_ppf  # noqa: E402

RNG_SEED = 20261125
OUT = REPO / "reports" / "x1" / "AMENDMENT_A1_POWER.json"
SEC_PER_REQ, SEC_RESET, SEC_SAMPLER_TOGGLE, WARMUP = 0.23, 1.2, 5.0, 3   # G0 timings seen in attempt 2


def nr_median(a: np.ndarray, axis: int = -1) -> np.ndarray:
    """Nearest-rank p50 along an axis (= frozen pf.pctl(x, 50))."""
    m = a.shape[axis]
    return np.take(np.sort(a, axis=axis), max(0, math.ceil(m / 2) - 1), axis=axis)


def pools() -> dict[str, np.ndarray]:
    hv = json.loads((REPO / "experiments" / "x1" / "g0m0" / "HOST_VERIFICATION.json").read_text())
    f = hv["preflight"]["phase1"]["ttft_floor_ms"]
    off, on = np.array(f["sampler_off_ms"]), np.array(f["sampler_on_ms"])
    def centre(x: np.ndarray) -> np.ndarray:
        return x - nr_median(x)
    return {"clean": np.concatenate([centre(off[1:]), centre(on[1:])]),     # first request of each pass = warm-up
            "tail": np.concatenate([centre(off), centre(on)])}             # warm-up NOT absorbed (worst case)


def simulate(rng: np.random.Generator, pool: np.ndarray, *, k: int, m: int, scale: float, seg_sd: float, mu: float,
             theta: float, n: int, drift_per_seg: float = 0.0) -> dict:
    """Returns pass rates for TOST-90, strict-95 and (comparator) naive pooled Welch-90 on the same draws."""
    e = pool[rng.integers(0, len(pool), size=(n, k, 2, m))] * scale             # arm axis: 0 = off, 1 = on
    seg = rng.normal(0.0, seg_sd, size=(n, k, 2, 1)) if seg_sd > 0 else 0.0
    order = np.array([[0, 1] if j % 2 == 0 else [1, 0] for j in range(k)])     # execution position of (off, on)
    pos = (2 * np.arange(k)[:, None] + order)[None, :, :, None]                 # segment index in the session
    x = mu + e + seg + drift_per_seg * pos + theta * np.array([0.0, 1.0])[None, None, :, None]
    med = nr_median(x)                                                          # (n, k, 2)
    d = med[:, :, 1] - med[:, :, 0]
    mean, sd = d.mean(1), d.std(1, ddof=1)
    se = sd / math.sqrt(k)
    delta = np.maximum(1.0, 0.02 * nr_median(x[:, :, 0, :].reshape(n, -1)))
    t90, t95 = t_ppf(0.95, k - 1), t_ppf(0.975, k - 1)
    tost = (mean - t90 * se > -delta) & (mean + t90 * se < delta)
    s95 = (mean - t95 * se > -delta) & (mean + t95 * se < delta)
    # comparator: treat all K*M requests per arm as iid (ignores segments), Welch interval on means
    on, off = x[:, :, 1, :].reshape(n, -1), x[:, :, 0, :].reshape(n, -1)
    nn = on.shape[1]
    dm = on.mean(1) - off.mean(1)
    sw = np.sqrt(on.var(1, ddof=1) / nn + off.var(1, ddof=1) / nn)
    naive = (dm - 1.6449 * sw > -delta) & (dm + 1.6449 * sw < delta)
    return {"tost90": float(tost.mean()), "strict95": float(s95.mean()), "naive_welch90": float(naive.mean()),
            "sd_pair_diff": float(np.median(sd))}


def frozen_rule_false_fail(rng: np.random.Generator, pool: np.ndarray, n: int = 20000, m: int = 20, mu: float = 58.0) -> float:
    """Rev 4 point rule at 20 + 20, no sampler effect: P(|med_on - med_off| > 1 ms and > 2%)."""
    x = mu + pool[rng.integers(0, len(pool), size=(n, 2, m))]
    md = nr_median(x)
    d = md[:, 1] - md[:, 0]
    return float(((np.abs(d) > 1.0) & (np.abs(d) > 0.02 * md[:, 0])).mean())


def minutes(k: int, m: int) -> float:
    return (2 * k * (m + WARMUP) * SEC_PER_REQ + 2 * k * SEC_RESET + k * SEC_SAMPLER_TOGGLE) / 60


def main() -> int:
    rng = np.random.default_rng(RNG_SEED)
    P = pools()
    out: dict = {"rng_seed": RNG_SEED, "noise_source": "g0m0 Phase 1 attempt 2 (9427ddf), arms centred at own p50",
                 "pool_sd_ms": {k: float(v.std(ddof=1)) for k, v in P.items()},
                 "pool_mad_ms": {k: float(np.median(np.abs(v - np.median(v)))) for k, v in P.items()},
                 "frozen_rule_false_fail_at_theta0": {k: frozen_rule_false_fail(rng, v) for k, v in P.items()}}
    base = {"pool": "clean", "scale": 1.0, "seg_sd": 0.25, "mu": 50.0}
    pess = {"pool": "clean", "scale": 1.5, "seg_sd": 0.50, "mu": 50.0}
    grid = []
    for k in (8, 10, 12, 16, 20, 24, 32, 40, 48):
        for m in (20, 30, 40, 60, 80):
            row = {"K": k, "M": m, "requests_per_arm": k * m, "est_minutes_G0": round(minutes(k, m), 1)}
            for name, sc in (("base", base), ("pess", pess)):
                r = simulate(rng, P[sc["pool"]], k=k, m=m, scale=sc["scale"], seg_sd=sc["seg_sd"], mu=sc["mu"],
                             theta=0.0, n=4000)
                row[f"{name}_power_tost90"], row[f"{name}_power_strict95"] = r["tost90"], r["strict95"]
            grid.append(row)
            print(f"K={k:2d} M={m:2d} req/arm={k*m:4d} ~{row['est_minutes_G0']:5.1f} min | base tost {row['base_power_tost90']:.3f} "
                  f"s95 {row['base_power_strict95']:.3f} | pess tost {row['pess_power_tost90']:.3f} s95 {row['pess_power_strict95']:.3f}")
    out["grid"] = grid

    def choose(rule: str) -> dict | None:
        ok = [g for g in grid if g[f"base_power_{rule}"] >= 0.95 and g[f"pess_power_{rule}"] >= 0.80]
        return min(ok, key=lambda g: (g["requests_per_arm"], g["K"])) if ok else None
    out["chosen"] = {"tost90": choose("tost90"), "strict95": choose("strict95")}
    print("chosen:", json.dumps(out["chosen"]))

    # C3 + sensitivity at the chosen TOST configuration (and the strict one, if different)
    sens = []
    configs = {(c["K"], c["M"]) for c in out["chosen"].values() if c} | {(10, 30)}          # (10, 30) = "300 per arm"
    scen = [("clean", s, sd, mu, dr) for s in (1.0, 1.5, 2.0) for sd in (0.0, 0.25, 0.5, 1.0) for mu in (50.0, 58.0)
            for dr in (0.0,)] + [("clean", 1.0, 0.25, 50.0, 0.05), ("tail", 1.0, 0.25, 50.0, 0.0),
                                 ("tail", 1.5, 0.5, 50.0, 0.0)]
    for k, m in sorted(configs):
        for pool, s, sd, mu, dr in scen:
            delta = max(1.0, 0.02 * (mu + dr * (2 * k - 1) / 2))   # the rule's delta at the session-mean baseline
            row = {"K": k, "M": m, "pool": pool, "scale": s, "seg_sd": sd, "mu": mu, "drift_per_seg": dr, "delta": delta}
            for th_name, th in (("0", 0.0), ("0.25d", 0.25 * delta), ("0.5d", 0.5 * delta), ("+d", delta), ("-d", -delta)):
                n = 20000 if th_name in ("+d", "-d") else 4000
                r = simulate(rng, P[pool], k=k, m=m, scale=s, seg_sd=sd, mu=mu, theta=th, n=n, drift_per_seg=dr)
                row[f"theta_{th_name}"] = r
            sens.append(row)
            print(f"K={k} M={m} {pool} s={s} seg={sd} mu={mu} dr={dr}: pass@0 tost {row['theta_0']['tost90']:.3f} "
                  f"s95 {row['theta_0']['strict95']:.3f} | @0.5d {row['theta_0.5d']['tost90']:.3f} | size@+d tost "
                  f"{row['theta_+d']['tost90']:.4f} s95 {row['theta_+d']['strict95']:.4f} naive {row['theta_+d']['naive_welch90']:.4f}"
                  f" | @-d tost {row['theta_-d']['tost90']:.4f}")
    out["sensitivity"] = sens
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print("pool sd", out["pool_sd_ms"], "mad", out["pool_mad_ms"], "frozen false-fail", out["frozen_rule_false_fail_at_theta0"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
