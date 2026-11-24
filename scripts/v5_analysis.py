"""Protocol v5 pre-registered decision rules (docs/PROTOCOL_V5.md §4–§6). FROZEN with the v5 freeze commit.

This module holds the statistical decision rules as pure functions so they can be unit-tested on synthetic inputs
before any v5 GPU run, plus the run-level loader (§9 item 8, bottom of the file) that reads v5 experiment reports
into the per-seed tables below, applies every rule, and writes reports/v5/ANALYSIS_<stage>.{md,json}:

    uv run python scripts/v5_analysis.py --stage A            # reports/v5/stage_a  -> reports/v5/ANALYSIS_A.md
    uv run python scripts/v5_analysis.py --stage B            # stage_a + stage_b   -> reports/v5/ANALYSIS_B.md

Read-only on reports/ and results/. It refuses an incomplete stage on real data (§6: no interim looks) and refuses to
overwrite an existing analysis without --force.

Per-seed inputs, per (comparison, L, C) cell:
  log_ratio[seed]   = log(mean victim user-facing TTFT, attack) - log(same, control)          (primary)
  Primary estimand: the GEOMETRIC MEAN of the per-seed attack/control ratios, exp(mean_s log_ratio[seed]), with a
  95% t interval on the log scale back-transformed. Every "ratio" this module reports for a cell is that geometric
  mean (`MeanCI.ratio`); it is not the ratio of arm means.
  E[seed]           = execution feasibility of the pair (both arms)                           (§4.1)
  Vb[seed]          = baseline victim-SLO feasibility: CONTROL-arm victim offered SLO success >= 0.95 (§4.2)
  slo_attack, slo_control = victim offered-load SLO success per arm (attack-arm degradation is an OUTCOME, §4.3)
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_v5  # noqa: E402
from v4_posthoc_slot_time import k_at, occupancy_steps, spearman, time_weighted  # noqa: E402
from v5_fcfs_predictions import holds  # noqa: E402  (H3 observed = the prediction's own definition)

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
    """Exact one-sided sign-flip permutation p for H: mean slope < 0 (2^n flips; n = 10 -> 1024).
    Valid under a SIGN-SYMMETRIC null: per-seed values independent and each symmetric about 0 (stronger than mean 0);
    hence the decision rules combine it with the t-test by max(p_t, p_perm) (PROTOCOL_V5 §6). The observed sign vector
    is counted (minimum p = 2^-n); ties with the observed mean count as extreme; exact zeros are flip-invariant."""
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


def h4a_backend_relocation(backend_c8: Sequence[float], backend_c32: Sequence[float]) -> dict:
    """H4(a): attack-arm victim mean backend TTFT at C = 32 exceeds C = 8. One-sided paired t on per-seed log ratios
    (C32 / C8), alpha 0.05. Seeds are paired across caps (same frozen schedule)."""
    lr = [math.log(b) - math.log(a) for a, b in zip(backend_c8, backend_c32, strict=True)]
    ci = mean_ci(lr)
    p = 1.0 - t_cdf(ci.mean / ci.se, ci.n - 1) if ci.se > 0 else float(ci.mean <= 0)
    return {"ratio_c32_over_c8": ci.ratio, "ci95": [math.exp(ci.lo95), math.exp(ci.hi95)], "p": p,
            "supported": p < ALPHA}


def h4b_queue_reduction(queue_c8: Sequence[float], queue_c32: Sequence[float]) -> dict:
    """H4(b): attack-arm victim mean gateway queue (ms) falls from C = 8 to C = 32. Separate from H3: it is scored
    on the observed paired reduction alone, never on FCFS prediction accuracy.
    Per seed d_s = q8_s - q32_s (same frozen schedule at both caps). SUPPORTED iff the one-sided paired t p (H: mean
    d > 0) < alpha AND the exact one-sided sign-flip p < alpha; p = max of the two (as H2a; robust to the heavy right
    tail of queue differences). Reported: mean d with its 95% t CI (ms)."""
    d = [a - b for a, b in zip(queue_c8, queue_c32, strict=True)]
    ci = mean_ci(d)
    p_t = 1.0 - t_cdf(ci.mean / ci.se, ci.n - 1) if ci.se > 0 else float(ci.mean <= 0)
    p_perm = sign_flip_p([-x for x in d])     # sign_flip_p tests mean < 0
    p = max(p_t, p_perm)
    return {"mean_reduction_ms": ci.mean, "ci95_ms": [ci.lo95, ci.hi95], "per_seed_reduction_ms": d, "p_t": p_t,
            "p_perm": p_perm, "p": p, "supported": p < ALPHA}


# ================================================================ run-level loader (§9 item 8)

PREDICTIONS = REPO / "experiments" / "v5" / "FCFS_PREDICTIONS.json"
CELL_RE = re.compile(r"v5_(aa_ind|decode_vs_short|prefill_vs_short)_L(\d+)_(?:C(\d+)|(direct))(__r2)?")
TAIL_MS = (500.0, 2000.0)
SEEDS = list(range(build_v5.SEED0, build_v5.SEED0 + build_v5.REPS))
H5_RHO_MIN = SPEARMAN_MIN


def expected_cells(stage: str) -> list[str]:
    """Cells a stage analysis needs: A = the 12 L = 200 cells; B = A plus the 7 L = 400 cells."""
    out = []
    for st in ("A", "B")[: 1 if stage == "A" else 2]:
        load, comps = build_v5.STAGES[st]
        for comp in comps:
            out += [build_v5.cell_id(comp, load, c) for c in build_v5.CAPS]
            if comp in build_v5.DIRECT[st]:
                out.append(build_v5.cell_id(comp, load, None))
    return out


def _resolve_run(d: str) -> Path:
    p = Path(d)
    if p.exists():
        return p
    i = p.parts.index("results") if "results" in p.parts else None
    return REPO.joinpath(*p.parts[i:]) if i is not None else p


def _victims(run: Path) -> pd.DataFrame:
    """Completed post-warm-up victims with user TTFT (ms): the population of run_metrics' victim means."""
    summ = json.loads((run / "metrics_summary.json").read_text())
    r = pd.read_parquet(run / "requests.parquet")
    r = r[(r.trace_arrival_s >= float(summ.get("warmup_s") or 0.0)) & (r.workload_class == "victim")
          & (r.terminal_status == "completed")]
    return pd.DataFrame({"user_ttft_ms": (r.t_first_token - r.t_offered) * 1000.0})


