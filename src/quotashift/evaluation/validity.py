"""Fail-closed experiment validity gates (ADR-Q17; pre-registered 2026-11-21 before the v3.1 long-context runs).

Added after the Suite S forensic audit (reports/v3/SUITE_S_FORENSIC_AUDIT.md): a block whose competitor was 97%
rejected with HTTP 400 still received a classification. A failed gate sets the experiment's classification to
`invalid` (the computed label is kept as `classification_unvalidated`) and the CLI exits non-zero.

Gate thresholds are validity criteria, not effect thresholds; they are fixed here, before any run they govern, and
never tuned on results. Historical reports are never re-labelled by these gates; the offline re-analysis
(scripts/reanalyze_suite.py) only *reports* them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from quotashift.evaluation.attack_effect import RunMetrics, metric_info
from quotashift.evaluation.occupancy import MIN_RECON_EXACT_FRACTION

MAX_BACKEND_ERROR_FRACTION = 0.01   # backend errors (any HTTP 4xx/5xx) / requests sent, per arm
MAX_HTTP_400_FRACTION = 0.01        # HTTP 400 / requests sent, per arm
MIN_ADMISSION_FRACTION = 0.95       # admitted / offered, per class, per arm
MIN_COMPETITOR_COMPLETION = 0.95    # (completed + designed client cancels/timeouts) / offered, per arm
MAX_VICTIM_CENSORED_FRACTION = 0.05  # (offered - completed) / offered victims, per arm (latency endpoints)
# v4 arrival coverage: in every arm the first competitor arrival is in the first quarter of the window and the last
# in the final quarter. A front-loaded budget (historical matched_total_short: last arrival ~0.5) fails; N iid uniform
# arrivals fail with probability 2 * 0.75**N (< 0.3% for the smallest v4 count, N = 23).
MAX_FIRST_ARRIVAL_FRACTION = 0.25
MIN_LAST_ARRIVAL_FRACTION = 0.75


def _chk(name: str, passed: bool | None, detail: str, severity: str = "fail") -> dict[str, Any]:
    return {"name": name, "passed": bool(passed) if passed is not None else False, "available": passed is not None,
            "detail": detail, "severity": severity}


def _frac(n: int | None, d: int | None) -> float | None:
    return None if n is None or not d else n / d


def run_manifest_provenance(run_dirs: list[Path]) -> dict[str, Any]:
    """Collect provenance from the runs' own manifests/summaries (never inferred from file names)."""
    shas, dirty, starts, versions, models, revisions = set(), set(), set(), set(), set(), set()
    missing: list[str] = []
    for d in run_dirs:
        d = Path(d)
        try:
            m = json.loads((d / "manifest.json").read_text())
            s = json.loads((d / "metrics_summary.json").read_text())
        except FileNotFoundError as e:
            missing.append(f"{d.name}: {e.filename}")
            continue
        g = m.get("git") or {}
        shas.add(g.get("sha"))
        dirty.add(g.get("dirty"))
        ec = s.get("engine_counters") or {}
        starts.add((ec.get("engine_state_at_start") or {}).get("process_start_time_seconds"))
        bi = (m.get("run_context") or {}).get("backend_identity") or {}
        versions.add(json.dumps(bi.get("vllm_version"), sort_keys=True))
        models.add(bi.get("model"))
        revisions.add(bi.get("model_revision"))
    return {"git_sha": sorted(map(str, shas)), "git_dirty": sorted(map(str, dirty)),
            "server_start": sorted(map(str, starts)), "vllm_version": sorted(versions), "model": sorted(map(str, models)),
            "model_revision_in_run_manifest": sorted(map(str, revisions)), "missing": missing}


