import pandas as pd
import pytest

from risksched.evaluation.metrics import summarize
from risksched.gateway.ledger import TokenLedger
from risksched.schedulers.simple import FCFSPassThrough, StaticQuota
from risksched.serving.engine_model import EngineParams
from tests.invariants.helpers import assert_accounting, sim_run


@pytest.mark.parametrize("policy_factory,ledger_factory", [
    (lambda: FCFSPassThrough(), lambda: None),
    (lambda: FCFSPassThrough(max_inflight=8), lambda: None),
    (lambda: StaticQuota(max_inflight_per_tenant=4), lambda: TokenLedger({"A": 5000, "B": 5000, "C": 5000})),
    (lambda: StaticQuota(), lambda: TokenLedger({"A": 3000, "B": 6000, "C": 3000}, allow_borrow=True)),
])
def test_every_offered_request_has_exactly_one_terminal(small_workload, policy_factory, ledger_factory):
    items, rec, gw, eng, _ = sim_run(small_workload, policy_factory(), ledger=ledger_factory())
    assert_accounting(items, rec, gw, eng)
    s = summarize(pd.DataFrame(list(rec.rows.values())), window_s=small_workload.duration_s)
    assert s["accounting_conserved"]
    assert sum(s["status_counts"].values()) == s["offered"] == len(items)


def test_run_cutoff_cancels_unfinished(small_workload):
    # single-sequence engine + zero drain => backlog unfinished at the stop-time cap
    items, rec, gw, eng, _ = sim_run(small_workload, FCFSPassThrough(), end_extra=0.0,
                                     params=EngineParams(max_num_seqs=1, c_decode_s=0.01, max_model_len=4096))
    statuses = pd.Series([r["terminal_status"] for r in rec.rows.values()])
    assert (statuses == "cancelled").sum() > 0
    assert all(r["terminal_detail"] == "run_cutoff" for r in rec.rows.values() if r["terminal_status"] == "cancelled")
    assert_accounting(items, rec, gw, eng)


def test_gateway_queue_timeout(small_workload):
    items, rec, gw, eng, _ = sim_run(small_workload, StaticQuota(max_inflight_per_tenant=1), max_queue_wait_s=1.0,
                                     params=EngineParams(max_num_seqs=2, max_model_len=4096))
    tos = [r for r in rec.rows.values() if r["terminal_status"] == "timed_out"]
    assert tos and all(r["terminal_detail"] == "gateway_queue_timeout" for r in tos)
    assert all(r["t_sent"] is None for r in tos)
    assert_accounting(items, rec, gw, eng)


def test_client_e2e_timeout(small_workload):
    items, rec, gw, eng, _ = sim_run(small_workload, FCFSPassThrough(), request_timeout_s=0.5,
                                     params=EngineParams(max_num_seqs=2, max_model_len=4096))
    tos = [r for r in rec.rows.values() if r["terminal_detail"] == "client_e2e_timeout"]
    assert tos
    assert_accounting(items, rec, gw, eng)


def test_backend_rejection_is_explicit_row(small_workload):
    # engine context smaller than the workload's => engine rejects some requests
    items, rec, gw, eng, _ = sim_run(small_workload, FCFSPassThrough(), params=EngineParams(max_model_len=600))
    errs = [r for r in rec.rows.values() if r["terminal_status"] == "backend_error"]
    assert errs and all(r["terminal_detail"].startswith("engine_rejected") for r in errs)
    assert_accounting(items, rec, gw, eng)


def test_virtual_time_runs_are_bit_identical(small_workload):
    def evs():
        _, rec, *_ = sim_run(small_workload, StaticQuota(max_inflight_per_tenant=3),
                             ledger=TokenLedger({"A": 4000, "B": 4000, "C": 4000}, allow_borrow=True))
        return [(e.request_id, e.event, e.t_rel_s, e.output_tokens) for e in rec.events]
    assert evs() == evs()


def test_policy_cannot_invent_or_duplicate_requests(small_workload):
    class Rogue(FCFSPassThrough):
        name = "rogue"

        def select(self, view):
            ids = super().select(view)
            return ["does-not-exist"] + ids + ids

    items, rec, gw, eng, _ = sim_run(small_workload, Rogue())
    assert_accounting(items, rec, gw, eng)
