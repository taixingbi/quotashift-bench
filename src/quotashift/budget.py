"""Matched-budget accounting and fail-closed verification for attack/control pairs.

QuotaShift's experimental variable is the *workload scenario*. For the comparison
to be honest, an attack scenario and its control must offer the *same authorized
budget* along the dimensions the comparison declares as matched (plan §2, §5):
otherwise a victim-degradation difference could be explained by one side simply
sending more work.

This module computes the planned budget of a compiled trace and compares an
attack trace to its control trace. Matching is checked against a pre-registered
tolerance (`comparison.budget_tolerance`), fail-closed: if a dimension the
comparison marks as matched disagrees by more than the tolerance,
`verify_matched_budget` raises. The full report (including unmatched dimensions
and absolute deltas) is always returned so discrepancies are recorded, never
hidden (plan §2: "Record both requested and actual token usage, and report
budget discrepancies").

Budgets here are *planned/requested* quantities (input tokens, requested max
output tokens). Realized output is a simulator/engine output and is reported
separately; it is never used to decide whether budgets match.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quotashift.scenario import Comparison
    from quotashift.schema import TraceItem


@dataclass(frozen=True)
class TraceBudget:
    """Planned budget of a compiled trace (requested quantities, not realized)."""

    requests: int
    input_tokens: int
    requested_output_tokens: int
    realized_output_tokens: int  # simulator ground truth; reported, never matched on

    @property
    def total_tokens(self) -> int:
        """Combined requested budget (prefill + requested decode)."""
        return self.input_tokens + self.requested_output_tokens

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def summarize_trace(trace: list[TraceItem]) -> TraceBudget:
    """Total planned budget across every request in `trace`."""
    req = inp = out = realized = 0
    for it in trace:
        r = it.request
        req += 1
        inp += r.input_token_count
        out += r.max_output_tokens
        realized += it.oracle.realized_output_tokens
    return TraceBudget(requests=req, input_tokens=inp, requested_output_tokens=out, realized_output_tokens=realized)


def _rel_delta(attack: int, control: int) -> float:
    """Relative difference |a-c| / max(a,c). Zero when both are zero."""
    hi = max(abs(attack), abs(control))
    return 0.0 if hi == 0 else abs(attack - control) / hi


# Which dimension each matched-flag gates. Per the plan, the matched token budget
# is the *total* (prefill + requested decode): A2/A3 deliberately trade input length
# for request count while holding the total fixed. The input/output split and the
# realized output are always reported, but never gate the match on their own.
_REQUEST_DIM = "requests"
_TOKEN_DIM = "total_tokens"


def budget_report(
    attack: TraceBudget, control: TraceBudget, comparison: Comparison
) -> dict:
    """Compare attack vs control budgets against the pre-registered tolerance.

    Returns a JSON-serializable report. `matched` is True iff every dimension the
    comparison requires (request count and/or total tokens) agrees within tolerance.
    All dimensions are reported with their deltas regardless of what is gated.
    """
    tol = comparison.budget_tolerance
    dims = {}
    for name, a, c in (
        ("requests", attack.requests, control.requests),
        ("total_tokens", attack.total_tokens, control.total_tokens),
        ("input_tokens", attack.input_tokens, control.input_tokens),
        ("requested_output_tokens", attack.requested_output_tokens, control.requested_output_tokens),
        ("realized_output_tokens", attack.realized_output_tokens, control.realized_output_tokens),
    ):
        dims[name] = {"attack": a, "control": c, "abs_delta": abs(a - c), "rel_delta": round(_rel_delta(a, c), 6)}

    required: list[str] = []
    if comparison.matched_request_budget:
        required.append(_REQUEST_DIM)
    if comparison.matched_token_budget:
        required.append(_TOKEN_DIM)

    violations = [d for d in required if dims[d]["rel_delta"] > tol]
    return {
        "tolerance": tol,
        "required_matched_dims": required,
        "violations": violations,
        "matched": not violations,
        "dimensions": dims,
    }


class BudgetMismatch(ValueError):
    """A matched dimension disagrees by more than the pre-registered tolerance."""

    def __init__(self, report: dict) -> None:
        self.report = report
        viols = ", ".join(
            f"{d}: attack={report['dimensions'][d]['attack']} vs control={report['dimensions'][d]['control']} "
            f"(rel {report['dimensions'][d]['rel_delta']:.3f} > tol {report['tolerance']})"
            for d in report["violations"]
        )
        super().__init__(f"matched-budget violation: {viols}")


def verify_matched_budget(
    attack: TraceBudget, control: TraceBudget, comparison: Comparison
) -> dict:
    """Fail-closed gate: raise `BudgetMismatch` if a required dimension is unmatched.

    Returns the full report when it passes so callers can record it.
    """
    report = budget_report(attack, control, comparison)
    if not report["matched"]:
        raise BudgetMismatch(report)
    return report
