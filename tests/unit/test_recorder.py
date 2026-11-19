import pytest

from quotashift.instrumentation.recorder import LifecycleError, RunRecorder, validate_events
from quotashift.schema import EventType as E
from quotashift.schema import Request, SLOType


def req(rid="r"):
    return Request(request_id=rid, tenant_id="A", arrival_time_s=0, prompt_text="x y", input_token_count=2,
                   max_output_tokens=4, workload_class="c", slo_type=SLOType.INTERACTIVE, ttft_deadline_ms=1,
                   seed=0, trace_id="t")


def test_happy_path_and_validate():
    rec = RunRecorder("e", "run", clock="virtual")
    rec.register(req())
    for i, k in enumerate([E.OFFERED, E.ACCEPTED, E.QUEUED, E.SENT_TO_BACKEND, E.FIRST_TOKEN]):
        rec.event("r", k, float(i))
    rec.event("r", E.COMPLETED, 9.0, output_tokens=3)
    assert rec.rows["r"]["terminal_status"] == "completed"
    assert rec.rows["r"]["output_tokens"] == 3
    assert validate_events(rec.events, {"r"}) == []


def test_illegal_transition_raises():
    rec = RunRecorder("e", "run")
    rec.register(req())
    rec.event("r", E.OFFERED, 0)
    with pytest.raises(LifecycleError):
        rec.event("r", E.FIRST_TOKEN, 1)


def test_duplicate_completion_detected():
    rec = RunRecorder("e", "run", strict=False)
    rec.register(req())
    for k in (E.OFFERED, E.REJECTED, E.COMPLETED):
        rec.event("r", k, 0)
    assert rec.violations and "after terminal" in rec.violations[0]
    assert rec.rows["r"]["terminal_status"] == "rejected"


def test_duplicate_registration():
    rec = RunRecorder("e", "run")
    rec.register(req())
    with pytest.raises(LifecycleError):
        rec.register(req())


def test_validate_flags_missing_terminal_and_time_reversal():
    rec = RunRecorder("e", "run", strict=False)
    rec.register(req("a"))
    rec.register(req("b"))
    rec.event("a", E.OFFERED, 5.0)
    rec.event("a", E.ACCEPTED, 4.0)
    errs = validate_events(rec.events, {"a", "b"})
    assert any("non-monotonic" in e for e in errs)
    assert any("a: 0 terminal" in e for e in errs)
    assert any("b: 0 terminal" in e for e in errs)