def slot_time(run: Path, cap: int) -> dict:
    """H5 inputs on the frozen slot-time primitives, thresholded at the run's OWN cap C (v4 used the reference 8):
    fraction of the window at C/C and fraction of victims arriving while k >= C. Also the H3 observable."""
    cfg = yaml.safe_load((run / "config.resolved.yaml").read_text())
    T = float(cfg.get("runtime_seconds") or build_v5.RUNTIME)
    r = holds(run)
    times, k = occupancy_steps(r)
    occ = time_weighted(times, k, 0.0, T) if len(times) else {}
    vic = r[r.workload_class == "victim"]
    sat = k_at(times, k, vic.t_offered.to_numpy() - 1e-9) >= cap if len(times) else np.zeros(len(vic), bool)
    return {"frac_time_at_cap": float(sum(p for kk, p in occ.items() if kk >= cap)),
            "victim_arrivals_during_saturation": float(sat.mean()) if len(sat) else float("nan"),
            "occ_max": int(k.max()) if len(k) else 0,
            "h3_obs_victim_queue_mean_ms": float(((vic.t_sent - vic.t_offered) * 1000).mean()) if len(vic) else float("nan")}


def _engine_queue(run: Path) -> dict:
    ec = (json.loads((run / "metrics_summary.json").read_text()).get("engine_counters") or {})
    return {"sum_s": ec.get("queue_time_seconds_sum"), "count": ec.get("queue_time_seconds_count"),
            "buckets": ec.get("queue_time_seconds_buckets")}


def _rel(p: Path) -> str:
    """Repo-relative path for anything written into a committed analysis (no absolute local paths)."""
    q = p.resolve()
    return str(q.relative_to(REPO)) if REPO in q.parents else str(p)


