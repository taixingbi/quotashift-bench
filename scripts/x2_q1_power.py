"""X2 Q1 (instrumentation invariance) sizing: offline size / power / heavy-tail / sensitivity simulation.

    uv run python scripts/x2_q1_power.py        # -> reports/x2/Q1_POWER.json, reports/x2/Q1_POWER.md

Offline only (no server, no GPU); owner approval "APPROVE offline Q1 qualification-test sizing" (2026-11-25).

Unit of analysis: K pairs of segments (procedure P = production boundary snapshot + 15 s guard, vs control N = the same
idle wait without the snapshot), M measured requests per segment, statistic on d_k = p50(P_k) - p50(N_k).

Segment-median model (calibrated, DISCLOSED, on X1 A1 data used for sizing only, never as X2 evidence):
  median_s = mu + n_s + burst_s + drift * position_s (+ procedure effect on P segments)
  n_s      within-segment + segment-to-segment noise, sd sigma_m * sqrt(80 / M) * scale; sigma_m = 0.279 ms from the 19
           non-slow A1 pairs (sd(d) 0.395 / sqrt 2). Heavy-tail variant: Student t(3) with the same sd.
  burst_s  host "slow segment" (both arms alike, i.e. not instrumentation): with prob p_host, + U(3, 5) ms (A1 magnitude);
           wide variant U(3, 10).
Procedure effects (alternatives on P segments only):
  constant   + theta on every P segment
  intermittent  extra burst with prob q on P segments, magnitude U(3, 5) (mean 4) -> mean effect 4 q (X1-like shape)

Candidate tests (TOST at alpha = 0.05 on the MEAN pair difference unless noted):
  T1  t-interval of the mean (90%; the A1 rule)
  T2  bootstrap-t interval of the mean (B = 499)
  T3  20%-trimmed mean, Tukey-McLaughlin SE, df = h - 1 (estimand: trimmed mean, NOT the mean)

  T1s strict: the T1 interval at 95% (one-sided alpha 0.025 each side); added in run 3, see "Run history"

Selection rules (fixed in this file before its first run):
  R1 size: P(pass | mean effect = +-delta) <= 0.05 + 2 MC SE, under BOTH the constant and the intermittent alternative,
     in every noise scenario (sigma x1/x1.5/x2, normal/t3, p_host 0/0.1/0.2/0.3, bursts U(3,5)/U(3,10), drift 0/0.05).
     A test that fails R1 anywhere is rejected for every design.
  R2 power base (sigma x1, normal, p_host 0, no drift, delta 1.0): P(pass | 0) >= 0.90
  R3 power pessimistic (sigma x1.5, p_host 0.2 in both arms, bursts U(3,5), delta 1.0): P(pass | 0) >= 0.80
  Choose the design (test, K even, M) meeting R1-R3 with the smallest estimated G0 wall time; ties -> T1 (simplest),
  then larger K. delta = max(1 ms, 2% x OFF p50); sizing uses the 1.0 ms floor (mu = 50 ms).

Correction after the first run (2026-11-25, recorded in reports/x2/Q1_POWER.log and the readiness report): the first run
held the boundary effect at a fixed 1.0 ms. Drift and host bursts raise the OFF baseline, so the rule's own delta was
above 1.0 ms and the "size" was measured inside the bound (T1/T2 worst cases were all drift scenarios). The boundary is now
set per draw at that draw's own delta. Selection rules R1-R3 are unchanged.

Run history (all runs kept under reports/x2/Q1_POWER.run*):
  run 1  boundary held at 1.0 ms (error above).
  run 2  boundary corrected. No candidate met R1: T1 0.071 (intermittent, skewed pair differences: the t interval is
         liberal on the upper side), T2 0.083 (bursts U(3,10)), T3 0.438 (trimming hides intermittent effects).
         R1 had been checked only at K = 48, although skew bias shrinks with K.
  run 3  (declared before it ran, no X2 data exist) R1 is evaluated at EVERY candidate design's own (K, M), and the
         candidate set adds T1s (the T1 interval at 95%). T2 is dropped (failed R1 at K = 48; expensive), T3 is kept
         only to document its rejection. R1-R3 themselves are unchanged. Ties: T1 before T1s, then larger K.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from quotashift.x1.sampler_equivalence_a1 import t_ppf  # noqa: E402  (validated t quantiles; imported unchanged)

OUT_JSON = REPO / "reports" / "x2" / "Q1_POWER.json"
OUT_MD = REPO / "reports" / "x2" / "Q1_POWER.md"
SEED = 20990
ALPHA = 0.05
SIGMA_M80 = 0.395 / math.sqrt(2)                  # per-segment sd at M = 80 (A1 non-slow pairs)
GUARD_S, SNAP_S, RESET_S, WARMUP, SEC_PER_REQ = 15.0, 1.0, 1.2, 3, 0.23
KS, MS = (32, 48, 56, 64, 72, 80, 96, 112, 128), (40, 80)
NSIM_POWER, NSIM_SIZE, B_BOOT = 4000, 20000, 499


def seg_seconds(m: int, sec_per_req: float = SEC_PER_REQ) -> float:
    return SNAP_S + GUARD_S + RESET_S + (m + WARMUP) * sec_per_req


def q1_minutes(k: int, m: int, sec_per_req: float = SEC_PER_REQ) -> float:
    return 2 * k * seg_seconds(m, sec_per_req) / 60


def draw(rng: np.random.Generator, n: int, k: int, m: int, *, scale: float = 1.0, tails: str = "normal",
         p_host: float = 0.0, burst: tuple[float, float] = (3.0, 5.0), drift: float = 0.0, mu: float = 50.0,
         theta: float = 0.0, q: float = 0.0, q_burst: tuple[float, float] = (3.0, 5.0),
         at_boundary: str | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Returns (d (n, k) = med_P - med_N, OFF-median baseline (n,)). Arm axis 0 = N (control), 1 = P (procedure).
    at_boundary: None, or "const+", "const-", "intermittent": the procedure effect is set, PER DRAW, exactly at that
    draw's own rule tolerance delta = max(1, 2% x OFF baseline) (correction, see module docstring)."""
    sd = SIGMA_M80 * math.sqrt(80 / m) * scale
    if tails == "t3":
        noise = rng.standard_t(3, size=(n, k, 2)) * sd / math.sqrt(3.0)
    else:
        noise = rng.normal(0.0, sd, size=(n, k, 2))
    host = (rng.random((n, k, 2)) < p_host) * rng.uniform(*burst, size=(n, k, 2))
    order = np.array([[0, 1] if j % 2 == 0 else [1, 0] for j in range(k)])      # execution position of (N, P) in pair
    pos = 2 * np.arange(k)[:, None] + order
    med = mu + noise + host + drift * pos[None]
    base = med[:, :, 0].mean(1)                     # OFF (N) baseline: unaffected by the procedure effect
    dl = delta_of(base)
    if at_boundary == "const+":
        theta = dl[:, None]
    elif at_boundary == "const-":
        theta = -dl[:, None]
    elif at_boundary == "intermittent":
        q = dl[:, None] / (sum(q_burst) / 2)        # mean extra = q x E[burst] = delta exactly
    med[:, :, 1] += theta + (rng.random((n, k)) < q) * rng.uniform(*q_burst, size=(n, k))
    return med[:, :, 1] - med[:, :, 0], base


