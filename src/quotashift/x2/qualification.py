"""X2 qualification: Q0 host stability (A/A, reported) and Q1 instrumentation invariance (gate).
docs/X2_INSTRUMENTATION_SPEC.md section 5; sizing: scripts/x2_q1_power.py -> reports/x2/Q1_POWER.{json,md}.

Segment (both tests): [state: P = production boundary snapshot, N = the same idle wait without it] -> GUARD_S idle ->
verified /reset_prefix_cache -> WARMUP unrecorded warm-ups (seeds 21900-21902) -> M measured sequential streamed
requests over ONE fixed prompt list (seeds 21000..21000+M-1, identical in every segment; 60 words, max_tokens 8,
temperature 0, ignore_eos), one in flight, fresh connection each, TTFT timed on the runner; the frozen v5 harness's
/metrics poller runs at its production interval in every segment (production conditions, both arms alike).
Q1: K pairs, pair k = (N, P) if k even else (P, N). d_k = p50(P_k) - p50(N_k) (nearest-rank).
Decision (T1s, fixed by the sizing rules R1-R3): PASS iff the 95% t-interval of mean d_k lies strictly inside
(-delta, +delta), delta = max(1 ms, 2% x nearest-rank p50 of all measured N requests). t quantiles from the FROZEN v5
`t_cdf` (scripts/v5_analysis.py, imported unchanged). Anything incomplete or unverified -> FAIL. No retry.
Q0: K0 pairs of two N segments (labels a/b alternate first); reported (mean, 90% CI, slow-segment count), never a gate.
"""

from __future__ import annotations

import math
import sys
from collections.abc import Sequence
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

TEST = "T1s"                                 # strict t-TOST on the mean pair difference (reports/x2/Q1_POWER.md)
ALPHA = 0.05                                 # bound on the test size; achieved with a 95% interval (0.025 per side)
CI_LEVEL = 0.95
DELTA_ABS_MS, DELTA_REL = 1.0, 0.02          # unchanged from X1 (owner: X2 not looser than X1)
K_PAIRS, M_PER_SEGMENT = 64, 40              # fixed design (Q1_POWER.json "chosen")
K0_PAIRS = 16                                # Q0 (descriptive)
WARMUP = 3
GUARD_S = 15.0
PROMPT_SEED0, WARMUP_SEEDS = 21000, (21900, 21901, 21902)
PROMPT_WORDS, MAX_TOKENS = 60, 8
SLOW_SEGMENT_MS = 2.0                        # descriptive: a segment p50 > pair partner + 2 ms is "slow"


def prompt_seeds(m: int = M_PER_SEGMENT) -> tuple[int, ...]:
    return tuple(range(PROMPT_SEED0, PROMPT_SEED0 + m))


def q1_order(k: int = K_PAIRS) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for j in range(k):
        out += [(j, "N"), (j, "P")] if j % 2 == 0 else [(j, "P"), (j, "N")]
    return out


def q0_order(k0: int = K0_PAIRS) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for j in range(k0):
        out += [(j, "a"), (j, "b")] if j % 2 == 0 else [(j, "b"), (j, "a")]
    return out


def pctl50(xs: Sequence[float]) -> float:
    s = sorted(xs)
    return s[max(0, math.ceil(len(s) / 2) - 1)]


def t_ppf(p: float, df: int) -> float:
    """Inverse of the FROZEN v5 Student-t CDF (scripts/v5_analysis.t_cdf), by bisection."""
    sys.path.insert(0, str(REPO / "scripts"))
    import v5_analysis as va
    lo, hi = -1e3, 1e3
    for _ in range(200):
        mid = (lo + hi) / 2
        if va.t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-11:
            break
    return (lo + hi) / 2