def load_cell(rep: Path) -> dict:
    """One v5 experiment report -> per-seed table and cell metadata. Integrity = every fail-severity gate passed."""
    m = CELL_RE.fullmatch(rep.name)
    if not m:
        raise ValueError(f"not a v5 cell report: {rep}")
    comp, load, cap, direct = m.group(1), int(m.group(2)), m.group(3), m.group(4)
    man = json.loads((rep / "manifest.json").read_text())
    df = pd.read_csv(rep / "summary.csv")
    checks = (man.get("validity") or {}).get("checks") or []
    failed = [c["name"] for c in checks if c.get("severity") == "fail" and not c.get("passed")]
    integrity_ok = bool(checks) and not failed
    C = None if direct else int(cap)
    rows = []
    for seed in sorted(int(s) for s in df.seed.unique()):
        a = df[(df.seed == seed) & (df.arm == "attack")].iloc[0]
        c = df[(df.seed == seed) & (df.arm == "control")].iloc[0]
        comp_done = (a.competitor_requests / a.competitor_offered, c.competitor_requests / c.competitor_offered)
        cens = (a.victim_censored_fraction, c.victim_censored_fraction)
        row = {"seed": seed, "integrity_ok": integrity_ok,
               "E": execution_feasible(integrity_ok=integrity_ok, completion=comp_done, censoring=cens),
               "Vb": baseline_victim_slo_feasible(float(c.victim_slo_success_offered)),
               "competitor_completion": list(map(float, comp_done)), "victim_censored": list(map(float, cens)),
               "log_ratio": math.log(a.victim_user_ttft_mean_ms) - math.log(c.victim_user_ttft_mean_ms),
               "log_ratio_p95": math.log(a.victim_user_ttft_p95_ms) - math.log(c.victim_user_ttft_p95_ms)}
        for arm, r in (("attack", a), ("control", c)):
            run = _resolve_run(r.run_dir)
            v = _victims(run)
            row[arm] = {
                "user_ttft_mean_ms": float(r.victim_user_ttft_mean_ms), "user_ttft_p95_ms": float(r.victim_user_ttft_p95_ms),
                "backend_ttft_mean_ms": float(r.victim_backend_ttft_mean_ms),
                "backend_ttft_p95_ms": float(r.victim_backend_ttft_p95_ms),
                "gateway_queue_mean_ms": float(r.victim_gateway_queue_mean_ms),
                "gateway_queue_p95_ms": float(r.victim_gateway_queue_p95_ms),
                "slo_success": float(r.victim_slo_success_offered), "tpot_p95_ms": float(r.victim_tpot_p95_ms),
                **{f"frac_user_ttft_gt_{int(t)}ms": float((v.user_ttft_ms > t).mean()) if len(v) else float("nan")
                   for t in TAIL_MS},
                "gpu_dynamic_energy_j_per_realized_tok": (float(r.gpu_dynamic_energy_j) / float(r.realized_tokens)
                                                          if pd.notna(r.gpu_dynamic_energy_j) and r.realized_tokens else None),
                "engine_queue": _engine_queue(run),
                "slot": slot_time(run, C if C is not None else build_v5.CAPS[0]),
                "configured_cap": None if pd.isna(r.gw_inflight_cap) else int(r.gw_inflight_cap),
                "path": r.path,
            }
        rows.append(row)
    return {"cell": build_v5.base_id(rep.name), "rerun": rep.name.endswith(build_v5.RERUN), "comparison": comp, "L": load, "C": C, "path": "direct" if direct else "gateway",
            "report": _rel(rep), "synthetic_backend": bool(man.get("synthetic_backend")), "failed_gates": failed,
            "server_start": list((man.get("provenance") or {}).get("server_start") or []),
            "seeds": [r["seed"] for r in rows], "rows": rows}


def server_identity(cells: dict[str, dict]) -> dict:
    """Stage gate `server_identity` (§5.1, fail): one vLLM process_start_time_seconds across every block of a stage
    (§1: one server start per stage; checked separately for stage A = L 200 and stage B = L 400). A failure in a stage
    invalidates that stage's cells. Not applicable to the mock."""
    if cells and all(c["synthetic_backend"] for c in cells.values()):
        return {"passed": True, "applicable": False, "detail": "synthetic backend: no server identity", "failed_stages": []}
    by_stage: dict[str, set[str]] = {}
    for c in cells.values():
        st = next(k for k, (load, _) in build_v5.STAGES.items() if load == c["L"])
        by_stage.setdefault(st, set()).update(c["server_start"] or ["None"])
    bad = sorted(st for st, ss in by_stage.items() if len(ss) != 1 or "None" in ss)
    return {"passed": not bad, "applicable": True, "failed_stages": bad,
            "server_starts": {st: sorted(ss) for st, ss in sorted(by_stage.items())},
            "detail": "; ".join(f"stage {st}: {sorted(ss)}" for st, ss in sorted(by_stage.items()))}


