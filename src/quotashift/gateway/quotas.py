"""Rolling-window RPM/TPM limits with token reservation and usage reconciliation.

Shared by both gateway execution paths (in-process `core.Gateway` used by live
A1–A5/E-series runs, and the FastAPI adapter in `app.py`). Ported from the
pre-consolidation `multitenant/` prototype. Fixed limits only — not a defense.

At admission a request reserves `estimated_input + max_tokens` tokens in every
applicable window (tenant and global). When the request finishes, the entry is
reconciled to the *actual* usage reported by vLLM (`prompt_tokens + completion_tokens`);
if the request never reached the backend (queue timeout, overload, client disconnect
before dispatch) the reservation is refunded entirely. Window = 60 s, rolling.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field


@dataclass
class _Entry:
    t: float
    tokens: int
    rid: str


@dataclass
class RollingWindow:
    """Requests and tokens admitted within the last `window_s` seconds."""

    rpm: int | None = None
    tpm: int | None = None
    window_s: float = 60.0
    _entries: deque[_Entry] = field(default_factory=deque)
    _by_rid: dict[str, _Entry] = field(default_factory=dict)
    _tokens: int = 0

    def _evict(self, now: float) -> None:
        while self._entries and self._entries[0].t <= now - self.window_s:
            e = self._entries.popleft()
            if self._by_rid.get(e.rid) is e:
                del self._by_rid[e.rid]
            self._tokens -= e.tokens

    def usage(self, now: float) -> tuple[int, int]:
        self._evict(now)
        return len(self._entries), self._tokens

    def check(self, now: float, tokens: int) -> str | None:
        """Return the violated limit name, or None if `tokens` more would fit."""
        n, tok = self.usage(now)
        if self.rpm is not None and n + 1 > self.rpm:
            return "rpm"
        if self.tpm is not None and tok + tokens > self.tpm:
            return "tpm"
        return None

    def retry_after_s(self, now: float) -> float:
        self._evict(now)
        if not self._entries:
            return 0.0
        return max(0.0, self._entries[0].t + self.window_s - now)

    def add(self, now: float, rid: str, tokens: int) -> None:
        e = _Entry(now, tokens, rid)
        self._entries.append(e)
        self._by_rid[rid] = e
        self._tokens += tokens

    def reconcile(self, rid: str, actual_tokens: int) -> None:
        """Replace the reserved amount with actual usage (entry keeps its admission time)."""
        e = self._by_rid.get(rid)
        if e is None:  # already aged out of the window: nothing left to adjust
            return
        self._tokens += actual_tokens - e.tokens
        e.tokens = actual_tokens

    def refund(self, rid: str) -> None:
        e = self._by_rid.pop(rid, None)
        if e is None:
            return
        self._tokens -= e.tokens
        e.tokens = 0
        try:
            self._entries.remove(e)  # a refunded request no longer counts toward RPM either
        except ValueError:
            pass


class RateLimiter:
    """Tenant + global windows; admission is atomic across both."""

    def __init__(self, tenant_limits: dict[str, tuple[int | None, int | None]],
                 global_rpm: int | None, global_tpm: int | None, window_s: float = 60.0) -> None:
        self.tenants = {t: RollingWindow(rpm, tpm, window_s) for t, (rpm, tpm) in tenant_limits.items()}
        self.glob = RollingWindow(global_rpm, global_tpm, window_s)
        self.reserved: dict[str, int] = {}

    def try_admit(self, now: float, tenant: str, rid: str, tokens: int) -> tuple[str | None, float]:
        """Return (violation, retry_after_s). violation is None on success."""
        tw = self.tenants[tenant]
        v = tw.check(now, tokens)
        if v is not None:
            return f"tenant_{v}", tw.retry_after_s(now)
        v = self.glob.check(now, tokens)
        if v is not None:
            return f"global_{v}", self.glob.retry_after_s(now)
        tw.add(now, rid, tokens)
        self.glob.add(now, rid, tokens)
        self.reserved[rid] = tokens
        return None, 0.0

    def reconcile(self, tenant: str, rid: str, actual_tokens: int) -> None:
        self.tenants[tenant].reconcile(rid, actual_tokens)
        self.glob.reconcile(rid, actual_tokens)
        self.reserved.pop(rid, None)

    def refund(self, tenant: str, rid: str) -> None:
        self.tenants[tenant].refund(rid)
        self.glob.refund(rid)
        self.reserved.pop(rid, None)


class TenantRate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    rpm: int | None = Field(default=None, gt=0)
    tpm: int | None = Field(default=None, gt=0)


class RateLimits(BaseModel):
    """Fixed RPM/TPM configuration. Absent == unlimited (historical behaviour)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    default_tenant: TenantRate = TenantRate()
    per_tenant: dict[str, TenantRate] = Field(default_factory=dict)
    global_rpm: int | None = Field(default=None, gt=0)
    global_tpm: int | None = Field(default=None, gt=0)
    window_s: float = Field(default=60.0, gt=0)

    def build(self, tenants: list[str]) -> RateLimiter:
        unknown = set(self.per_tenant) - set(tenants)
        if unknown:
            raise ValueError(f"rate limits for unknown tenants: {sorted(unknown)}")
        lim = {t: self.per_tenant.get(t, self.default_tenant) for t in tenants}
        return RateLimiter({t: (r.rpm, r.tpm) for t, r in lim.items()}, self.global_rpm, self.global_tpm,
                           window_s=self.window_s)