def _validate(segments: Sequence[dict], order: list[tuple[int, str]], m: int, ok_key: str) -> tuple[dict, list[str]]:
    reasons: list[str] = []
    by: dict[tuple[int, str], dict] = {}
    for s in segments:
        key = (int(s["pair"]), str(s["arm"]))
        if key in by:
            reasons.append(f"duplicate segment {key}")
        by[key] = s
    want = set(order)
    if set(by) != want:
        reasons.append(f"segments missing {sorted(want - set(by))[:4]} / unexpected {sorted(set(by) - want)[:4]}")
    for key in sorted(want & set(by)):
        s = by[key]
        v = s.get("ttft_ms") or []
        if len(v) != m or any(x is None or not math.isfinite(x) or x <= 0 for x in v):
            reasons.append(f"segment {key}: needs exactly {m} finite measured TTFTs")
        if not s.get("reset_verified"):
            reasons.append(f"segment {key}: prefix-cache reset not verified")
        if not s.get(ok_key):
            reasons.append(f"segment {key}: segment procedure not verified")
    return by, reasons


def interval(d: Sequence[float], level: float) -> tuple[float, float, float, float]:
    k = len(d)
    mean = sum(d) / k
    sd = math.sqrt(sum((x - mean) ** 2 for x in d) / (k - 1))
    se = sd / math.sqrt(k)
    t = t_ppf(0.5 + level / 2, k - 1)
    return mean, sd, mean - t * se, mean + t * se


def q1_decide(segments: Sequence[dict], *, k: int = K_PAIRS, m: int = M_PER_SEGMENT) -> dict:
    """segments: [{"pair", "arm" in N|P, "ttft_ms": [m], "reset_verified", "procedure_ok"}]."""
    by, reasons = _validate(segments, q1_order(k), m, "procedure_ok")
    if reasons:
        return {"status": "fail", "reasons": reasons, "test": TEST}
    d = [pctl50(by[(j, "P")]["ttft_ms"]) - pctl50(by[(j, "N")]["ttft_ms"]) for j in range(k)]
    base = pctl50([v for j in range(k) for v in by[(j, "N")]["ttft_ms"]])
    delta = max(DELTA_ABS_MS, DELTA_REL * base)
    mean, sd, lo, hi = interval(d, CI_LEVEL)
    _, _, lo90, hi90 = interval(d, 0.90)
    ok = -delta < lo and hi < delta
    return {"status": "pass" if ok else "fail", "test": TEST, "ci_level": CI_LEVEL, "k_pairs": k, "m_per_segment": m,
            "reasons": [] if ok else [f"95% CI [{lo:+.3f}, {hi:+.3f}] ms not inside (-{delta:.3f}, +{delta:.3f}) ms"],
            "pair_diffs_ms": d, "mean_diff_ms": mean, "sd_pair_diff_ms": sd, "ci95_ms": [lo, hi],
            "ci90_ms_reported": [lo90, hi90], "off_baseline_p50_ms": base, "delta_ms": delta,
            "slow_pairs_descriptive": sum(1 for x in d if x > SLOW_SEGMENT_MS)}


def q0_describe(segments: Sequence[dict], *, k0: int = K0_PAIRS, m: int = M_PER_SEGMENT) -> dict:
    by, reasons = _validate(segments, q0_order(k0), m, "procedure_ok")
    if reasons:
        return {"status": "incomplete", "reasons": reasons}
    d = [pctl50(by[(j, "b")]["ttft_ms"]) - pctl50(by[(j, "a")]["ttft_ms"]) for j in range(k0)]
    mean, sd, lo, hi = interval(d, 0.90)
    meds = [pctl50(s["ttft_ms"]) for s in by.values()]
    floor = pctl50(meds)
    return {"status": "reported", "gate": False, "pair_diffs_ms": d, "mean_diff_ms": mean, "sd_pair_diff_ms": sd,
            "ci90_ms": [lo, hi], "segment_p50_floor_ms": floor,
            "slow_segments": sum(1 for x in meds if x > floor + SLOW_SEGMENT_MS), "n_segments": len(meds)}