def summarize_cell(cell: dict) -> dict:
    rows = cell["rows"]
    lr = [r["log_ratio"] for r in rows]
    out = {"stratum": stratum([r["E"] for r in rows], [r["Vb"] for r in rows]), "n": len(rows),
           "primary": classify_cell(lr), "p95_ratio": classify_cell([r["log_ratio_p95"] for r in rows]),
           "attack_slo_degradation": attack_slo_degradation([r["attack"]["slo_success"] for r in rows],
                                                            [r["control"]["slo_success"] for r in rows])}
    for t in TAIL_MS:
        k = f"frac_user_ttft_gt_{int(t)}ms"
        d = [r["attack"][k] - r["control"][k] for r in rows]
        ci = mean_ci(d)
        out[f"tail_diff_gt_{int(t)}ms"] = {"mean_diff": ci.mean, "ci95": [ci.lo95, ci.hi95]}
    for arm in ("attack", "control"):
        out[f"{arm}_means"] = {k: float(np.mean([r[arm][k] for r in rows])) for k in
                               ("user_ttft_mean_ms", "backend_ttft_mean_ms", "gateway_queue_mean_ms",
                                "gateway_queue_p95_ms", "slo_success")}
    return out


def _cell_ok(cells: dict, cid: str) -> bool:
    return cid in cells and cells[cid]["summary"]["stratum"] == "E&Vb"


