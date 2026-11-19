import itertools

import numpy as np
import pytest

from quotashift.gateway.ledger import LedgerError, TokenLedger


def test_reserve_release_conservation():
    led = TokenLedger({"A": 100, "B": 100})
    assert led.reserve("A", "r1", 60)
    assert led.reserved == {"A": 60, "B": 0}
    refund = led.release("r1", charged_tokens=25)
    assert refund == 35
    assert led.reserved == {"A": 0, "B": 0}
    assert led.charged["A"] == 25


def test_isolation_without_borrow():
    led = TokenLedger({"A": 100, "B": 100}, allow_borrow=False)
    assert led.reserve("A", "r1", 100)
    assert not led.reserve("A", "r2", 1)  # B's idle capacity is NOT usable
    assert led.reserve("B", "r3", 100)


def test_borrow_only_free_capacity_regression():
    """Regression: two borrowers must not both claim the same idle headroom (over-commit)."""
    led = TokenLedger({"A": 100, "B": 100, "C": 100}, allow_borrow=True)
    assert led.reserve("A", "a1", 250)  # borrows 150 of B/C headroom
    assert not led.reserve("B", "b1", 100)  # only 50 free globally
    assert led.reserve("B", "b2", 50)
    assert led.total_reserved == 300 == led.capacity
    assert not led.can_reserve("C", 1)


def test_errors():
    led = TokenLedger({"A": 10})
    with pytest.raises(LedgerError):
        led.release("nope", None)
    led.reserve("A", "x", 5)
    with pytest.raises(LedgerError):
        led.reserve("A", "x", 1)
    with pytest.raises(LedgerError):
        led.can_reserve("A", -1)
    with pytest.raises(LedgerError):
        TokenLedger({"A": -1})


def test_charged_uses_realized_not_max():
    led = TokenLedger({"A": 1000})
    led.reserve("A", "r", 10 + 500)  # input 10 + max_tokens 500 (planning)
    led.release("r", charged_tokens=10 + 37)  # realized 37 output tokens
    assert led.charged["A"] == 47


@pytest.mark.parametrize("borrow", [False, True])
def test_random_ops_preserve_invariants(borrow):
    rng = np.random.default_rng(0)
    led = TokenLedger({"A": 500, "B": 300, "C": 200}, allow_borrow=borrow)
    live: dict[str, str] = {}
    ids = itertools.count()
    for _ in range(5000):
        if live and rng.random() < 0.45:
            rid = list(live)[rng.integers(len(live))]
            led.release(rid, int(rng.integers(0, 50)))
            del live[rid]
        else:
            t = "ABC"[rng.integers(3)]
            rid = f"r{next(ids)}"
            if led.reserve(t, rid, int(rng.integers(1, 200))):
                live[rid] = t
        led.check_invariants()
        assert all(v >= 0 for v in led.reserved.values())
        assert led.total_reserved <= led.capacity
        if not borrow:
            assert all(led.reserved[t] <= led.quotas[t] for t in led.quotas)
