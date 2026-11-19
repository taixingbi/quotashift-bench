import pytest
from pydantic import ValidationError

from quotashift.schema import LengthDist, OracleInfo, Request, SLOType, WorkloadConfig
from tests.conftest import tenant


def _req(**kw):
    base = dict(request_id="r", tenant_id="A", arrival_time_s=0.0, prompt_text="hi there", input_token_count=2,
                max_output_tokens=16, workload_class="c", slo_type=SLOType.INTERACTIVE, ttft_deadline_ms=100,
                seed=1, trace_id="t")
    return Request(**(base | kw))


def test_request_has_no_realized_output_field():
    fields = set(Request.model_fields)
    assert not any("realized" in f or "oracle" in f or "true_output" in f for f in fields)
    assert "realized_output_tokens" in OracleInfo.model_fields


def test_request_rejects_extra_fields_and_is_frozen():
    with pytest.raises(ValidationError):
        _req(realized_output_tokens=10)
    r = _req()
    with pytest.raises(ValidationError):
        r.max_output_tokens = 5


def test_request_token_id_length_must_match():
    with pytest.raises(ValidationError):
        _req(prompt_text=None, prompt_token_ids=(1, 2, 3), input_token_count=2)
    assert _req(prompt_text=None, prompt_token_ids=(1, 2), input_token_count=2).input_token_count == 2


def test_request_needs_prompt():
    with pytest.raises(ValidationError):
        _req(prompt_text=None)


def test_reserved_upper_bound_is_planning_not_usage():
    r = _req(input_token_count=2, max_output_tokens=16)
    assert r.reserved_tokens_upper_bound == 18


def test_length_dist_validation():
    with pytest.raises(ValidationError):
        LengthDist(dist="lognormal", median=10)
    with pytest.raises(ValidationError):
        LengthDist(dist="fixed")
    with pytest.raises(ValidationError):
        LengthDist(dist="fixed", value=3, min=5, max=1)


def test_duplicate_tenants_rejected():
    with pytest.raises(ValidationError):
        WorkloadConfig(workload_id="x", duration_s=1, tenants=[tenant("A"), tenant("A")])


def test_onoff_requires_params():
    with pytest.raises(ValidationError):
        tenant("A", process="onoff")