def validity_gates(attack: list[RunMetrics], control: list[RunMetrics], analysis: dict, *, max_model_len: int,
                   prompt_token_unit: str = "whitespace", designed_early_termination: bool = False,
                   provenance: dict[str, Any] | None = None, tokenization: dict | None = None,
                   synthetic: bool = False, protocol_version: int = 3, ignore_eos: bool = False,
                   feasibility_gates: str = "enforce", expected_cap: int | None = None,
                   path: str = "gateway") -> dict[str, Any]:
    """Evaluate every gate on one experiment; `passed` is False if any fail-severity gate fails or is unavailable."""
    arms = [*attack, *control]
    checks: list[dict[str, Any]] = []
    info = metric_info(analysis["metric"])

    # 1-2. HTTP errors
    worst_err = max([(_frac(m.backend_error_total, m.requests_sent) or 0.0) for m in arms] or [0.0])
    worst_400 = max([(_frac(m.http_400_total, m.requests_sent) or 0.0) for m in arms] or [0.0])
    have = bool(arms) and all(m.backend_error_total is not None and m.requests_sent is not None for m in arms)
    checks.append(_chk("backend_error_rate", (worst_err <= MAX_BACKEND_ERROR_FRACTION) if have else None,
                       f"worst arm {worst_err:.4f} (max {MAX_BACKEND_ERROR_FRACTION})" if have else "unavailable"))
    checks.append(_chk("http_400_rate", (worst_400 <= MAX_HTTP_400_FRACTION) if have else None,
                       f"worst arm {worst_400:.4f} (max {MAX_HTTP_400_FRACTION})" if have else "unavailable"))

    # 3. admission (victims and competitor)
    adm = [(_frac(m.victim_admitted, m.victim_offered), _frac(m.competitor_admitted, m.competitor_offered)) for m in arms]
    vals: list[float] = []
    complete = bool(arms)
    for (v, c), m in zip(adm, arms, strict=True):
        if v is None or (c is None and m.competitor_offered):
            complete = False
            break
        vals += [v, c if c is not None else 1.0]
    if complete:
        lo = min(vals)
        checks.append(_chk("admission_rate", lo >= MIN_ADMISSION_FRACTION,
                           f"lowest class admission {lo:.3f} (min {MIN_ADMISSION_FRACTION})"))
    else:
        checks.append(_chk("admission_rate", None, "unavailable (no t_accepted column)"))

    # 4. competitor completion (client-designed cancels/timeouts count as intended outcomes)
    def comp_ok(m: RunMetrics) -> float | None:
        if not m.competitor_offered:
            return None
        ok = m.competitor_requests + ((m.competitor_cancelled or 0) + (m.competitor_timed_out or 0)
                                      if designed_early_termination else 0)
        return ok / m.competitor_offered
    cc = [x for x in (comp_ok(m) for m in arms) if x is not None]
    checks.append(_chk("competitor_completion", (min(cc) >= MIN_COMPETITOR_COMPLETION) if cc else None,
                       f"lowest arm {min(cc):.3f} (min {MIN_COMPETITOR_COMPLETION}"
                       f"{'; designed client cancels/timeouts counted' if designed_early_termination else ''})"
                       if cc else "no competitor"))

    # 5. primary metric present for every seed
    n, k = analysis.get("n_seeds", 0), analysis.get("n_seeds_with_metric", 0)
    checks.append(_chk("primary_metric_present", n > 0 and n == k, f"{k}/{n} seeds have a finite {info.label}"))

    # 6. tokenized context
    ctx: list[float] = [float(m.max_context_tokens_completed) for m in arms
                        if m.max_context_tokens_completed is not None and finite(m.max_context_tokens_completed)]
    tok_ok = tokenization is not None and all(r.get("ok") for per in (tokenization.get("per_seed") or {}).values()
                                              for r in per.values())
    ctx_ok = (max(ctx) <= max_model_len) if ctx else None
    if not synthetic and tokenization is None:
        checks.append(_chk("tokenized_context", None, "no pre-run tokenization check recorded"))
    else:
        if not synthetic and not ctx:
            ctx_ok = False  # live runs must report usage for completed requests
        checks.append(_chk("tokenized_context", bool(ctx_ok is not False and (tok_ok or tokenization is None)),
                           f"max completed prompt+max_output {max(ctx) if ctx else 'n/a'} <= {max_model_len}; "
                           f"pre-run check {'ok' if tok_ok else ('n/a' if tokenization is None else 'FAILED')}"))
    if prompt_token_unit == "tokenizer":
        mism = sum(m.token_count_mismatch_completed or 0 for m in arms)
        n_rep = sum(m.token_count_reported_completed or 0 for m in arms)
        n_done = sum(m.requests_completed or 0 for m in arms)
        if synthetic and n_rep == 0:
            checks.append(_chk("planned_vs_reported_tokens", True, "mock backend reports no usage.prompt_tokens"))
        else:  # live: every completed request must report usage and match its plan exactly
            avail = n_done > 0 and n_rep == n_done
            checks.append(_chk("planned_vs_reported_tokens", (mism == 0) if avail else None,
                               f"{mism} mismatch(es) among {n_rep}/{n_done} completed requests reporting "
                               "usage.prompt_tokens (planned input_token_count must equal it)"))

    # 7. provenance
    if provenance is not None and not synthetic:
        p = provenance
        problems = []
        if len(p.get("git_sha", [])) != 1 or p["git_sha"][0] in ("None", ""):
            problems.append(f"git sha {p.get('git_sha')}")
        if p.get("git_dirty") != ["False"]:
            problems.append(f"dirty {p.get('git_dirty')}")
        if len(p.get("server_start", [])) != 1 or p["server_start"][0] == "None":
            problems.append(f"server start {p.get('server_start')}")
        if len(p.get("vllm_version", [])) != 1 or p["vllm_version"][0] == "null":
            problems.append("vllm version")
        if not p.get("model_revision_status"):
            problems.append("model revision status not recorded")
        if p.get("missing"):
            problems.append(f"missing files {p['missing'][:2]}")
        checks.append(_chk("provenance", not problems, "; ".join(problems) or
                           f"sha {p['git_sha'][0][:12]}, clean, server start {p['server_start'][0]}"))
    elif not synthetic:
        checks.append(_chk("provenance", None, "no provenance collected"))

    # 8. censoring (fail for a victim-latency primary; flag for others)
    cens = [m.victim_censored_fraction for m in arms if m.victim_censored_fraction is not None]
    worst = max(cens) if cens else None
    sev = "fail" if info.kind in ("victim_latency",) else "flag"
    checks.append(_chk("victim_latency_censoring", (worst <= MAX_VICTIM_CENSORED_FRACTION) if worst is not None else None,
                       f"worst arm censored fraction {worst:.3f} (max {MAX_VICTIM_CENSORED_FRACTION}); "
                       f"{'primary' if sev == 'fail' else 'secondary latency endpoints only'}"
                       if worst is not None else "unavailable", severity=sev))

    # 9-10. protocol v4: load covers the window; realized output equals the authorized output
    if protocol_version >= 4:
        withc = [m for m in arms if m.competitor_offered]
        firsts = [m.competitor_first_arrival_fraction for m in withc]
        lasts = [m.competitor_last_arrival_fraction for m in withc]
        avail = bool(withc) and all(x is not None for x in (*firsts, *lasts))
        fmax = max([x for x in firsts if x is not None] or [0.0])
        lmin = min([x for x in lasts if x is not None] or [0.0])
        checks.append(_chk("arrival_coverage",
                           (fmax <= MAX_FIRST_ARRIVAL_FRACTION and lmin >= MIN_LAST_ARRIVAL_FRACTION) if avail else None,
                           f"latest first arrival {fmax:.3f} (max {MAX_FIRST_ARRIVAL_FRACTION}), earliest last arrival "
                           f"{lmin:.3f} (min {MIN_LAST_ARRIVAL_FRACTION}) of the window" if withc else "no competitor"))
    if ignore_eos:
        mis = [m.output_mismatch_completed for m in arms]
        checks.append(_chk("realized_output_equals_authorized", (sum(x or 0 for x in mis) == 0)
                           if all(x is not None for x in mis) else None,
                           f"{sum(x or 0 for x in mis)} completed request(s) with output_tokens != max_output_tokens"))
    # 11-12. protocol v5 (PROTOCOL_V5_DRAFT §5.1): the cell's cap is the one applied; slot occupancy is reconstructable
    if protocol_version >= 5:
        checks.append(_cap_configured(arms, expected_cap, path))
        fr = [m.occ_recon_exact_frac for m in arms]
        ok = bool(arms) and all(x is not None for x in fr)
        worst_recon = min(x for x in fr if x is not None) if ok else None
        basis = sorted({str(m.occ_recon_time_basis) for m in arms})
        checks.append(_chk("occupancy_reconstruction",
                           (worst_recon >= MIN_RECON_EXACT_FRACTION) if worst_recon is not None else None,
                           f"lowest arm exact agreement {worst_recon:.3f} (min {MIN_RECON_EXACT_FRACTION}; time basis "
                           f"{basis})" if worst_recon is not None else "unavailable (no sampled gateway in-flight)",
                           severity="flag"))
    # v4 R2: feasibility gates classify the operating regime instead of invalidating the point
    feas = {"competitor_completion", "victim_latency_censoring"}
    regime = None
    if feasibility_gates == "classify":
        fc = [g for g in checks if g["name"] in feas]
        regime = "feasible" if all(g["passed"] for g in fc) else "overload"
        for g in fc:
            g["severity"] = "regime"
    passed = all(c["passed"] for c in checks if c["severity"] == "fail")
    flags = [c["name"] for c in checks if c["severity"] == "flag" and not c["passed"]]
    return {"passed": passed, "checks": checks, "flags": flags, "regime": regime,
            "thresholds": {"max_backend_error_fraction": MAX_BACKEND_ERROR_FRACTION,
                           "max_http_400_fraction": MAX_HTTP_400_FRACTION,
                           "min_admission_fraction": MIN_ADMISSION_FRACTION,
                           "min_competitor_completion": MIN_COMPETITOR_COMPLETION,
                           "max_victim_censored_fraction": MAX_VICTIM_CENSORED_FRACTION,
                           "max_first_arrival_fraction": MAX_FIRST_ARRIVAL_FRACTION,
                           "min_last_arrival_fraction": MIN_LAST_ARRIVAL_FRACTION,
                           "min_recon_exact_fraction": MIN_RECON_EXACT_FRACTION}}