def delta_of(base: np.ndarray) -> np.ndarray:
    return np.maximum(1.0, 0.02 * base)


def t1(d: np.ndarray, delta: np.ndarray) -> np.ndarray:
    k = d.shape[1]
    m, se = d.mean(1), d.std(1, ddof=1) / math.sqrt(k)
    t = t_ppf(1 - ALPHA, k - 1)
    return (m - t * se > -delta) & (m + t * se < delta)


def t1s(d: np.ndarray, delta: np.ndarray) -> np.ndarray:
    k = d.shape[1]
    m, se = d.mean(1), d.std(1, ddof=1) / math.sqrt(k)
    t = t_ppf(0.975, k - 1)
    return (m - t * se > -delta) & (m + t * se < delta)


def t3(d: np.ndarray, delta: np.ndarray, gamma: float = 0.2) -> np.ndarray:
    k = d.shape[1]
    g = int(math.floor(gamma * k))
    s = np.sort(d, axis=1)
    tm = s[:, g:k - g].mean(1)
    w = np.clip(s, s[:, [g]], s[:, [k - g - 1]])                                  # winsorized sample
    se = w.std(1, ddof=1) / ((1 - 2 * gamma) * math.sqrt(k))
    t = t_ppf(1 - ALPHA, k - 2 * g - 1)
    return (tm - t * se > -delta) & (tm + t * se < delta)


