"""X1 Amendment A1 — sampler on/off equivalence by a paired-segment equivalence test.

STATUS: CANDIDATE (proposal, docs/X1_AMENDMENT_A1_SAMPLER_EQUIVALENCE.md). Not frozen, not wired into any driver, never
used to evaluate a run until the owner approves the amendment and it is pinned in experiments/x1/AMENDMENT_A1_SHA256.json.
It supersedes, for preflight runs AFTER that pin only, the frozen point-estimate rule
`quotashift.x1.preflight.sampler_equivalence_check` (rev 4 section 9.1), which stays unchanged and still describes how
attempts 1 and 2 of g0m0 Phase 1 were judged (both FAIL; never reclassified).

Design (fixed before any amended-run data):
  K pairs of segments; pair k runs OFF then ON when k is even (0-based), ON then OFF when k is odd (balanced ABBA order).
  Each segment: sampler state set and verified -> verified prefix-cache reset -> WARMUP unrecorded warm-up requests
  (dedicated prompts) -> M measured sequential requests (one in flight, fresh connection each) over ONE fixed prompt list
  used identically in every segment. TTFT is timed on the runner (monotonic clock), independently of the GPU-host sampler.
Statistic: d_k = p50(ON_k) - p50(OFF_k) (nearest-rank, the frozen `pctl`); D = mean d_k; SE = sd(d_k)/sqrt(K).
Tolerance (unchanged practical tolerance of rev 4): delta = max(1 ms, 2% x p50 of all measured OFF requests).
Decision: PASS iff the (1 - 2 alpha) two-sided t interval D +- t_{1-alpha, K-1} SE lies strictly inside (-delta, +delta)
(TOST, alpha = 0.05 -> 90% interval). Anything else, including an incomplete or invalid segment, is FAIL (no flag).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from quotashift.x1.preflight import pctl

RULE_ID = "X1-A1 paired-segment TOST"
DELTA_ABS_MS, DELTA_REL = 1.0, 0.02          # rev 4 tolerance, unchanged
ALPHA = 0.05                                 # TOST: one-sided 5% each side == 90% two-sided interval
K_PAIRS, M_PER_SEGMENT, WARMUP = 24, 80, 3   # fixed; reports/x1/AMENDMENT_A1_POWER.json (selection rule C1-C3)
PROMPT_SEEDS = tuple(range(200, 200 + M_PER_SEGMENT))   # prompt_of(60, seed), max_tokens 8: SAME list in every segment
WARMUP_SEEDS = (900, 901, 902)                         # dedicated warm-up prompts, same in every segment, not analysed


def segment_order(k_pairs: int = K_PAIRS) -> list[tuple[int, str]]:
    """[(pair, arm), ...] in execution order: OFF,ON | ON,OFF | OFF,ON | ... (balanced; cancels linear drift)."""
    out: list[tuple[int, str]] = []
    for k in range(k_pairs):
        out += [(k, "off"), (k, "on")] if k % 2 == 0 else [(k, "on"), (k, "off")]
    return out


# --------------------------------------------------------------------------------------------- Student t (no scipy)
_FPMIN = 1e-300


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the regularized incomplete beta function (modified Lentz; Numerical Recipes betacf)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > _FPMIN else _FPMIN)
    h = d
    for m in range(1, 1000):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)), -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1.0 + aa * d
            d = 1.0 / (d if abs(d) > _FPMIN else _FPMIN)
            c = 1.0 + aa / c
            c = c if abs(c) > _FPMIN else _FPMIN
            step = d * c
            h *= step
        if abs(step - 1.0) < 1e-15:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def _t_cdf(x: float, df: int) -> float:
    """Student t CDF: P(|T| > |x|) = I_{df/(df+x^2)}(df/2, 1/2)."""
    tail = 0.5 * _betai(df / 2.0, 0.5, df / (df + x * x))
    return 1.0 - tail if x > 0 else tail


def t_ppf(p: float, df: int) -> float:
    """Inverse Student t CDF by bisection (|error| < 1e-10)."""
    if not 0.0 < p < 1.0 or df < 1:
        raise ValueError("p in (0, 1), df >= 1")
    lo, hi = -1e3, 1e3
    for _ in range(200):
        mid = (lo + hi) / 2
        if _t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-11:
            break
    return (lo + hi) / 2


# --------------------------------------------------------------------------------------------- decision
def equivalence_a1(segments: Sequence[dict], *, alpha: float = ALPHA, k_pairs: int = K_PAIRS,
                   m_per_segment: int = M_PER_SEGMENT) -> dict:
    """segments: [{"pair": k, "arm": "on"|"off", "ttft_ms": [M measured values], "reset_verified": bool,
    "sampler_state_ok": bool}, ...]. Returns {"status": "pass"|"fail", "reasons": [...], ...}."""
    reasons: list[str] = []
    by: dict[tuple[int, str], dict] = {}
    for s in segments:
        key = (int(s["pair"]), str(s["arm"]))
        if key in by:
            reasons.append(f"duplicate segment {key}")
        by[key] = s
    want = {(k, a) for k in range(k_pairs) for a in ("off", "on")}
    if set(by) != want:
        reasons.append(f"segments missing or unexpected: missing {sorted(want - set(by))}, extra {sorted(set(by) - want)}")
    for key in sorted(want & set(by)):
        s = by[key]
        vals = s.get("ttft_ms") or []
        if len(vals) != m_per_segment or any(v is None or not math.isfinite(v) or v <= 0 for v in vals):
            reasons.append(f"segment {key}: needs exactly {m_per_segment} finite measured TTFTs")
        if not s.get("reset_verified"):
            reasons.append(f"segment {key}: prefix-cache reset not verified")
        if not s.get("sampler_state_ok"):
            reasons.append(f"segment {key}: sampler state not verified ({'running' if key[1] == 'on' else 'stopped'})")
    if reasons:
        return {"status": "fail", "reasons": reasons, "rule": RULE_ID}
    d = [pctl(by[(k, "on")]["ttft_ms"], 50) - pctl(by[(k, "off")]["ttft_ms"], 50) for k in range(k_pairs)]
    mean = sum(d) / k_pairs
    sd = math.sqrt(sum((x - mean) ** 2 for x in d) / (k_pairs - 1))
    se = sd / math.sqrt(k_pairs)
    off_all = [v for k in range(k_pairs) for v in by[(k, "off")]["ttft_ms"]]
    base = pctl(off_all, 50)
    delta = max(DELTA_ABS_MS, DELTA_REL * base)
    t90, t95 = t_ppf(1 - alpha, k_pairs - 1), t_ppf(0.975, k_pairs - 1)
    ci = (mean - t90 * se, mean + t90 * se)
    ci95 = (mean - t95 * se, mean + t95 * se)
    ok = -delta < ci[0] and ci[1] < delta
    return {"status": "pass" if ok else "fail",
            "reasons": [] if ok else [f"{100 * (1 - 2 * alpha):.0f}% CI [{ci[0]:+.3f}, {ci[1]:+.3f}] ms not inside "
                                      f"(-{delta:.3f}, +{delta:.3f}) ms"],
            "rule": RULE_ID, "alpha": alpha, "k_pairs": k_pairs, "m_per_segment": m_per_segment,
            "pair_diffs_ms": d, "mean_diff_ms": mean, "sd_pair_diff_ms": sd, "se_ms": se,
            "off_baseline_p50_ms": base, "delta_ms": delta, "ci90_ms": list(ci), "ci95_ms_reported": list(ci95),
            "strict95_would_pass": -delta < ci95[0] and ci95[1] < delta}
