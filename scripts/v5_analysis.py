"""Protocol v5 pre-registered decision rules (docs/PROTOCOL_V5_DRAFT.md §4–§6). FROZEN with the v5 freeze commit.

This module holds the statistical decision rules as pure functions so they can be unit-tested on synthetic inputs
before any v5 GPU run. The run-level loader (reading v5 reports into the per-seed tables below) is listed in §9 as an
implementation prerequisite and must be added before the freeze; nothing here reads v5 data.

Per-seed inputs, per (comparison, L, C) cell:
  log_ratio[seed]   = log(mean victim user-facing TTFT, attack) - log(same, control)          (primary)
  E[seed]           = execution feasibility of the pair (both arms)                           (§4.1)
  Vb[seed]          = baseline victim-SLO feasibility: CONTROL-arm victim offered SLO success >= 0.95 (§4.2)
  slo_attack, slo_control = victim offered-load SLO success per arm (attack-arm degradation is an OUTCOME, §4.3)
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product

THRESHOLD = 1.25
EQ_LO, EQ_HI = math.log(0.8), math.log(1.25)    # equivalence / null band on the log ratio (= +-log 1.25)
ALPHA = 0.05
SLO_BASELINE_MIN = 0.95
COMPLETION_MIN, CENSOR_MAX = 0.95, 0.05
SPEARMAN_MIN = 0.6


# ---------------------------------------------------------------- Student t (no scipy)
def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the regularized incomplete beta (Lentz; Numerical Recipes betacf)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)), -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1.0 + aa * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + aa / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1.0) < 1e-14:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lb = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x)
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lb) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lb) * _betacf(b, a, 1.0 - x) / b


def t_cdf(t: float, df: int) -> float:
    x = df / (df + t * t)
    tail = 0.5 * _betai(df / 2.0, 0.5, x)
    return 1.0 - tail if t > 0 else tail


def t_ppf(p: float, df: int) -> float:
    lo, hi = -100.0, 100.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------- summaries
@dataclass(frozen=True)
class MeanCI:
    n: int
    mean: float
    se: float
    lo95: float
    hi95: float
    lo90: float
    hi90: float

    @property
    def ratio(self) -> float:
        return math.exp(self.mean)

    @property
    def half_width95(self) -> float:
        return (self.hi95 - self.lo95) / 2


def mean_ci(x: Sequence[float]) -> MeanCI:
    n = len(x)
    if n < 2:
        raise ValueError("need >= 2 seeds")
    m = sum(x) / n
    sd = math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1))
    se = sd / math.sqrt(n)
    t95, t90 = t_ppf(0.975, n - 1), t_ppf(0.95, n - 1)
    return MeanCI(n, m, se, m - t95 * se, m + t95 * se, m - t90 * se, m + t90 * se)


# ---------------------------------------------------------------- §4 feasibility
def execution_feasible(*, integrity_ok: bool, completion: tuple[float, float], censoring: tuple[float, float]) -> bool:
    """E: every fail-severity gate passed AND competitor completion >= 0.95 AND victim censoring <= 0.05 in BOTH arms."""
    return integrity_ok and min(completion) >= COMPLETION_MIN and max(censoring) <= CENSOR_MAX


def baseline_victim_slo_feasible(slo_control: float) -> bool:
    """Vb (baseline victim-SLO feasibility): the CONTROL arm's victim offered-load SLO success >= 0.95.
    It qualifies the operating point; it never uses the attack arm (attack-arm SLO is an outcome, §4.3)."""
    return slo_control >= SLO_BASELINE_MIN


def stratum(E: Sequence[bool], Vb: Sequence[bool]) -> str:  # noqa: N803
    """Cell stratum. Primary analyses use only 'E&Vb' cells; a cell needs every seed E, and every seed Vb."""
    if not all(E):
        return "notE"          # invalid (whole cell; no seed dropping)
    return "E&Vb" if all(Vb) else "E&notVb"   # E&notVb = victim-overloaded baseline, reported separately


def attack_slo_degradation(slo_attack: Sequence[float], slo_control: Sequence[float]) -> dict:
    """§4.3 outcome: per-seed paired difference (attack - control) in victim offered SLO success, mean + 95% CI."""
    d = [a - c for a, c in zip(slo_attack, slo_control, strict=True)]
    ci = mean_ci(d)
    return {"mean_diff": ci.mean, "ci95": [ci.lo95, ci.hi95], "per_seed": d}


# ---------------------------------------------------------------- §6 primary classification per cell
def classify_cell(log_ratios: Sequence[float]) -> dict:
    """Two-sided superiority vs the 1.25 band, plus TOST equivalence. Reported for every cell (not only H-tests).
    supported_increase: 95% CI lower bound > log 1.25; supported_decrease: upper < log 0.8;
    equivalent: 90% CI inside [log 0.8, log 1.25] (TOST at alpha 0.05); otherwise inconclusive."""
    ci = mean_ci(log_ratios)
    if ci.lo95 > EQ_HI:
        c = "supported_increase"
    elif ci.hi95 < EQ_LO:
        c = "supported_decrease"
    elif ci.lo90 >= EQ_LO and ci.hi90 <= EQ_HI:
        c = "equivalent"
    else:
        c = "inconclusive"
    return {"classification": c, "ratio": ci.ratio, "ci95": [math.exp(ci.lo95), math.exp(ci.hi95)],
            "ci90": [math.exp(ci.lo90), math.exp(ci.hi90)], "n": ci.n}


def p_superiority(log_ratios: Sequence[float]) -> float:
    """One-sided p for H: mean log ratio > log 1.25."""
    ci = mean_ci(log_ratios)
    return 1.0 - t_cdf((ci.mean - EQ_HI) / ci.se, ci.n - 1) if ci.se > 0 else float(ci.mean <= EQ_HI)


def p_tost(log_ratios: Sequence[float]) -> float:
    """TOST p = max of the two one-sided p values against log 0.8 and log 1.25."""
    ci = mean_ci(log_ratios)
    if ci.se == 0:
        return 0.0 if EQ_LO < ci.mean < EQ_HI else 1.0
    p_lo = 1.0 - t_cdf((ci.mean - EQ_LO) / ci.se, ci.n - 1)
    p_hi = t_cdf((ci.mean - EQ_HI) / ci.se, ci.n - 1)
    return max(p_lo, p_hi)


def threshold_above_noise(aa_log_ratios: Sequence[float]) -> bool:
    """1.25 is a valid threshold at (C, L) only if log 1.25 > 2 x the A/A-ind 95% half-width (log scale)."""
    return EQ_HI > 2 * mean_ci(aa_log_ratios).half_width95


# ---------------------------------------------------------------- H2a dose-response (separate from H2b)
def per_seed_slopes(by_cap: dict[int, Sequence[float]]) -> list[float]:
    """OLS slope of the per-seed log ratio on log2(C), one slope per seed (seeds are paired across caps)."""
    caps = sorted(by_cap)
    xs = [math.log2(c) for c in caps]
    xm = sum(xs) / len(xs)
    sxx = sum((x - xm) ** 2 for x in xs)
    n = len(by_cap[caps[0]])
    out = []
    for i in range(n):
        ys = [by_cap[c][i] for c in caps]
        ym = sum(ys) / len(ys)
        out.append(sum((x - xm) * (y - ym) for x, y in zip(xs, ys, strict=True)) / sxx)
    return out


def sign_flip_p(slopes: Sequence[float]) -> float:
    """Exact one-sided sign-flip permutation p for H: mean slope < 0 (2^n flips; n = 10 -> 1024)."""
    obs = sum(slopes) / len(slopes)
    hits = tot = 0
    for signs in product((1, -1), repeat=len(slopes)):
        tot += 1
        hits += (sum(s * v for s, v in zip(signs, slopes, strict=True)) / len(slopes)) <= obs + 1e-15
    return hits / tot


def h2a_dose_response(by_cap: dict[int, Sequence[float]]) -> dict:
    """H2a: amplification decreases with the cap. SUPPORTED iff the mean per-seed slope < 0 with one-sided t p < alpha
    AND exact sign-flip p < alpha. NOT SUPPORTED otherwise. Inputs must be the three E&Vb gateway cells."""
    sl = per_seed_slopes(by_cap)
    ci = mean_ci(sl)
    p_t = t_cdf(ci.mean / ci.se, ci.n - 1) if ci.se > 0 else float(ci.mean >= 0)
    p_perm = sign_flip_p(sl)
    p = max(p_t, p_perm)
    return {"mean_slope_per_doubling": ci.mean, "slope_ci95": [ci.lo95, ci.hi95], "p_t": p_t, "p_perm": p_perm,
            "p": p, "supported": p < ALPHA, "ratio_change_per_doubling": math.exp(ci.mean)}


def h2b_equivalence_c32(log_ratios_c32: Sequence[float], aa_c32: Sequence[float]) -> dict:
    """H2b: at C = 32 the D-vs-S ratio is equivalent to 1 (TOST, band [0.8, 1.25]). Separate hypothesis, separate
    test. EQUIVALENT iff TOST p < alpha (90% CI inside the band) AND the threshold is above the A/A-ind noise at C=32.
    'not_equivalent' iff the 95% CI lies entirely outside the band; otherwise 'inconclusive'."""
    ci = mean_ci(log_ratios_c32)
    p = p_tost(log_ratios_c32)
    noise_ok = threshold_above_noise(aa_c32)
    if p < ALPHA and noise_ok:
        v = "equivalent"
    elif ci.lo95 > EQ_HI or ci.hi95 < EQ_LO:
        v = "not_equivalent"
    else:
        v = "inconclusive" if noise_ok else "threshold_not_above_noise"
    return {"verdict": v, "p_tost": p, "ratio": ci.ratio, "ci90": [math.exp(ci.lo90), math.exp(ci.hi90)],
            "threshold_above_noise": noise_ok}


def holm(pvals: dict[str, float], alpha: float = ALPHA) -> dict[str, bool]:
    """Holm step-down; returns reject (True) per hypothesis."""
    order = sorted(pvals, key=pvals.get)  # type: ignore[arg-type]
    rej, m, stop = {}, len(order), False
    for i, k in enumerate(order):
        stop = stop or pvals[k] > alpha / (m - i)
        rej[k] = not stop
    return rej


# ---------------------------------------------------------------- H3 FCFS prediction scoring
def score_fcfs(pred_seed: Sequence[float], obs_seed: Sequence[float], tol_seed: Sequence[float],
               pred_cell: float, tol_cell: float) -> dict:
    """H3 per (cell, arm). PASS iff |mean_obs - mean_pred| <= tol_cell AND >= 8/10 seeds within their tolerance.
    Reports MAE, signed bias, RMSE (ms) and the fraction of seeds within tolerance."""
    err = [o - p for o, p in zip(obs_seed, pred_seed, strict=True)]
    within = [abs(e) <= t for e, t in zip(err, tol_seed, strict=True)]
    mean_obs = sum(obs_seed) / len(obs_seed)
    k_needed = math.ceil(0.8 * len(err))
    return {"mae_ms": sum(abs(e) for e in err) / len(err), "bias_ms": sum(err) / len(err),
            "rmse_ms": math.sqrt(sum(e * e for e in err) / len(err)), "seeds_within": sum(within),
            "cell_error_ms": mean_obs - pred_cell,
            "pass": abs(mean_obs - pred_cell) <= tol_cell and sum(within) >= k_needed}


# ---------------------------------------------------------------- H4 engine queue (histogram semantics, §5.2)
def engine_queue_negligible(queue_sum_s: float, queue_count: float, buckets: Sequence[tuple[float | str, float]],
                            *, mean_max_s: float = 0.010) -> dict:
    """H4 engine-queue criterion on ENGINE-GLOBAL, finish-time observations (all finished requests of the arm, all
    tenants; aborted requests are not observed): mean (sum/count) <= 10 ms AND every observation in the le=0.3 s bucket.
    A per-request or per-victim engine queue P95 is NOT identifiable from this histogram."""
    if queue_count <= 0:
        return {"evaluable": False}
    le03 = next((c for le, c in buckets if le != "+Inf" and float(le) == 0.3), None)
    return {"evaluable": le03 is not None, "mean_s": queue_sum_s / queue_count,
            "frac_le_0p3s": None if le03 is None else le03 / queue_count,
            "negligible": le03 is not None and queue_sum_s / queue_count <= mean_max_s and le03 >= queue_count}