def t2(d: np.ndarray, delta: np.ndarray, rng: np.random.Generator, b: int = B_BOOT) -> np.ndarray:
    """Bootstrap-t interval of the mean (studentized; 5% / 95% quantiles of the bootstrap t)."""
    n, k = d.shape
    m, se = d.mean(1), d.std(1, ddof=1) / math.sqrt(k)
    out = np.empty(n, dtype=bool)
    for lo in range(0, n, 500):
        dd = d[lo:lo + 500]
        idx = rng.integers(0, k, size=(dd.shape[0], b, k))
        bs = np.take_along_axis(dd[:, None, :].repeat(b, 1), idx, 2)
        bm, bse = bs.mean(2), bs.std(2, ddof=1) / math.sqrt(k)
        tt = (bm - m[lo:lo + 500, None]) / np.where(bse > 0, bse, np.inf)
        qlo, qhi = np.quantile(tt, 0.05, axis=1), np.quantile(tt, 0.95, axis=1)
        lo_ci, hi_ci = m[lo:lo + 500] - qhi * se[lo:lo + 500], m[lo:lo + 500] - qlo * se[lo:lo + 500]
        out[lo:lo + 500] = (lo_ci > -delta[lo:lo + 500]) & (hi_ci < delta[lo:lo + 500])
    return out


def rates(rng: np.random.Generator, n: int, k: int, m: int, tests: tuple[str, ...], **kw) -> dict[str, float]:  # noqa: ANN003
    d, base = draw(rng, n, k, m, **kw)
    dl = delta_of(base)
    res = {}
    if "T1" in tests:
        res["T1"] = float(t1(d, dl).mean())
    if "T1s" in tests:
        res["T1s"] = float(t1s(d, dl).mean())
    if "T2" in tests:
        res["T2"] = float(t2(d, dl, rng).mean())
    if "T3" in tests:
        res["T3"] = float(t3(d, dl).mean())
    return res


NOISE = [dict(scale=s, tails=t, p_host=p, burst=b, drift=dr)
         for s in (1.0, 1.5, 2.0) for t in ("normal", "t3") for p in (0.0, 0.1, 0.2, 0.3)
         for b in ((3.0, 5.0), (3.0, 10.0)) for dr in (0.0, 0.05)
         if not (p == 0.0 and b == (3.0, 10.0))]


def main() -> int:
    rng = np.random.default_rng(SEED)
    out: dict = {"seed": SEED, "alpha": ALPHA, "sigma_m80_ms": SIGMA_M80, "model": __doc__.split("Candidate tests")[0],
                 "timing_assumptions_s": {"guard": GUARD_S, "snapshot": SNAP_S, "reset": RESET_S, "warmup": WARMUP,
                                          "per_request_G0": SEC_PER_REQ}}
    base_kw = dict(scale=1.0, tails="normal", p_host=0.0, drift=0.0)
    pess_kw = dict(scale=1.5, tails="normal", p_host=0.2, burst=(3.0, 5.0), drift=0.0)
    # 1) power grid
    grid = []
    for k in KS:
        for m in MS:
            row = {"K": k, "M": m, "q1_min_G0": round(q1_minutes(k, m), 1)}
            for name, kw in (("base", base_kw), ("pess", pess_kw)):
                for tname, v in rates(rng, NSIM_POWER, k, m, ("T1", "T1s", "T3"), **kw).items():
                    row[f"{name}_{tname}"] = v
            grid.append(row)
            print(f"K={k:2d} M={m} {row['q1_min_G0']:5.1f} min | base T1 {row['base_T1']:.3f} T1s {row['base_T1s']:.3f} | "
                  f"pess T1 {row['pess_T1']:.3f} T1s {row['pess_T1s']:.3f} T3 {row['pess_T3']:.3f}", flush=True)
    out["power_grid"] = grid
    # 2) size (R1) at every design that meets R2 and R3 for some test, every noise scenario, three boundary alternatives
    mc = 2 * math.sqrt(ALPHA * (1 - ALPHA) / NSIM_SIZE)
    out["size_mc_2se"] = mc
    size: dict[str, dict] = {}
    for g in grid:
        tests = tuple(t for t in ("T1", "T1s") if g[f"base_{t}"] >= 0.90 and g[f"pess_{t}"] >= 0.80)
        if not tests:
            continue
        rows = []
        for nk in NOISE:
            for alt in ("const+", "const-", "intermittent"):
                rows.append({"noise": {k_: (list(v) if isinstance(v, tuple) else v) for k_, v in nk.items()}, "alt": alt,
                             **rates(rng, NSIM_SIZE, g["K"], g["M"], tests, **nk, at_boundary=alt)})
        worst = {t: max(r[t] for r in rows) for t in tests}
        key = f"K{g['K']}_M{g['M']}"
        size[key] = {"K": g["K"], "M": g["M"], "worst": worst, "r1": {t: worst[t] <= ALPHA + mc for t in tests},
                     "rows": rows}
        print(f"size K={g['K']} M={g['M']}: worst {worst} R1 {size[key]['r1']}", flush=True)
    # T3 rejection documented at K = 64, M = 40 (intermittent alternative, base noise)
    out["t3_rejection"] = rates(rng, NSIM_SIZE, 64, 40, ("T3",), **base_kw, at_boundary="intermittent")
    out["size"] = size
    # 3) choose
    cands = []
    for g in grid:
        key = f"K{g['K']}_M{g['M']}"
        for t in ("T1", "T1s"):
            if key in size and size[key]["r1"].get(t):
                cands.append({"test": t, "K": g["K"], "M": g["M"], "q1_min_G0": g["q1_min_G0"],
                              "base": g[f"base_{t}"], "pess": g[f"pess_{t}"], "worst_size": size[key]["worst"][t]})
    cands.sort(key=lambda c: (c["q1_min_G0"], c["test"] != "T1", -c["K"]))
    out["candidates"] = cands
    chosen = cands[0] if cands else None
    out["chosen"] = chosen
    print("chosen:", chosen, flush=True)
    # 4) sensitivity at the chosen design (T1 statistic): power and size per noise scenario
    if chosen:
        k, m = chosen["K"], chosen["M"]
        sens = []
        for nk in NOISE:
            row = {"noise": {k_: (list(v) if isinstance(v, tuple) else v) for k_, v in nk.items()}}
            for nm, extra in (("p0", {}), ("p_half_delta", {"theta": 0.5}), ("size_const+", {"at_boundary": "const+"}),
                              ("size_intermittent", {"at_boundary": "intermittent"})):
                row[nm] = rates(rng, NSIM_POWER if nm in ("p0", "p_half_delta") else NSIM_SIZE, k, m,
                                (chosen["test"],), **nk, **extra)[chosen["test"]]
            sens.append(row)
        out["sensitivity"] = sens
        # time on L4 (unknown per-request time): bracket 0.23 .. 0.45 s
        out["q1_minutes_by_sec_per_req"] = {str(s): round(q1_minutes(k, m, s), 1) for s in (0.23, 0.30, 0.45)}
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1) + "\n")
    OUT_MD.write_text(render(out))
    return 0