def analyse(cells: dict[str, dict], stage: str) -> dict:
    """Apply every pre-registered rule (§3, §6) to loaded cells. Non-evaluable hypotheses enter their Holm family with
    p = 1 (family size fixed; conservative) and are reported as not evaluable."""
    for c in cells.values():
        c["summary"] = summarize_cell(c)
    cid = build_v5.cell_id
    res: dict = {"stage": stage, "cells": {}}
    # threshold validity per cell vs A/A-ind at the same (C, L)
    for c in cells.values():
        aa = cid("aa_ind", c["L"], c["C"])
        c["summary"]["threshold_above_noise"] = (threshold_above_noise([r["log_ratio"] for r in cells[aa]["rows"]])
                                                 if aa in cells else None)
    # ---- F1: H1, H2a, H2b (L = 200)
    ds = {C: cid("decode_vs_short", 200, C) for C in build_v5.CAPS}
    f1_p, hyp = {}, {}
    if _cell_ok(cells, ds[8]):
        lr = [r["log_ratio"] for r in cells[ds[8]]["rows"]]
        f1_p["H1"] = p_superiority(lr)
        hyp["H1"] = {"evaluable": True, "p": f1_p["H1"], **classify_cell(lr)}
    else:
        f1_p["H1"], hyp["H1"] = 1.0, {"evaluable": False, "reason": f"{ds[8]} not in stratum E&Vb"}
    if all(_cell_ok(cells, ds[C]) for C in build_v5.CAPS) and len({tuple(cells[ds[C]]["seeds"]) for C in build_v5.CAPS}) == 1:
        h = h2a_dose_response({C: [r["log_ratio"] for r in cells[ds[C]]["rows"]] for C in build_v5.CAPS})
        f1_p["H2a"], hyp["H2a"] = h["p"], {"evaluable": True, **h}
    else:
        f1_p["H2a"], hyp["H2a"] = 1.0, {"evaluable": False, "reason": "not all three D-vs-S L200 gateway cells E&Vb "
                                                                        "with identical seeds"}
    aa32 = cid("aa_ind", 200, 32)
    if _cell_ok(cells, ds[32]) and aa32 in cells:
        h = h2b_equivalence_c32([r["log_ratio"] for r in cells[ds[32]]["rows"]], [r["log_ratio"] for r in cells[aa32]["rows"]])
        f1_p["H2b"], hyp["H2b"] = h["p_tost"], {"evaluable": True, **h}
    else:
        f1_p["H2b"], hyp["H2b"] = 1.0, {"evaluable": False, "reason": f"{ds[32]} not E&Vb or {aa32} missing"}
    rej = holm(f1_p)
    for k in ("H1", "H2a", "H2b"):
        hyp[k]["holm_reject"] = rej[k] and hyp[k]["evaluable"]
    hyp["H1"]["verdict"] = "supported" if hyp["H1"]["holm_reject"] else ("not_supported" if hyp["H1"]["evaluable"] else "not_evaluable")
    hyp["H2a"]["verdict"] = "supported" if hyp["H2a"]["holm_reject"] else ("not_supported" if hyp["H2a"]["evaluable"] else "not_evaluable")
    if hyp["H2b"]["evaluable"]:
        v = hyp["H2b"]["verdict"]
        hyp["H2b"]["verdict"] = "equivalent" if (v == "equivalent" and hyp["H2b"]["holm_reject"]) else (
            "inconclusive" if v == "equivalent" else v)
    else:
        hyp["H2b"]["verdict"] = "not_evaluable"
    # ---- H3: FCFS prediction scoring
    pred = json.loads(PREDICTIONS.read_text())["cells"]
    h3 = {}
    for k, pc in pred.items():
        if k not in cells:
            continue
        c = cells[k]
        for arm in ("attack", "control"):
            ps = {int(s): v[arm] for s, v in pc["seeds"].items()}
            seeds = c["seeds"]
            if any(s not in ps for s in seeds):
                h3[f"{k}/{arm}"] = {"evaluable": False, "reason": "seeds not in FCFS_PREDICTIONS.json"}
                continue
            obs = [r[arm]["slot"]["h3_obs_victim_queue_mean_ms"] for r in c["rows"]]
            pseed = [ps[s]["victim_queue_mean_ms"] for s in seeds]
            if sorted(seeds) == sorted(ps):   # the protocol case: the frozen cell values
                pcell, tcell = pc[f"{arm}_cell_victim_queue_mean_ms"], pc[f"{arm}_tolerance_cell_ms"]
            else:                             # plumbing subsets only: same cell rule over the loaded seeds
                rho = json.loads(PREDICTIONS.read_text())["tolerances"]["rho_rel"]
                pcell = float(np.mean(pseed))
                tcell = max(5.0, rho * pcell)
            sc = score_fcfs(pseed, obs, [ps[s]["tolerance_ms"] for s in seeds], pcell, tcell)
            h3[f"{k}/{arm}"] = {"evaluable": c["summary"]["stratum"] != "notE", "C": pc["C"], "L": pc["L"],
                                "validated_envelope": pc["validated_envelope"],
                                "pred_cell_ms": pcell, "obs_cell_ms": float(np.mean(obs)),
                                "frozen_cell_values": sorted(seeds) == sorted(ps), **sc}
    inenv = {k: v for k, v in h3.items() if v.get("validated_envelope")}
    c8 = [v for v in inenv.values() if v.get("C") == 8]
    hi = [v for v in inenv.values() if v.get("C") in (16, 32)]
    if not hi or not all(v["evaluable"] for v in [*c8, *hi]):
        h3v = "not_evaluable"
    elif not all(v["pass"] for v in c8):
        h3v = "model_not_calibrated_on_v5"
    else:
        h3v = "supported" if all(v["pass"] for v in hi) else "not_supported"
    hyp["H3"] = {"verdict": h3v, "scores": h3}
    # ---- H4 relocation (D vs S, L = 200)
    if all(ds[C] in cells and cells[ds[C]]["summary"]["stratum"] != "notE" for C in build_v5.CAPS) and len(
            {tuple(cells[ds[C]]["seeds"]) for C in build_v5.CAPS}) == 1:
        a = h4a_backend_relocation([r["attack"]["backend_ttft_mean_ms"] for r in cells[ds[8]]["rows"]],
                                   [r["attack"]["backend_ttft_mean_ms"] for r in cells[ds[32]]["rows"]])
        qs = {C: [r["attack"]["gateway_queue_mean_ms"] for r in cells[ds[C]]["rows"]] for C in build_v5.CAPS}
        b = h4b_queue_reduction(qs[8], qs[32]) | {
            "attack_victim_gateway_queue_cell_mean_ms": {C: float(np.mean(v)) for C, v in qs.items()},
            "descriptive_paired_reduction_ms": {f"C{x}-C{y}": (lambda ci: {"mean": ci.mean, "ci95": [ci.lo95, ci.hi95]})(
                mean_ci([u - w for u, w in zip(qs[x], qs[y], strict=True)])) for x, y in ((8, 16), (16, 32))},
            "h3_reported_separately": True}
        eq = {}
        for cc in [ds[C] for C in build_v5.CAPS] + [cid("decode_vs_short", 200, None)]:
            if cc not in cells:
                continue
            for r in cells[cc]["rows"]:
                for arm in ("attack", "control"):
                    e = r[arm]["engine_queue"]
                    eq[f"{cc}/{r['seed']}/{arm}"] = (engine_queue_negligible(e["sum_s"], e["count"], e["buckets"])
                                                    if e["count"] is not None and e["buckets"] is not None else {"evaluable": False})
        gw = {k: v for k, v in eq.items() if "_direct/" not in k}
        cev = bool(gw) and all(v.get("evaluable") for v in gw.values())
        cres = {"evaluable": cev, "negligible_all_gateway_arms": cev and all(v["negligible"] for v in gw.values()),
                "per_arm": eq}
        hyp["H4"] = {"a": a, "b": b, "c": cres,
                     "verdict": ("not_evaluable" if not cev else
                                 "supported" if a["supported"] and b["supported"] and cres["negligible_all_gateway_arms"]
                                 else "not_supported")}
    else:
        hyp["H4"] = {"verdict": "not_evaluable", "reason": "a D-vs-S L200 gateway cell is missing, not E, or the "
                                                            "caps' seed lists differ"}
    # ---- H5: explanatory CONSISTENCY test (all loaded gateway arms). It checks that victim queueing tracks the slot
    # saturation the FCFS account implies; it is not an independent or novel mechanism claim.
    pts = [(r[arm]["gateway_queue_mean_ms"], r[arm]["slot"]["frac_time_at_cap"], r[arm]["slot"]["victim_arrivals_during_saturation"])
           for c in cells.values() if c["path"] == "gateway" for r in c["rows"] for arm in ("attack", "control")]
    if len(pts) >= 3:
        qv, ft, va = zip(*pts, strict=True)
        rho_a, rho_b = spearman(qv, ft), spearman(qv, va)
        hyp["H5"] = {"n_arms": len(pts), "rho_frac_time_at_cap": rho_a, "rho_victims_during_saturation": rho_b,
                     "verdict": ("not_evaluable" if math.isnan(rho_a) or math.isnan(rho_b) else
                                 "supported" if rho_a >= H5_RHO_MIN and rho_b >= H5_RHO_MIN else "not_supported")}
    else:
        hyp["H5"] = {"verdict": "not_evaluable", "n_arms": len(pts)}
    # ---- F2: H6 P vs S equivalence at each cap (L = 200)
    f2_p, h6 = {}, {}
    for C in build_v5.CAPS:
        k = cid("prefill_vs_short", 200, C)
        if _cell_ok(cells, k):
            lr = [r["log_ratio"] for r in cells[k]["rows"]]
            f2_p[f"C{C}"] = p_tost(lr)
            h6[f"C{C}"] = {"evaluable": True, "p_tost": f2_p[f"C{C}"], **classify_cell(lr)}
        else:
            f2_p[f"C{C}"], h6[f"C{C}"] = 1.0, {"evaluable": False}
    rej2 = holm(f2_p)
    for k, v in h6.items():
        v["verdict"] = "equivalent" if (v["evaluable"] and rej2[k]) else ("not_equivalent_or_inconclusive" if v["evaluable"]
                                                                           else "not_evaluable")
    hyp["H6"] = h6
    # ---- H7 descriptive, every cell
    for k, c in sorted(cells.items()):
        res["cells"][k] = {kk: c[kk] for kk in ("comparison", "L", "C", "path", "seeds", "failed_gates", "synthetic_backend",
                                                "rerun")} | {
            "summary": c["summary"], "per_seed": c["rows"]}
    res["hypotheses"] = hyp
    res["synthetic_backend"] = any(c["synthetic_backend"] for c in cells.values())
    res["seed_set_matches_protocol"] = all(c["seeds"] == SEEDS for c in cells.values())
    return res


