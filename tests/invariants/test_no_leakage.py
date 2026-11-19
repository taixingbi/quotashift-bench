import dataclasses

import pytest

from quotashift.config import BackendConfig
from quotashift.gateway.core import Gateway
from quotashift.instrumentation.recorder import RunRecorder
from quotashift.runtime.runner import make_backend
from quotashift.schedulers.base import GatewayView
from quotashift.schedulers.simple import FCFSPassThrough, OracleSJF
from quotashift.schema import OracleInfo, Request
from tests.invariants.helpers import sim_run

FORBIDDEN = ("realized", "oracle", "true_output", "target_out")


def _walk(obj, seen=None):
    seen = seen if seen is not None else set()
    if id(obj) in seen:
        return
    seen.add(id(obj))
    yield obj
    if isinstance(obj, dict) or hasattr(obj, "items") and callable(obj.items):
        for k, v in obj.items():
            yield from _walk(k, seen)
            yield from _walk(v, seen)
    elif isinstance(obj, list | tuple | set | frozenset):
        for v in obj:
            yield from _walk(v, seen)
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            yield from _walk(getattr(obj, f.name), seen)


def test_policy_never_sees_oracle(small_workload):
    views: list[GatewayView] = []

    class Spy(FCFSPassThrough):
        name = "spy"

        def select(self, view):
            views.append(view)
            return super().select(view)

    items, *_ = sim_run(small_workload, Spy())
    assert views
    truth = {i.request.request_id: i.oracle.realized_output_tokens for i in items}
    for v in views[:200]:
        for o in _walk(v):
            assert not isinstance(o, OracleInfo)
            if isinstance(o, Request):
                dumped = o.model_dump()
                assert not any(any(f in k for f in FORBIDDEN) for k in dumped)
            if isinstance(o, str):
                assert not any(f in o for f in FORBIDDEN)
    # the only output-length information in a Request is the requested cap
    assert all(it.request.max_output_tokens >= truth[it.request.request_id] for it in items)


def test_non_deployable_policy_refused():
    with pytest.raises(ValueError, match="non-deployable"):
        Gateway(OracleSJF(), ["A"], RunRecorder("e", "r"))


def test_real_vllm_backend_never_gets_oracle_side_channel():
    be = make_backend(BackendConfig(kind="vllm", base_url="http://127.0.0.1:9", model="m"), "http://127.0.0.1:9")
    assert be.send_mock_oracle_header is False
    be_mock = make_backend(BackendConfig(kind="mock_http"), "http://127.0.0.1:9")
    assert be_mock.send_mock_oracle_header is True
