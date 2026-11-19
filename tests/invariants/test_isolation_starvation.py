from quotashift.gateway.ledger import TokenLedger
from quotashift.schedulers.simple import StaticQuota
from quotashift.schema import WorkloadConfig
from tests.conftest import tenant
from tests.invariants.helpers import assert_accounting, sim_run


class CheckingQuota(StaticQuota):
    """Wraps StaticQuota and asserts isolation every time the policy is consulted."""

    name = "checking_quota"

    def select(self, view):
        led = view.ledger
        for t, q in led.quotas.items():
            assert led.reserved[t] <= q, f"tenant {t} exceeded its quota without borrowing"
        return super().select(view)


def test_tenant_isolation_without_borrowing(small_workload):
    led = TokenLedger({"A": 2000, "B": 4000, "C": 2000}, allow_borrow=False)
    items, rec, gw, eng, _ = sim_run(small_workload, CheckingQuota(), ledger=led, end_extra=200)
    assert_accounting(items, rec, gw, eng)
    # noisy tenant C cannot exceed its reservation even when A/B are idle
    assert led.reserved == {"A": 0, "B": 0, "C": 0}


def test_no_starvation_under_feasible_load():
    """Feasible load + finite drain: every tenant's every request completes (round-robin, no starvation)."""
    wl = WorkloadConfig(workload_id="feasible", duration_s=30, max_model_len=4096,
                        tenants=[tenant("A", 1.0), tenant("B", 1.0), tenant("C", 3.0, out_median=200)])
    led = TokenLedger({"A": 3000, "B": 3000, "C": 3000}, allow_borrow=True)
    items, rec, gw, eng, _ = sim_run(wl, StaticQuota(max_inflight_per_tenant=4), ledger=led, end_extra=300)
    assert_accounting(items, rec, gw, eng)
    by_t = {}
    for r in rec.rows.values():
        by_t.setdefault(r["tenant_id"], set()).add(r["terminal_status"])
    assert all(s == {"completed"} for s in by_t.values()), by_t
