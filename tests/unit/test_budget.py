"""Hard budget enforcement in the gateway accountant (fail-closed)."""

from __future__ import annotations

import pytest

from quotashift.gateway.accounting import Accountant, BudgetExceeded, Caps, DuplicateRequest
from quotashift.gateway.ledger import TokenLedger


def _acct(total=5, per_tenant=3, inflight=4, qtokens=10000) -> Accountant:
    caps = Caps(max_total_requests=total, max_requests_per_tenant=per_tenant,
                max_input_tokens_per_request=100, max_output_tokens_per_request=100,
                max_global_inflight=inflight)
    ledger = TokenLedger({"a": qtokens, "b": qtokens}, allow_borrow=False)
    return Accountant(caps=caps, ledger=ledger)


def test_caps_reject_nonpositive():
    with pytest.raises(ValueError):
        Caps(max_total_requests=0, max_requests_per_tenant=1, max_input_tokens_per_request=1,
             max_output_tokens_per_request=1, max_global_inflight=1)


def test_per_tenant_request_cap():
    acc = _acct(per_tenant=2)
    acc.admit("a", "a-1", 10, 10)
    acc.admit("a", "a-2", 10, 10)
    with pytest.raises(BudgetExceeded) as e:
        acc.admit("a", "a-3", 10, 10)
    assert e.value.reason == "max_requests_per_tenant"


def test_total_request_cap_aborts():
    acc = _acct(total=2, per_tenant=5)
    acc.admit("a", "a-1", 10, 10)
    acc.admit("b", "b-1", 10, 10)
    with pytest.raises(BudgetExceeded) as e:
        acc.admit("a", "a-2", 10, 10)
    assert e.value.reason == "max_total_requests"
    assert acc.aborted and acc.abort_reason == "max_total_requests"


def test_per_request_shape_caps():
    acc = _acct()
    with pytest.raises(BudgetExceeded) as e:
        acc.admit("a", "a-1", 10_000, 10)
    assert e.value.reason == "input_tokens_per_request"


def test_token_quota_isolation():
    acc = _acct(qtokens=250)  # room for ~1 reservation of 200 tokens (100+100)
    acc.admit("a", "a-1", 100, 100)
    with pytest.raises(BudgetExceeded) as e:
        acc.admit("a", "a-2", 100, 100)
    assert e.value.reason == "tenant_token_quota"


def test_idempotent_admit_and_record():
    acc = _acct()
    acc.admit("a", "a-1", 10, 10)
    with pytest.raises(DuplicateRequest):
        acc.admit("a", "a-1", 10, 10)
    acc.record("a", "a-1", 10, 7, ok=True)
    with pytest.raises(DuplicateRequest):
        acc.record("a", "a-1", 10, 7, ok=True)
    assert acc.counters["a"].requests_completed == 1
    assert acc.counters["a"].output_tokens == 7


def test_record_releases_reservation():
    acc = _acct()
    acc.admit("a", "a-1", 100, 100)
    assert acc.ledger.reserved["a"] == 200
    acc.record("a", "a-1", 100, 50, ok=True)
    assert acc.ledger.reserved["a"] == 0
    assert acc.ledger.charged["a"] == 150
