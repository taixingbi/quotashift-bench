"""Phase 1 gateway: identity, per-tenant attribution, budgets, idempotency, egress."""

from __future__ import annotations

import contextlib

import httpx
import pytest
from asgi_lifespan import LifespanManager

from quotashift.config import BackendConfig
from quotashift.gateway.accounting import Caps
from quotashift.gateway.app import GatewayApp, build_app
from quotashift.gateway.forwarder import Forwarder
from quotashift.gateway.identity import TenantRegistry
from quotashift.runtime.runner import local_mock_server

REGISTRY = TenantRegistry.model_validate({"keys": {
    "qs-test-a": {"tenant_id": "victim_a", "experiment_id": "e", "run_id": "r", "role": "victim"},
    "qs-test-b": {"tenant_id": "victim_b", "experiment_id": "e", "run_id": "r", "role": "victim"},
    "qs-test-c": {"tenant_id": "competitor", "experiment_id": "e", "run_id": "r", "role": "competitor"},
}})


def _caps(**over) -> Caps:
    base = dict(max_total_requests=100, max_requests_per_tenant=50, max_input_tokens_per_request=512,
                max_output_tokens_per_request=128, max_global_inflight=4)
    base.update(over)
    return Caps(**base)


@contextlib.contextmanager
def _mock_backend():
    with local_mock_server(BackendConfig(kind="mock_http", model="mock-model", time_scale=1.0)) as url:
        yield url


@contextlib.asynccontextmanager
async def _client(caps: Caps, backend_url: str):
    gw = GatewayApp(REGISTRY, caps, backend_url=backend_url, model="mock-model")
    app = build_app(gw)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://gw") as c:
            yield c, gw


def _chat(msg="hello there friend", **kw):
    return {"messages": [{"role": "user", "content": msg}], "max_tokens": 16, **kw}


async def test_unknown_tenant_rejected():
    with _mock_backend() as url:
        async with _client(_caps(), url) as (c, _gw):
            r = await c.post("/v1/chat/completions", json=_chat(), headers={"authorization": "Bearer nope"})
            assert r.status_code == 401
            r2 = await c.post("/v1/chat/completions", json=_chat())  # no auth
            assert r2.status_code == 401


async def test_valid_forward_and_attribution():
    with _mock_backend() as url:
        async with _client(_caps(), url) as (c, gw):
            for key, tenant in (("qs-test-a", "victim_a"), ("qs-test-a", "victim_a"), ("qs-test-c", "competitor")):
                r = await c.post("/v1/chat/completions", json=_chat(), headers={"authorization": f"Bearer {key}"})
                assert r.status_code == 200, r.text
                assert r.json()["object"] == "chat.completion"
                assert r.headers["x-quotashift-tenant"] == tenant
            assert gw.accountant.counters["victim_a"].requests_completed == 2
            assert gw.accountant.counters["competitor"].requests_completed == 1
            # no cross-tenant misattribution
            assert "victim_b" not in gw.accountant.counters


async def test_idempotent_request_id():
    with _mock_backend() as url:
        async with _client(_caps(), url) as (c, gw):
            h = {"authorization": "Bearer qs-test-a", "x-quotashift-request-id": "fixed-1"}
            r1 = await c.post("/v1/chat/completions", json=_chat(), headers=h)
            r2 = await c.post("/v1/chat/completions", json=_chat(), headers=h)
            assert r1.status_code == 200 and r2.status_code == 409
            assert gw.accountant.counters["victim_a"].requests_admitted == 1


async def test_per_tenant_budget_cutoff():
    with _mock_backend() as url:
        async with _client(_caps(max_requests_per_tenant=2), url) as (c, gw):
            codes = []
            for i in range(4):
                r = await c.post("/v1/chat/completions", json=_chat(),
                                 headers={"authorization": "Bearer qs-test-a", "x-quotashift-request-id": f"a-{i}"})
                codes.append(r.status_code)
            assert codes[:2] == [200, 200]
            assert codes[2] == 429 and codes[3] == 429
            assert gw.accountant.counters["victim_a"].requests_admitted == 2


async def test_per_request_output_cap():
    with _mock_backend() as url:
        async with _client(_caps(max_output_tokens_per_request=8), url) as (c, _gw):
            r = await c.post("/v1/chat/completions", json=_chat(max_tokens=9999),
                             headers={"authorization": "Bearer qs-test-a"})
            assert r.status_code == 429 and r.json()["error"]["reason"] == "output_tokens_per_request"


def test_forwarder_rejects_external_backend():
    with pytest.raises(ValueError, match="private hosts only"):
        Forwarder("http://api.openai.com", model="m")


async def test_forwarder_rejects_url_override_in_body():
    with _mock_backend() as url:
        async with _client(_caps(), url) as (c, _gw):
            r = await c.post("/v1/chat/completions",
                             json=_chat(url="http://evil.example.com"),
                             headers={"authorization": "Bearer qs-test-a"})
            assert r.status_code == 400 and "forbidden body keys" in r.json()["error"]["reason"]


async def test_metrics_endpoint():
    with _mock_backend() as url:
        async with _client(_caps(), url) as (c, _gw):
            await c.post("/v1/chat/completions", json=_chat(), headers={"authorization": "Bearer qs-test-a"})
            m = await c.get("/metrics")
            assert m.status_code == 200 and 'quotashift_requests_completed{tenant="victim_a"}' in m.text