def _fmt(x: object, d: int = 3) -> str:
    return f"{x:.{d}f}" if isinstance(x, float) and math.isfinite(x) else str(x)


def render_md(res: dict) -> str:
    L = [f"# Protocol v5 analysis, stage {res['stage']}", ""]
    if res["synthetic_backend"]:
        L += ["> **SYNTHETIC BACKEND (mock): plumbing evidence only, never GPU measurements.**", ""]
    if not res["seed_set_matches_protocol"]:
        L += [f"> Seed set differs from the protocol's {SEEDS[0]}–{SEEDS[-1]}; not a protocol result.", ""]
    sg = res.get("stage_gates", {}).get("server_identity")
    if sg and not sg["passed"]:
        L += [f"> **STAGE {', '.join(sg['failed_stages'])} INVALID: server_identity failed ({sg['detail']}); "
              "its cells are ¬E.**", ""]
    L += ["Rules: `docs/PROTOCOL_V5.md` §3–§6, implemented in `scripts/v5_analysis.py`. No seed exclusion.", "",
          "## Hypotheses", "", "| Hypothesis | Verdict | Detail |", "|---|---|---|"]
    h = res["hypotheses"]
    for k in ("H1", "H2a", "H2b"):
        v = h[k]
        det = (f"ratio {_fmt(v.get('ratio'))}, p {_fmt(v.get('p', v.get('p_tost')), 4)}, Holm reject {v['holm_reject']}"
               if v["evaluable"] else v["reason"])
        if k == "H2a" and v["evaluable"]:
            det = (f"ratio change per doubling {_fmt(v['ratio_change_per_doubling'])}, p_t {_fmt(v['p_t'], 4)}, "
                   f"p_perm {_fmt(v['p_perm'], 4)}, Holm reject {v['holm_reject']}")
        L.append(f"| {k} (F1) | **{v['verdict']}** | {det} |")
    L.append(f"| H3 (FCFS predictions) | **{h['H3']['verdict']}** | {len(h['H3']['scores'])} (cell, arm) scores |")
    h4 = h["H4"]
    L.append(f"| H4 (relocation) | **{h4['verdict']}** | " + (
        f"(a) backend C32/C8 {_fmt(h4['a']['ratio_c32_over_c8'])} p {_fmt(h4['a']['p'], 4)}; (b) queue reduction "
        f"C8−C32 {_fmt(h4['b']['mean_reduction_ms'], 1)} ms [{_fmt(h4['b']['ci95_ms'][0], 1)}, "
        f"{_fmt(h4['b']['ci95_ms'][1], 1)}] p {_fmt(h4['b']['p'], 4)} → {h4['b']['supported']}; "
        f"(c) {h4['c']['negligible_all_gateway_arms']} |" if "a" in h4 else f"{h4.get('reason')} |"))
    h5 = h["H5"]
    L.append(f"| H5 (explanatory consistency) | **{h5['verdict']}** | n {h5['n_arms']} arms" + (
        f", ρ(at-cap) {_fmt(h5['rho_frac_time_at_cap'])}, ρ(victims in saturation) {_fmt(h5['rho_victims_during_saturation'])} |"
        if "rho_frac_time_at_cap" in h5 else " |"))
    for C, v in h["H6"].items():
        L.append(f"| H6 P vs S {C} (F2) | **{v['verdict']}** | " + (
            f"ratio {_fmt(v['ratio'])}, p_TOST {_fmt(v['p_tost'], 4)} |" if v["evaluable"] else "not E&Vb |"))
    L += ["", "## Cells (primary: geometric mean over seeds of the per-seed victim mean user-facing TTFT ratio, "
          "attack/control; H7 strata)", "",
          "| Cell | Stratum | n | Geo-mean ratio [95% CI] | Class | P95 ratio | ΔSLO (atk−ctl) | Δ>500 ms | Gw queue mean atk/ctl (ms) | "
          "Threshold > noise | Failed gates |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, c in res["cells"].items():
        s = c["summary"]
        p = s["primary"]
        L.append(f"| {k} | {s['stratum']} | {s['n']} | {_fmt(p['ratio'])} [{_fmt(p['ci95'][0])}, {_fmt(p['ci95'][1])}] | "
                 f"{p['classification']} | {_fmt(s['p95_ratio']['ratio'])} | {_fmt(s['attack_slo_degradation']['mean_diff'])} | "
                 f"{_fmt(s['tail_diff_gt_500ms']['mean_diff'])} | {_fmt(s['attack_means']['gateway_queue_mean_ms'], 1)} / "
                 f"{_fmt(s['control_means']['gateway_queue_mean_ms'], 1)} | {s['threshold_above_noise']} | "
                 f"{', '.join(c['failed_gates']) or '—'} |")
    L += ["", "## H3 scores (victim mean gateway queue, ms)", "",
          "| Cell/arm | Envelope | Pred | Obs | Seeds within | Pass |", "|---|---|---|---|---|---|"]
    for k, v in h["H3"]["scores"].items():
        if "pass" in v:
            L.append(f"| {k} | {'validated' if v['validated_envelope'] else 'extrapolated'} | {_fmt(v['pred_cell_ms'], 1)} | "
                     f"{_fmt(v['obs_cell_ms'], 1)} | {v['seeds_within']}/{len(res['cells'][k.split('/')[0]]['seeds'])} | {v['pass']} |")
    L += ["", "Engine-queue figures are engine-global, finish-time aggregates (§5.2); they are not per-victim.", ""]
    return "\n".join(L)


def run(dirs: list[Path], stage: str, out: Path, *, force: bool = False) -> dict:
    cells: dict[str, dict] = {}
    reruns: dict[str, dict] = {}
    for d in dirs:
        for rep in sorted(p for p in d.iterdir() if (p / "manifest.json").exists() and CELL_RE.fullmatch(p.name)):
            c = load_cell(rep)
            (reruns if c["rerun"] else cells)[c["cell"]] = c
    replaced = {}
    for k, r in reruns.items():   # §8 rule 2: a rerun replaces its block only if that block failed; the failure is kept
        b = cells.get(k)
        if b is None or not b["failed_gates"]:
            raise SystemExit(f"rerun {k}{build_v5.RERUN} found but {k} is {'missing' if b is None else 'valid'}: "
                             "a rerun is permitted only after the block failed a gate")
        replaced[k] = {"original_report": b["report"], "original_failed_gates": b["failed_gates"], "rerun_report": r["report"]}
        cells[k] = r
    missing = [c for c in expected_cells(stage) if c not in cells]
    synthetic = bool(cells) and all(c["synthetic_backend"] for c in cells.values())
    if missing and not synthetic:
        raise SystemExit(f"stage {stage} incomplete ({len(missing)} cells missing, e.g. {missing[:3]}): no interim looks "
                         "at primary endpoints on real data (PROTOCOL_V5 §6)")
    if not cells:
        raise SystemExit("no v5 cell reports found")
    sid = server_identity(cells)
    if not sid["passed"]:   # a restart mid-stage invalidates that whole stage (§8 rule 3): its cells become notE
        for c in cells.values():
            if next(k for k, (load, _) in build_v5.STAGES.items() if load == c["L"]) not in sid["failed_stages"]:
                continue
            c["failed_gates"] = [*c["failed_gates"], "server_identity"]
            c["rows"] = [r | {"integrity_ok": False, "E": False} for r in c["rows"]]
    md, js = out / f"ANALYSIS_{stage}.md", out / f"analysis_{stage}.json"
    if (md.exists() or js.exists()) and not force:
        raise SystemExit(f"refusing to overwrite {md} (use --force)")
    res = analyse(cells, stage)
    res["missing_cells"] = missing
    res["replaced_by_rerun"] = replaced
    res["stage_gates"] = {"server_identity": sid}
    out.mkdir(parents=True, exist_ok=True)
    js.write_text(json.dumps(res, indent=1, default=lambda o: None if isinstance(o, float) and not math.isfinite(o) else str(o),
                             allow_nan=True))
    md.write_text(render_md(res))
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=("A", "B"), required=True)
    ap.add_argument("--reports", action="append", default=None,
                    help="report dirs holding v5 cell reports (default: reports/v5/stage_a [+ stage_b for B])")
    ap.add_argument("--out", default=str(REPO / "reports" / "v5"))
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    dirs = ([Path(p) for p in a.reports] if a.reports else
            [REPO / "reports" / "v5" / "stage_a", *([REPO / "reports" / "v5" / "stage_b"] if a.stage == "B" else [])])
    res = run(dirs, a.stage, Path(a.out), force=a.force)
    print(json.dumps({k: v.get("verdict") if isinstance(v, dict) and "verdict" in v else
                      {kk: vv.get("verdict") for kk, vv in v.items()} if k == "H6" else None
                      for k, v in res["hypotheses"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
