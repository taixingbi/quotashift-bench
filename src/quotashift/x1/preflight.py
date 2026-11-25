"""X1 preflight and host-telemetry rules (docs/PROTOCOL_X1_CROSS_PLATFORM_DRAFT.md rev 4, section 9). Pure functions.

Every check returns {"status": "pass" | "flag" | "fail", "reasons": [...], ...measurements}. "fail" makes the
platform NOT ADMISSIBLE (preflight) or fails the block (OOM during an arm); "flag" is reported, never invalidating.
Thresholds are module constants so they are frozen with the protocol (X1 Freeze Commit 1) and tested here.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

GIB = 1024 ** 3

# ---- thresholds (proposed; frozen at X1-G)
KV_MIN_TOKENS = 2 * 32 * 320            # 2 x (C = 32 x largest X1 request, 64 in + 256 out)
KV_FLAG_PEAK_MULT = 4                   # flag if KV < 4 x observed direct-path peak KV demand (calibration A)
RAM_FAIL_BYTES = 1 * GIB                # MemAvailable below this at any sample -> fail
RAM_FLAG_BYTES = 2 * GIB                # below this -> flag
CPU_FAIL_HOST = 0.95                    # host busy >= 95% ...
CPU_FAIL_FRAC = 0.10                    # ... for >= 10% of samples -> fail (preflight phase 2 only)
CPU_FLAG_HOST, CPU_FLAG_HOST_FRAC = 0.80, 0.10
CPU_FLAG_API, CPU_FLAG_API_FRAC = 0.85, 0.05   # API server >= 85% of one core for >= 5% of samples
LOAD_TIMEOUT_S = 1800                   # no healthy server within 30 min -> fail
LOAD_FLAG_MULT = 2.0                    # load time > 2 x G0's for the same model -> flag
TOK_ISOLATED_P99_FAIL_MS = 25.0         # isolated (sequential) /tokenize p99
TOK_ISOLATED_FLAG_MULT = 2.0            # flag if isolated p99 > 2 x G0's p99 (+1 ms floor)
TOK_UTIL_MAX = 0.10                     # rho = peak request rate x mean isolated service time must be <= 0.10
TOK_BURST_MULT = 10.0                   # burst test rate = 10 x peak offered request rate
TOK_BURST_MIN_ACHIEVED = 0.95           # achieved / offered during the burst
TOK_BURST_EXCESS_FAIL_MS = 10.0         # burst p99 - isolated p99 (queueing excess) -> fail above
TOK_BURST_EXCESS_FLAG_MS = 5.0
SAMPLER_MAX_CORE_FRAC = 0.01            # sampler's own CPU must stay below 1% of one core


def _res(status: str, reasons: list[str], **kw: object) -> dict:
    return {"status": status, "reasons": reasons, **kw}


def _worst(*statuses: str) -> str:
    return "fail" if "fail" in statuses else "flag" if "flag" in statuses else "pass"


def pctl(xs: Sequence[float], q: float) -> float:
    """Nearest-rank percentile (q in [0, 100]); deterministic, no interpolation."""
    if not xs:
        return math.nan
    s = sorted(xs)
    return s[max(0, math.ceil(q / 100 * len(s)) - 1)]


# ------------------------------------------------------------------------------------------------ model loading
def model_load_check(*, healthy: bool, startup_complete: bool, models_lists_pinned_revision: bool,
                     weight_hash_ok: bool, argv_matches_template: bool, smoke_generation_ok: bool,
                     startup_s: float | None, g0_startup_s: float | None = None,
                     log_error_lines: Sequence[str] = ()) -> dict:
    """Fail only on OBSERVABLE serving failure or identity mismatch, never on log text alone.

    WARNING lines (dtype casts, optional kernels such as FlashInfer, deprecations) are ignored entirely.
    ERROR/CRITICAL/Traceback lines are recorded and FLAG the platform for owner review: a crash that matters
    shows up as unhealthy, missing startup or a failed smoke generation, which are the fail conditions."""
    reasons, st = [], "pass"
    hard = {"server not healthy (/health != 200)": not healthy,
            "startup never completed": not startup_complete,
            "/v1/models does not list the pinned revision": not models_lists_pinned_revision,
            "weight hash differs from the pinned SHA-256": not weight_hash_ok,
            "server argv differs from the X1 launch template": not argv_matches_template,
            "smoke generation failed (wrong length, non-finite logprobs or empty text)": not smoke_generation_ok,
            f"no healthy server within {LOAD_TIMEOUT_S} s": startup_s is None or startup_s > LOAD_TIMEOUT_S}
    for why, bad in hard.items():
        if bad:
            reasons.append(why)
            st = "fail"
    if st != "fail":
        if g0_startup_s and startup_s and startup_s > LOAD_FLAG_MULT * g0_startup_s:
            reasons.append(f"load time {startup_s:.0f} s > {LOAD_FLAG_MULT} x G0 {g0_startup_s:.0f} s")
            st = "flag"
        if log_error_lines:
            reasons.append(f"{len(log_error_lines)} ERROR/Traceback log line(s) recorded for owner review "
                           "(server otherwise healthy)")
            st = "flag"
    return _res(st, reasons, startup_s=startup_s, log_error_lines=list(log_error_lines)[:20])


# ------------------------------------------------------------------------------------------------ KV capacity
def kv_capacity_check(kv_tokens: int, observed_direct_peak_tokens: float | None = None) -> dict:
    if kv_tokens < KV_MIN_TOKENS:
        return _res("fail", [f"GPU KV {kv_tokens} tokens < {KV_MIN_TOKENS}"], kv_tokens=kv_tokens)
    if observed_direct_peak_tokens and kv_tokens < KV_FLAG_PEAK_MULT * observed_direct_peak_tokens:
        return _res("flag", [f"GPU KV {kv_tokens} < {KV_FLAG_PEAK_MULT} x observed peak "
                             f"{observed_direct_peak_tokens:.0f}"], kv_tokens=kv_tokens)
    return _res("pass", [], kv_tokens=kv_tokens)


# ------------------------------------------------------------------------------------------------ host telemetry
def _frac(xs: Sequence[float | None], thr: float) -> float:
    v = [x for x in xs if x is not None]
    return sum(x >= thr for x in v) / len(v) if v else 0.0


def ram_check(samples: Sequence[dict]) -> dict:
    """Preflight and per-arm. Fail: any OOM kill or MemAvailable < 1 GiB. Flag: < 2 GiB or any swap-in."""
    mem = [s["mem_available"] for s in samples if s.get("mem_available") is not None]
    ooms = [s["oom_kill"] for s in samples if s.get("oom_kill") is not None]
    swp = [s["pswpin"] for s in samples if s.get("pswpin") is not None]
    d_oom = (ooms[-1] - ooms[0]) if len(ooms) > 1 else 0
    d_swp = (swp[-1] - swp[0]) if len(swp) > 1 else 0
    reasons: list[str] = []
    if not mem:
        return _res("fail", ["no MemAvailable samples"], min_mem_available=None, oom_kills=d_oom, swap_in=d_swp)
    lo = min(mem)
    if d_oom > 0:
        reasons.append(f"{d_oom} OOM kill(s)")
    if lo < RAM_FAIL_BYTES:
        reasons.append(f"MemAvailable min {lo / GIB:.2f} GiB < 1 GiB")
    if reasons:
        return _res("fail", reasons, min_mem_available=lo, oom_kills=d_oom, swap_in=d_swp)
    if lo < RAM_FLAG_BYTES:
        reasons.append(f"MemAvailable min {lo / GIB:.2f} GiB < 2 GiB")
    if d_swp > 0:
        reasons.append(f"{d_swp} pages swapped in")
    return _res("flag" if reasons else "pass", reasons, min_mem_available=lo, oom_kills=d_oom, swap_in=d_swp)


def cpu_check(samples: Sequence[dict], *, preflight: bool) -> dict:
    """Per-arm (`host_cpu_headroom`, flag only) or preflight phase 2 (adds the fail rule)."""
    host = [s.get("host_busy") for s in samples]
    api = [s.get("api_cpu") for s in samples]
    f_fail, f_host, f_api = _frac(host, CPU_FAIL_HOST), _frac(host, CPU_FLAG_HOST), _frac(api, CPU_FLAG_API)
    m = {"frac_host_ge_95": f_fail, "frac_host_ge_80": f_host, "frac_api_ge_85": f_api,
         "n_samples": len(samples), "api_found": any(a is not None for a in api)}
    if not samples:
        return _res("fail", ["no CPU samples"], **m)
    if preflight and f_fail >= CPU_FAIL_FRAC:
        return _res("fail", [f"host CPU >= 95% in {f_fail:.0%} of samples"], **m)
    reasons = []
    if f_api >= CPU_FLAG_API_FRAC:
        reasons.append(f"API server >= 85% of a core in {f_api:.0%} of samples")
    if f_host >= CPU_FLAG_HOST_FRAC:
        reasons.append(f"host CPU >= 80% in {f_host:.0%} of samples")
    if not m["api_found"]:
        reasons.append("API-server process not found by the sampler")
    return _res("flag" if reasons else "pass", reasons, **m)


def sampler_overhead_check(summary: dict) -> dict:
    f = summary.get("overhead_core_frac")
    if f is None:
        return _res("fail", ["no sampler summary"], overhead_core_frac=None)
    st = "pass" if f < SAMPLER_MAX_CORE_FRAC else "fail"
    return _res(st, [] if st == "pass" else [f"sampler used {f:.2%} of a core"], overhead_core_frac=f)


# ------------------------------------------------------------------------------------------------ tokenization
def tokenization_check(*, isolated_ms: Sequence[float], peak_request_rps: float,
                       burst_offered_rps: float | None = None, burst_achieved_rps: float | None = None,
                       burst_ms: Sequence[float] = (), g0_isolated_p99_ms: float | None = None) -> dict:
    """Two separate questions, two separate measurements.

    1. ISOLATED latency (sequential requests, no queue): the per-request CPU cost of tokenizing one prompt,
       incl. HTTP overhead -> an upper bound on what tokenization adds to every request's TTFT.
       Fail if p99 > 25 ms (about 30% of the ~82 ms v5 idle victim TTFT: beyond that the platform's TTFT would be
       dominated by CPU-side work). Flag if p99 > 2 x the G0 value for the same model (+1 ms floor).
    2. CAPACITY / burst queueing: utilisation rho = peak offered request rate x mean isolated service time must
       be <= 0.10 (the "10 x headroom" rule). At rho <= 0.1 an M/G/1 queue adds a mean wait of at most
       rho/(1-rho) x E[S^2]/(2 E[S]) ~ 0.06-0.11 x service time, i.e. negligible. The burst test VALIDATES that
       assumption empirically: an open-loop burst at 10 x peak must be sustained (achieved >= 95% of offered)
       and its p99 must exceed the isolated p99 by <= 10 ms (queueing excess; flag above 5 ms).
    Phase 1 (before calibration) can run only part 1 with a provisional peak; part 2 needs the calibrated high
    rate and runs in phase 2."""
    reasons, st = [], "pass"
    iso_p99 = pctl(isolated_ms, 99)
    iso_mean = sum(isolated_ms) / len(isolated_ms) if isolated_ms else math.nan
    rho = peak_request_rps * iso_mean / 1000.0
    m: dict = {"isolated_p50_ms": pctl(isolated_ms, 50), "isolated_p99_ms": iso_p99, "isolated_mean_ms": iso_mean,
               "rho_at_peak": rho, "peak_request_rps": peak_request_rps}
    if not isolated_ms:
        return _res("fail", ["no isolated tokenization samples"], **m)
    if iso_p99 > TOK_ISOLATED_P99_FAIL_MS:
        reasons.append(f"isolated p99 {iso_p99:.1f} ms > {TOK_ISOLATED_P99_FAIL_MS} ms")
        st = "fail"
    if rho > TOK_UTIL_MAX:
        reasons.append(f"tokenization utilisation at peak {rho:.3f} > {TOK_UTIL_MAX}")
        st = "fail"
    if burst_offered_rps is not None:
        b_p99 = pctl(burst_ms, 99)
        excess = b_p99 - iso_p99
        ach = (burst_achieved_rps or 0.0) / burst_offered_rps if burst_offered_rps else 0.0
        m |= {"burst_offered_rps": burst_offered_rps, "burst_achieved_frac": ach, "burst_p99_ms": b_p99,
              "burst_excess_p99_ms": excess}
        if burst_offered_rps < TOK_BURST_MULT * peak_request_rps * 0.999:
            reasons.append(f"burst rate {burst_offered_rps:.1f}/s below {TOK_BURST_MULT} x peak")
            st = "fail"
        if ach < TOK_BURST_MIN_ACHIEVED:
            reasons.append(f"burst achieved only {ach:.0%} of offered")
            st = "fail"
        if excess > TOK_BURST_EXCESS_FAIL_MS:
            reasons.append(f"burst p99 exceeds isolated p99 by {excess:.1f} ms")
            st = "fail"
        elif excess > TOK_BURST_EXCESS_FLAG_MS and st != "fail":
            reasons.append(f"burst queueing excess {excess:.1f} ms > {TOK_BURST_EXCESS_FLAG_MS} ms")
            st = "flag"
    if st == "pass" and g0_isolated_p99_ms is not None and iso_p99 > max(TOK_ISOLATED_FLAG_MULT * g0_isolated_p99_ms,
                                                                          g0_isolated_p99_ms + 1.0):
        reasons.append(f"isolated p99 {iso_p99:.1f} ms > 2 x G0 {g0_isolated_p99_ms:.1f} ms")
        st = "flag"
    return _res(st, reasons, **m)


def combine(*results: dict) -> str:
    return _worst(*(r["status"] for r in results))


SAMPLER_EQ_ABS_MS, SAMPLER_EQ_REL = 1.0, 0.02


def sampler_equivalence_check(ttft_on_ms: Sequence[float], ttft_off_ms: Sequence[float]) -> dict:
    """Phase 1: idle TTFT floor with the sampler running vs stopped. Fail only if the medians differ by more than
    1 ms AND by more than 2% (both, so sub-millisecond jitter on a fast platform cannot fail it)."""
    if not ttft_on_ms or not ttft_off_ms:
        return _res("fail", ["missing sampler on/off TTFT samples"])
    on, off = pctl(ttft_on_ms, 50), pctl(ttft_off_ms, 50)
    d = on - off
    bad = abs(d) > SAMPLER_EQ_ABS_MS and abs(d) > SAMPLER_EQ_REL * off
    return _res("fail" if bad else "pass", [f"sampler shifts idle TTFT median by {d:+.2f} ms"] if bad else [],
                median_on_ms=on, median_off_ms=off, diff_ms=d)


# ------------------------------------------------------------------------------------------------ clock alignment
CLOCK_OFFSET_FLAG_S, CLOCK_OFFSET_FAIL_S = 2.0, 5.0


def clock_offset_check(offset_s: float | None, bound_s: float | None) -> dict:
    """Phase 1: GPU-host clock minus runner clock (from the server's HTTP Date header; tokenize_probe.clock_offset_probe).
    Host-telemetry samples are stamped by the GPU host, arm windows by the runner: the analysis shifts each window by
    this offset. Windows are padded by 30 s, so |offset| <= 2 s is negligible; > 5 s fails (clock not synchronised)."""
    if offset_s is None:
        return _res("fail", ["no clock-offset measurement"], offset_s=None, bound_s=bound_s)
    worst = abs(offset_s) + (bound_s or 0.0)
    if worst > CLOCK_OFFSET_FAIL_S:
        return _res("fail", [f"clock offset {offset_s:+.2f} s (+/- {bound_s:.2f}) > {CLOCK_OFFSET_FAIL_S} s"],
                    offset_s=offset_s, bound_s=bound_s)
    if worst > CLOCK_OFFSET_FLAG_S:
        return _res("flag", [f"clock offset {offset_s:+.2f} s (+/- {bound_s:.2f}) > {CLOCK_OFFSET_FLAG_S} s"],
                    offset_s=offset_s, bound_s=bound_s)
    return _res("pass", [], offset_s=offset_s, bound_s=bound_s)
