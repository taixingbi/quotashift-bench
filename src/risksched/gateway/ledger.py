"""Per-tenant token reservation ledger.

Units are *tokens*. A reservation is a planning upper bound
(input_tokens + requested max_output_tokens); it is NOT realized usage.
On completion the full reservation is released and the *charged* amount
(input + realized output, when known) is accumulated separately for
service accounting, so `max_output_tokens` is never mistaken for usage.

Isolation rule: with `allow_borrow=False` a tenant can never hold more than its
own quota. With `allow_borrow=True` a tenant may additionally use capacity that
is *currently unused* by other tenants; borrowed capacity is not preempted, so
an owner may wait for borrowed tokens to drain (documented in
docs/KNOWN_LIMITATIONS.md). Total reserved never exceeds total capacity.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class LedgerError(RuntimeError):
    pass


@dataclass
class _Res:
    tenant: str
    amount: int
    borrowed: int


@dataclass
class TokenLedger:
    quotas: dict[str, int]  # tenant -> token quota (in-flight reserved tokens)
    allow_borrow: bool = False
    reserved: dict[str, int] = field(default_factory=dict)
    charged: dict[str, int] = field(default_factory=dict)
    _res: dict[str, _Res] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for t, q in self.quotas.items():
            if q < 0:
                raise LedgerError(f"negative quota for {t}")
            self.reserved.setdefault(t, 0)
            self.charged.setdefault(t, 0)

    @property
    def capacity(self) -> int:
        return sum(self.quotas.values())

    @property
    def total_reserved(self) -> int:
        return sum(self.reserved.values())

    def own_headroom(self, tenant: str) -> int:
        return max(0, self.quotas[tenant] - self.reserved[tenant])

    @property
    def free_total(self) -> int:
        return self.capacity - self.total_reserved

    def borrowable(self, tenant: str) -> int:
        """Capacity usable beyond the tenant's own headroom (globally free, unowned-by-it)."""
        if not self.allow_borrow:
            return 0
        return max(0, self.free_total - self.own_headroom(tenant))

    def can_reserve(self, tenant: str, amount: int) -> bool:
        if amount < 0:
            raise LedgerError("negative reservation")
        if amount > self.free_total:
            return False  # never over-commit total capacity (borrowers may have used owners' headroom)
        if not self.allow_borrow:
            return self.reserved[tenant] + amount <= self.quotas[tenant]
        return True

    def reserve(self, tenant: str, rid: str, amount: int) -> bool:
        if rid in self._res:
            raise LedgerError(f"duplicate reservation {rid}")
        if not self.can_reserve(tenant, amount):
            return False
        borrowed = max(0, amount - self.own_headroom(tenant))
        self._res[rid] = _Res(tenant, amount, borrowed)
        self.reserved[tenant] += amount
        self.check_invariants()
        return True

    def release(self, rid: str, charged_tokens: int | None) -> int:
        """Release a reservation. Returns refunded (unused) planning tokens."""
        r = self._res.pop(rid, None)
        if r is None:
            raise LedgerError(f"unknown or already released reservation {rid}")
        self.reserved[r.tenant] -= r.amount
        refund = r.amount
        if charged_tokens is not None:
            if charged_tokens < 0:
                raise LedgerError("negative charge")
            self.charged[r.tenant] += charged_tokens
            refund = max(0, r.amount - charged_tokens)
        self.check_invariants()
        return refund

    def holds(self, rid: str) -> bool:
        return rid in self._res

    def check_invariants(self) -> None:
        for t, v in self.reserved.items():
            if v < 0:
                raise LedgerError(f"negative reserved for {t}")
        if self.total_reserved > self.capacity:
            raise LedgerError("total reserved exceeds capacity")
        per_t: dict[str, int] = {t: 0 for t in self.quotas}
        for r in self._res.values():
            per_t[r.tenant] += r.amount
        if per_t != self.reserved:
            raise LedgerError("reservation conservation violated")
        if not self.allow_borrow:
            for t, v in self.reserved.items():
                if v > self.quotas[t]:
                    raise LedgerError(f"tenant {t} exceeds quota without borrowing")
