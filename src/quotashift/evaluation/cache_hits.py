"""Per-request prefix-cache hits (`usage.prompt_tokens_details.cached_tokens`) aggregated per tenant/class.

Source: vLLM with `--enable-prompt-tokens-details`. Tenant identity comes from the gateway's own trace labels
(`tenant_id`), never from vLLM. Null handling (docs/SELFHOST.md §7):
- `cached_tokens: 0` is a valid observed measurement (zero-hit request) and is included.
- Absent / `prompt_tokens_details: null` is *missing telemetry*, never imputed as 0. Stock vLLM 0.17.1 returns
  null for any zero-hit request; the target's local patch fixes this for /v1/chat/completions only, so the
  /v1/completions path (live runner) still reports null for zero-hit requests.

Token-weighted (never a mean of per-request ratios), over completed requests with a valid measurement:

    coverage            = completed requests with a numeric cached_tokens / completed requests
    hit_ratio_reported  = sum(cached_tokens) / sum(prompt_tokens) over those requests

When coverage < 1 the missing requests are the zero-hit ones (on this target), so `hit_ratio_reported` is biased
upward (toward warm requests). Cancelled / timed-out requests carry no usage and are counted separately
(`noncompleted`), never in the ratio. Never a substitute for the engine-global per-arm counters.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def _stats(g: pd.DataFrame) -> dict[str, Any]:
    done = g[g["terminal_status"] == "completed"]
    nonc = int(len(g) - len(done))  # cancelled / timed out / rejected / errors: no usage -> not in the ratio
    if "cached_tokens_reported" not in done:
        return {"completed": int(len(done)), "noncompleted": nonc, "reporting": 0, "zero_hit_reported": 0,
                "coverage": None, "hit_ratio_reported": None, "cached_tokens_sum": None,
                "prompt_tokens_reporting_sum": None}
    ct = pd.to_numeric(done["cached_tokens_reported"], errors="coerce")
    pt = pd.to_numeric(done["prompt_tokens_reported"], errors="coerce")
    rep = ct.notna() & pt.notna() & (pt > 0)
    n, k = int(len(done)), int(rep.sum())
    num, den = float(ct[rep].sum()), float(pt[rep].sum())
    return {"completed": n, "noncompleted": nonc, "reporting": k, "zero_hit_reported": int((ct[rep] == 0).sum()),
            "coverage": (k / n) if n else None,
            "hit_ratio_reported": (num / den) if den > 0 else None,
            "cached_tokens_sum": num if k else None, "prompt_tokens_reporting_sum": den if k else None}


def cached_token_summary(df: pd.DataFrame) -> dict[str, Any]:
    """{'by_class': {victim|competitor: stats}, 'by_tenant': {tenant: stats}, 'any_reported': bool}."""
    if not len(df):
        return {"by_class": {}, "by_tenant": {}, "any_reported": False}
    by_class = {str(c): _stats(g) for c, g in df.groupby("workload_class")}
    by_tenant = {str(t): _stats(g) for t, g in df.groupby("tenant_id")}
    any_rep = any((s["reporting"] or 0) > 0 for s in by_tenant.values())
    return {"by_class": by_class, "by_tenant": by_tenant, "any_reported": any_rep,
            "note": "token-weighted over completed requests with a valid cached_tokens (0 included); "
                    "null = missing telemetry (not 0); see coverage"}


def engine_reconciliation(summary_ct: dict[str, Any], df: pd.DataFrame, engine: dict | None) -> dict[str, Any]:
    """Cross-check Σ per-request cached_tokens against the engine's Δprefix_cache_hits_total for the same arm.

    residual = engine Δhits − Σ reported cached_tokens (completed requests). Hits are non-negative, so when the
    arm's attribution is *exact* (every engine token accounted for by this run's completed requests, no
    unrelated traffic) and residual == 0, every request that reported null had exactly 0 hits. Only then a
    complete-coverage ratio `hit_ratio_all_completed_reconciled` = Σ cached / Σ prompt over ALL completed
    requests is reported, labelled as derived from the reconciliation — never as an observation, and the
    reported-only ratio and coverage stay unchanged beside it."""
    e = engine or {}
    hits = e.get("prefix_cache_hits_total")
    tenants = summary_ct.get("by_tenant") or {}
    per_req = sum((t.get("cached_tokens_sum") or 0.0) for t in tenants.values())
    exact = e.get("attribution_mode") == "exact" and e.get("unrelated_traffic_suspected") is False
    residual = (float(hits) - per_req) if isinstance(hits, (int, float)) else None
    implied_zero = bool(exact and residual is not None and abs(residual) < 0.5)
    out: dict[str, Any] = {"engine_prefix_hits": hits, "per_request_cached_sum": per_req, "residual": residual,
                           "attribution_exact": exact, "nulls_implied_zero": implied_zero}
    if implied_zero and len(df):
        done = df[df["terminal_status"] == "completed"]
        ct = pd.to_numeric(done.get("cached_tokens_reported"), errors="coerce").fillna(0.0)
        pt = pd.to_numeric(done["prompt_tokens_reported"], errors="coerce")
        ok = pt.notna() & (pt > 0)
        for key, col in (("by_class", "workload_class"), ("by_tenant", "tenant_id")):
            for name, idx in done[ok].groupby(col).groups.items():
                den = float(pt[idx].sum())
                summary_ct[key][str(name)]["hit_ratio_all_completed_reconciled"] = (
                    float(ct[idx].sum()) / den if den > 0 else None)
    return out
