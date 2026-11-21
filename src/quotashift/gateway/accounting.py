"""Per-tenant request accounting and fixed hard budgets for the gateway.

Budgets are fixed and identical across a scenario and its control, for experimental
equivalence (plan §1, Phase 1). This is *not* a defense or an adaptive scheduler:
it only enforces the authorized caps and attributes usage per synthetic tenant.

Fail-closed: when any cap is reached the gateway stops admitting and the run is
marked aborted. Records are idempotent per request_id (a replay never double-counts).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quotashift.gateway.ledger import TokenLedger


class BudgetExceeded(Exception):
    """Raised when a hard cap is hit. `reason`/`cap`/`observed` are structured."""

    def __init__(self, reason: str, cap: int | float, observed: int | float) -> None:
        super().__init__(reason)
        self.reason = reason
        self.cap = cap
        self.observed = observed

    def as_error(self) -> dict:
        return {"error": {"type": "budget_exhausted", "reason": self.reason,
                          "cap": self.cap, "observed": self.observed}}


@dataclass
class Caps:
    max_total_requests: int
    max_requests_per_tenant: int
    max_input_tokens_per_request: int
    max_output_tokens_per_request: int
    max_global_inflight: int

    def __post_init__(self) -> None:
        for name in ("max_total_requests", "max_requests_per_tenant", "max_input_tokens_per_request",
                     "max_output_tokens_per_request", "max_global_inflight"):
            v = getattr(self, name)
            if not isinstance(v, int) or v < 1:
                raise ValueError(f"cap {name} must be a positive int (got {v!r}); gateway refuses to start")


@dataclass
class TenantCounters:
    requests_admitted: int = 0
    requests_completed: int = 0
    requests_rejected: int = 0
    input_tokens: int = 0  # realized, from backend usage
    output_tokens: int = 0  # realized, from backend usage
    reserved_peak: int = 0


@dataclass
class Accountant:
    caps: Caps
    ledger: TokenLedger
    aborted: bool = False
    abort_reason: str | None = None
    total_admitted: int = 0
    counters: dict[str, TenantCounters] = field(default_factory=dict)
    _seen: set[str] = field(default_factory=set)
    _recorded: set[str] = field(default_factory=set)

    def _c(self, tenant: str) -> TenantCounters:
        return self.counters.setdefault(tenant, TenantCounters())

    def check_shapes(self, input_tokens: int, max_output_tokens: int) -> None:
        if input_tokens > self.caps.max_input_tokens_per_request:
            raise BudgetExceeded("input_tokens_per_request", self.caps.max_input_tokens_per_request, input_tokens)
        if max_output_tokens > self.caps.max_output_tokens_per_request:
            raise BudgetExceeded("output_tokens_per_request", self.caps.max_output_tokens_per_request, max_output_tokens)

    def admit(self, tenant: str, request_id: str, input_tokens: int, max_output_tokens: int) -> None:
        """Admit a new request and reserve its planning tokens. Idempotent per id.

        Raises BudgetExceeded when a hard request cap or the tenant's in-flight token
        quota is reached; raises DuplicateRequest on a replayed id. On any rejection
        no counters change (the reservation, if taken, is rolled back).
        """
        if request_id in self._seen:
            raise DuplicateRequest(request_id)
        self.check_shapes(input_tokens, max_output_tokens)
        c = self._c(tenant)
        if self.total_admitted >= self.caps.max_total_requests:
            self._abort("max_total_requests")
            raise BudgetExceeded("max_total_requests", self.caps.max_total_requests, self.total_admitted)
        if c.requests_admitted >= self.caps.max_requests_per_tenant:
            raise BudgetExceeded("max_requests_per_tenant", self.caps.max_requests_per_tenant, c.requests_admitted)
        amount = input_tokens + max_output_tokens
        if not self.ledger.reserve(tenant, request_id, amount):
            raise BudgetExceeded("tenant_token_quota", self.ledger.quotas.get(tenant, 0),
                                 self.ledger.reserved.get(tenant, 0) + amount)
        self._seen.add(request_id)
        self.total_admitted += 1
        c.requests_admitted += 1
        c.reserved_peak = max(c.reserved_peak, self.ledger.reserved.get(tenant, 0))

    def rollback(self, tenant: str, request_id: str) -> None:
        """Undo `admit` for a request that never reached the backend (queue full/timeout,
        rate limit, client disconnect while queued). Releases its reservation without
        charge and frees the id, so the request consumes no budget and may be retried."""
        if request_id not in self._seen or request_id in self._recorded:
            return
        self._seen.discard(request_id)
        if self.ledger.holds(request_id):
            self.ledger.release(request_id, 0)
        self.total_admitted -= 1
        c = self._c(tenant)
        c.requests_admitted -= 1
        c.requests_rejected += 1

    def is_seen(self, request_id: str) -> bool:
        return request_id in self._seen

    def record(self, tenant: str, request_id: str, input_tokens: int, output_tokens: int, ok: bool) -> None:
        """Record terminal outcome exactly once per request_id and release tokens."""
        if request_id in self._recorded:
            raise DuplicateRequest(request_id)
        self._recorded.add(request_id)
        if self.ledger.holds(request_id):
            charged = max(0, input_tokens) + max(0, output_tokens) if ok else 0
            self.ledger.release(request_id, charged if ok else 0)
        c = self._c(tenant)
        if ok:
            c.requests_completed += 1
            c.input_tokens += max(0, input_tokens)
            c.output_tokens += max(0, output_tokens)
        else:
            c.requests_rejected += 1

    def _abort(self, reason: str) -> None:
        self.aborted = True
        self.abort_reason = reason

    def snapshot(self) -> dict:
        return {
            "aborted": self.aborted,
            "abort_reason": self.abort_reason,
            "total_admitted": self.total_admitted,
            "per_tenant": {t: vars(c) for t, c in sorted(self.counters.items())},
        }


class DuplicateRequest(Exception):
    def __init__(self, request_id: str) -> None:
        super().__init__(f"duplicate request_id {request_id}")
        self.request_id = request_id
