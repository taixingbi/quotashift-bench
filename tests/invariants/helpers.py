from __future__ import annotations

from quotashift.gateway.core import Gateway
from quotashift.gateway.ledger import TokenLedger
from quotashift.instrumentation.recorder import RunRecorder, validate_events
from quotashift.runtime.clients import OpenLoopClient
from quotashift.runtime.sim import SimConfig, run_simulation
from quotashift.schedulers.base import SchedulerPolicy
from quotashift.serving.engine_model import EngineModel, EngineParams
from quotashift.workload.generator import generate_trace


def sim_run(wl, policy: SchedulerPolicy, seed=11, ledger=None, end_extra=60.0, max_queue_wait_s=None,
            request_timeout_s=None, params=None):
    items = generate_trace(wl, seed)
    rec = RunRecorder("test", f"run-{policy.name}-{seed}", clock="virtual")
    gw = Gateway(policy, [t.tenant_id for t in wl.tenants], rec, ledger=ledger, max_queue_wait_s=max_queue_wait_s)
    eng = EngineModel(params or EngineParams(max_model_len=wl.max_model_len))
    ts = run_simulation(OpenLoopClient(items), gw, eng,
                        SimConfig(end_time_s=wl.duration_s + end_extra, request_timeout_s=request_timeout_s))
    return items, rec, gw, eng, ts


def assert_accounting(items, rec, gw, eng):
    assert set(rec.rows) == {i.request.request_id for i in items}
    assert validate_events(rec.events, set(rec.rows)) == []
    assert rec.violations == []
    assert rec.non_terminal() == []
    assert not gw.inflight and gw.queued_count == 0
    assert not eng.has_work()
    assert eng.free_blocks == eng.params.kv_blocks_total
    if gw.ledger is not None:
        assert gw.ledger.total_reserved == 0
        gw.ledger.check_invariants()


__all__ = ["sim_run", "assert_accounting", "TokenLedger"]
