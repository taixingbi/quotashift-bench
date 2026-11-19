"""Load clients: open-loop trace replay and closed-loop fixed concurrency."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from quotashift.schema import TraceItem


@dataclass
class OpenLoopClient:
    """Replays a pre-generated trace at its arrival times (primary mode)."""

    items: list[TraceItem]
    kind: str = "open_loop"

    def initial(self) -> list[tuple[float, TraceItem]]:
        return [(it.request.arrival_time_s, it) for it in self.items]

    def on_terminal(self, rid: str, now: float) -> list[tuple[float, TraceItem]]:
        return []


@dataclass
class ClosedLoopClient:
    """`concurrency` virtual users; each issues a new request when its previous one ends.

    `factory(i, now)` builds the i-th request (with arrival_time_s=now).
    """

    concurrency: int
    total: int
    factory: Callable[[int, float], TraceItem]
    kind: str = "closed_loop"
    _issued: int = field(default=0, init=False)

    def _next(self, now: float) -> list[tuple[float, TraceItem]]:
        if self._issued >= self.total:
            return []
        it = self.factory(self._issued, now)
        self._issued += 1
        return [(now, it)]

    def initial(self) -> list[tuple[float, TraceItem]]:
        out = []
        for _ in range(min(self.concurrency, self.total)):
            out += self._next(0.0)
        return out

    def on_terminal(self, rid: str, now: float) -> list[tuple[float, TraceItem]]:
        return self._next(now)