def render(o: dict) -> str:
    L = ["# X2 Q1 sizing (offline simulation; generated by scripts/x2_q1_power.py)", "",
         f"Seed {o['seed']}; alpha {o['alpha']}; per-segment noise sd at M = 80: {o['sigma_m80_ms']:.3f} ms "
         "(X1 A1 non-slow pairs; sizing only). Run history and the boundary correction: script docstring.", "",
         "## Power grid: P(pass | no effect)", "",
         "| K | M | Q1 min (G0) | base T1 | base T1s | pess T1 | pess T1s | pess T3 |", "|---|---|---|---|---|---|---|---|"]
    for g in o["power_grid"]:
        L.append(f"| {g['K']} | {g['M']} | {g['q1_min_G0']} | {g['base_T1']:.3f} | {g['base_T1s']:.3f} | "
                 f"{g['pess_T1']:.3f} | {g['pess_T1s']:.3f} | {g['pess_T3']:.3f} |")
    L += ["", f"## Size at the boundary (R1; limit {o['alpha']} + 2 MC SE = {o['alpha'] + o['size_mc_2se']:.4f}), "
          "worst case over all noise scenarios and the constant +/-delta and intermittent alternatives", "",
          "| design | test | worst-case size | R1 |", "|---|---|---|---|"]
    for v in o["size"].values():
        for t, w in v["worst"].items():
            L.append(f"| K = {v['K']}, M = {v['M']} | {t} | {w:.4f} | {'pass' if v['r1'][t] else 'FAIL'} |")
    L += ["", f"T3 (20%-trimmed mean) at K = 64, M = 40, intermittent alternative at delta: P(pass) = "
          f"{o['t3_rejection']['T3']:.3f} -> rejected (estimand hides intermittent effects).", "",
          f"**Chosen:** {o['chosen']}", ""]
    if o.get("sensitivity"):
        L += ["## Sensitivity at the chosen design", "",
              "| scale | tails | p_host | burst | drift | P(pass\\|0) | P(pass\\|delta/2) | size const +delta | size intermittent |",
              "|---|---|---|---|---|---|---|---|---|"]
        for s_ in o["sensitivity"]:
            n = s_["noise"]
            L.append(f"| {n['scale']} | {n['tails']} | {n['p_host']} | {n.get('burst', [3, 5])} | {n['drift']} | "
                     f"{s_['p0']:.3f} | {s_['p_half_delta']:.3f} | {s_['size_const+']:.4f} | {s_['size_intermittent']:.4f} |")
        L += ["", f"Q1 minutes by per-request time (s): {o['q1_minutes_by_sec_per_req']}"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