def _cap_configured(arms: list[RunMetrics], expected_cap: int | None, path: str) -> dict[str, Any]:
    """Gateway path: every arm's resolved cap equals the cell's C, and neither the gateway's sampled in-flight count
    nor the in-flight count rebuilt from timestamps ever exceeds C. Direct path: no gateway cap applies (recorded)."""
    caps = sorted({m.gw_inflight_cap for m in arms}, key=str)
    smax = [m.gw_inflight_max for m in arms if m.gw_inflight_max is not None]
    rmax = [m.occ_recon_max for m in arms if m.occ_recon_max is not None]
    seen = f"sampled max {max(smax) if smax else 'n/a'}, rebuilt max {max(rmax) if rmax else 'n/a'}"
    if path == "direct":
        return _chk("cap_configured", bool(arms), f"direct path: no gateway cap (safety stream cap {caps}); {seen}")
    if expected_cap is None or not arms or any(c is None for c in caps) or len(rmax) != len(arms):
        return _chk("cap_configured", None, f"unavailable (expected {expected_cap}, resolved {caps})")
    ok = caps == [expected_cap] and all(x <= expected_cap for x in (*smax, *rmax))
    return _chk("cap_configured", ok, f"resolved cap {caps} (expected {expected_cap}); {seen}")


def apply_gates(analysis: dict, validity: dict) -> dict:
    """Return analysis with classification `invalid` when a fail-severity gate failed (original kept)."""
    out = dict(analysis)
    if not validity["passed"]:
        out["classification_unvalidated"] = analysis.get("classification")
        out["classification"] = "invalid"
    return out


def finite(x: float | None) -> bool:
    return x is not None and bool(np.isfinite(x))
