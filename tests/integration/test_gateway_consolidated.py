"""Consolidated gateway: hashed auth, RPM/TPM, reconciliation, streaming cleanup, slots, timeouts,
idempotency — through the FastAPI adapter (HTTP path) and the in-process core (live-runner path).

All backends here are the CPU mock (simulator timings; not GPU measurements)."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json

import httpx
import pytest
from asgi_lifespan import LifespanManager

from quotashift.config import BackendConfig
from quotashift.gateway.accounting import Caps
from quotashift.gateway.app import GatewayApp, build_app
from quotashift.gateway.core import Gateway
from quotashift.gateway.identity import TenantRegistry
from quotashift.gateway.quotas import RateLimits
from quotashift.instrumentation.recorder import RunRecorder
from quotashift.runtime.runner import local_mock_server
from quotashift.schedulers.simple import make_policy
from quotashift.schema import EventType, Request, SLOType


def _d(k: str) -> str:
    return hashlib.sha256(k.encode()).hexdigest()


REG = TenantRegistry.model_validate({"tenants": [
    {"tenant_id": "victim_a", "experiment_id": "e", "run_id": "r", "role": "victim", "key_sha256": _d("ka")},
    {"tenant_id": "victim_b", "experiment_id": "e", "run_id": "r", "role": "victim", "key_sha256": _d("kb")},
    {"tenant_id": "competitor", "experiment_id": "e", "run_id": "r", "role": "competitor", "key_sha256": _d("kc")},
]})
H = {t: {"authorization": f"Bearer {k}"} for t, k in (("a", "ka"), ("b", "kb"), ("c", "kc"))}


def _caps(**over) -> Caps:
    base = dict(max_total_requests=500, max_requests_per_tenant=300, max_input_tokens_per_request=512,
                max_output_tokens_per_request=256, max_global_inflight=4)
    base.update(over)
    return Caps(**base)


def _chat(words=8, max_tokens=8, **kw):
    return {"messages": [{"role": "user", "content": " ".join(["hello"] * words)}], "max_tokens": max_tokens,
            "ignore_eos": True, **kw}


@pytest.fixture(scope="module")
def backend_url():
    with local_mock_server(BackendConfig(kind="mock_http", model="mock-model", time_scale=1.0)) as url:
        yield url


@contextlib.asynccontextmanager
async def _gw(url: str, caps: Caps | None = None, **kw):
    gw = GatewayApp(REG, caps or _caps(), backend_url=url, model="mock-model", **kw)
    app = build_app(gw)
    async with LifespanManager(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw",
                                     timeout=30) as c:
            yield c, gw, app


def _clean(gw: GatewayApp) -> None:
    """No leaked slots, reservations, waiters or queued requests."""
    assert gw.core.inflight == {} and gw.core.queued_count == 0
    assert gw.ledger.total_reserved == 0
    assert gw._waiters == {}
    if gw.core.rate_limiter is not None:
        assert gw.core.rate_limiter.reserved == {}


# ------------------------------------------------------------------ auth


def test_hashed_registry_never_stores_plaintext(monkeypatch):
    monkeypatch.setenv("QS_KEY_X", "secret-x")
    reg = TenantRegistry.model_validate({"tenants": [
        {"tenant_id": "x", "experiment_id": "e", "run_id": "r", "key_env": "QS_KEY_X"}]})
    assert reg.resolve("Bearer secret-x").tenant_id == "x"
    assert reg.resolve("Bearer nope") is None and reg.resolve(None) is None and reg.resolve("Bearer ") is None
    assert "secret-x" not in reg.model_dump_json()


def test_registry_fails_closed(monkeypatch):
    monkeypatch.delenv("QS_KEY_MISSING", raising=False)
    with pytest.raises(ValueError):
        TenantRegistry.model_validate({"tenants": [
            {"tenant_id": "x", "experiment_id": "e", "run_id": "r", "key_env": "QS_KEY_MISSING"}]})
    with pytest.raises(ValueError):
        TenantRegistry.model_validate({"tenants": [
            {"tenant_id": "x", "experiment_id": "e", "run_id": "r", "key_sha256": _d("k")},
            {"tenant_id": "y", "experiment_id": "e", "run_id": "r", "key_sha256": _d("k")}]})
    with pytest.raises(ValueError):
        TenantRegistry.model_validate({})


async def test_auth_and_attribution(backend_url):
    async with _gw(backend_url) as (c, gw, _):
        assert (await c.post("/v1/chat/completions", json=_chat())).status_code == 401
        for who, tenant in (("a", "victim_a"), ("c", "competitor"), ("a", "victim_a")):
            r = await c.post("/v1/chat/completions", json=_chat(), headers=H[who])
            assert r.status_code == 200 and r.headers["x-quotashift-tenant"] == tenant
            assert r.headers["x-quotashift-admission"] == "admitted"
        assert gw.accountant.counters["victim_a"].requests_completed == 2
        assert "victim_b" not in gw.accountant.counters
        _clean(gw)


# ------------------------------------------------------------------ RPM / TPM + reconciliation


async def test_tenant_rpm_429_retry_after_and_isolation(backend_url):
    rl = RateLimits(per_tenant={"victim_a": {"rpm": 2}})
    async with _gw(backend_url, rate_limits=rl) as (c, gw, _):
        codes = [(await c.post("/v1/chat/completions", json=_chat(), headers=H["a"])).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        r = await c.post("/v1/chat/completions", json=_chat(), headers=H["a"])
        assert r.json()["error"]["reason"] == "tenant_rpm" and int(r.headers["retry-after"]) >= 1
        assert (await c.post("/v1/chat/completions", json=_chat(), headers=H["b"])).status_code == 200
        # rate-limited requests consumed no hard-cap budget
        assert gw.accountant.counters["victim_a"].requests_admitted == 2
        _clean(gw)


async def test_global_tpm_and_reconciliation_to_actual_usage(backend_url):
    rl = RateLimits(global_tpm=300)
    async with _gw(backend_url, rate_limits=rl) as (c, gw, _):
        # reserve 8 + 200 = 208; actual = prompt (mock counts "user:" + 8 words) + 200 generated
        r = await c.post("/v1/chat/completions", json=_chat(words=8, max_tokens=200), headers=H["a"])
        assert r.status_code == 200
        u = r.json()["usage"]
        win = gw.core.rate_limiter.glob
        assert win.usage(gw.now())[1] == u["prompt_tokens"] + u["completion_tokens"]
        r2 = await c.post("/v1/chat/completions", json=_chat(words=8, max_tokens=200), headers=H["b"])
        assert r2.status_code == 429 and r2.json()["error"]["reason"] == "global_tpm"
        _clean(gw)


async def test_requested_vs_reserved_vs_actual_tokens(backend_url):
    async with _gw(backend_url) as (c, gw, _):
        body = _chat(max_tokens=50)
        body["ignore_eos"] = False  # realized output decided by the (mock) engine
        r = await c.post("/v1/chat/completions", json=body, headers=H["a"])
        assert r.headers["x-quotashift-requested-max-tokens"] == "50"
        assert int(r.headers["x-quotashift-reserved-tokens"]) == 50 + int(r.headers["x-quotashift-input-tokens-estimate"])
        actual = r.json()["usage"]["completion_tokens"]
        assert gw.accountant.counters["victim_a"].output_tokens == actual  # charged = actual, never max_tokens
        _clean(gw)


# ------------------------------------------------------------------ slots, queue timeout, cancellation


async def test_concurrent_slot_acquire_release(backend_url):
    async with _gw(backend_url, _caps(max_global_inflight=3)) as (c, gw, _):
        rs = await asyncio.gather(*(c.post("/v1/chat/completions", json=_chat(max_tokens=20),
                                           headers=H["abc"[i % 3]]) for i in range(24)))
        assert all(r.status_code == 200 for r in rs), [r.text for r in rs if r.status_code != 200]
        assert gw.max_inflight_observed == 3  # cap reached, never exceeded
        _clean(gw)


async def test_queue_timeout_503_rolls_back_all_budgets(backend_url):
    rl = RateLimits(default_tenant={"rpm": 100})
    async with _gw(backend_url, _caps(max_global_inflight=1), rate_limits=rl, queue_timeout_s=0.05) as (c, gw, _):
        first = asyncio.create_task(c.post("/v1/chat/completions", json=_chat(max_tokens=200), headers=H["a"]))
        await asyncio.sleep(0.05)
        r = await c.post("/v1/chat/completions", json=_chat(max_tokens=4), headers=H["b"])
        assert r.status_code == 503 and r.json()["error"]["type"] == "queue_timeout"
        assert gw.core.rate_limiter.tenants["victim_b"].usage(gw.now()) == (0, 0)  # refunded
        assert gw.accountant.counters["victim_b"].requests_admitted == 0
        assert (await first).status_code == 200
        _clean(gw)


async def test_queue_capacity(backend_url):
    async with _gw(backend_url, _caps(max_global_inflight=1), max_queue_per_tenant=1) as (c, gw, _):
        t1 = asyncio.create_task(c.post("/v1/chat/completions", json=_chat(max_tokens=150), headers=H["a"]))
        await asyncio.sleep(0.03)
        t2 = asyncio.create_task(c.post("/v1/chat/completions", json=_chat(max_tokens=2), headers=H["a"]))
        await asyncio.sleep(0.03)
        r = await c.post("/v1/chat/completions", json=_chat(max_tokens=2), headers=H["a"])
        assert r.status_code == 429 and r.json()["error"]["reason"] == "tenant_queue_full"
        assert (await t1).status_code == 200 and (await t2).status_code == 200
        _clean(gw)


async def test_cancel_while_queued_releases_everything(backend_url):
    async with _gw(backend_url, _caps(max_global_inflight=1)) as (c, gw, _):
        t1 = asyncio.create_task(c.post("/v1/chat/completions", json=_chat(max_tokens=150), headers=H["a"]))
        await asyncio.sleep(0.03)
        t2 = asyncio.create_task(c.post("/v1/chat/completions", json=_chat(max_tokens=2), headers=H["b"]))
        await asyncio.sleep(0.03)
        assert gw.core.queued_count == 1
        t2.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t2
        await asyncio.sleep(0)
        assert gw.core.queued_count == 0 and gw.accountant.counters["victim_b"].requests_admitted == 0
        assert (await t1).status_code == 200
        _clean(gw)


# ------------------------------------------------------------------ streaming + disconnect cleanup


async def test_stream_passthrough_usage_stripped_unless_requested(backend_url):
    async with _gw(backend_url) as (c, gw, _):
        r = await c.post("/v1/chat/completions", json=_chat(max_tokens=5, stream=True), headers=H["a"])
        events = [e for e in r.text.split("\n\n") if e.startswith("data:")]
        assert events[-1] == "data: [DONE]"
        payloads = [json.loads(e[5:]) for e in events[:-1]]
        assert not any(p.get("usage") for p in payloads)
        assert gw.accountant.counters["victim_a"].output_tokens == 5  # reconciled from upstream usage
        r2 = await c.post("/v1/chat/completions",
                          json=_chat(max_tokens=3, stream=True, stream_options={"include_usage": True}),
                          headers=H["b"])
        p2 = [json.loads(e[5:]) for e in r2.text.split("\n\n") if e.startswith("data:") and e != "data: [DONE]"]
        assert p2[-1]["usage"]["completion_tokens"] == 3
        _clean(gw)


async def _asgi_call(app, body: dict, headers: dict, fail_after_sends: int) -> int:
    """Drive the ASGI app directly with a client that disconnects after N sends."""
    sent = {"n": 0}
    raw = json.dumps(body).encode()
    hdrs = [(k.encode(), v.encode()) for k, v in headers.items()] + [(b"content-type", b"application/json")]
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
             "path": "/v1/chat/completions", "raw_path": b"/v1/chat/completions", "query_string": b"",
             "headers": hdrs, "scheme": "http", "server": ("gw", 80), "client": ("t", 1), "root_path": ""}
    got_body = {"done": False}

    async def receive():
        if not got_body["done"]:
            got_body["done"] = True
            return {"type": "http.request", "body": raw, "more_body": False}
        await asyncio.sleep(3600)
        return {"type": "http.disconnect"}

    async def send(msg):
        if sent["n"] >= fail_after_sends:
            raise OSError("client went away")
        sent["n"] += 1

    with contextlib.suppress(OSError, RuntimeError):
        await app(scope, receive, send)
    return sent["n"]


@pytest.mark.parametrize("fail_after", [0, 1, 2])  # before headers / after headers / mid-body
async def test_stream_disconnect_cleanup(backend_url, fail_after):
    rl = RateLimits(global_tpm=100000)
    async with _gw(backend_url, rate_limits=rl) as (c, gw, app):
        await _asgi_call(app, _chat(max_tokens=40, stream=True), H["a"], fail_after)
        await asyncio.sleep(0.05)
        assert gw.core.inflight == {} and gw.ledger.total_reserved == 0 and gw._waiters == {}
        assert gw.core.rate_limiter.reserved == {}
        st = [r["terminal_status"] for r in gw.recorder.rows.values()]
        assert st == ["cancelled"]
        # gateway still serves after the disconnect
        assert (await c.post("/v1/chat/completions", json=_chat(), headers=H["a"])).status_code == 200
        _clean(gw)


# ------------------------------------------------------------------ retries / idempotency


async def test_retry_semantics(backend_url):
    rl = RateLimits(per_tenant={"victim_a": {"rpm": 1}})
    async with _gw(backend_url, rate_limits=rl) as (c, gw, _):
        h1 = H["a"] | {"x-quotashift-request-id": "req-1"}
        assert (await c.post("/v1/chat/completions", json=_chat(), headers=h1)).status_code == 200
        assert (await c.post("/v1/chat/completions", json=_chat(), headers=h1)).status_code == 409  # replay
        h2 = H["a"] | {"x-quotashift-request-id": "req-2"}
        assert (await c.post("/v1/chat/completions", json=_chat(), headers=h2)).status_code == 429  # rate limited
        gw.core.rate_limiter.tenants["victim_a"].window_s = 0.0  # window elapses
        r = await c.post("/v1/chat/completions", json=_chat(), headers=h2)
        assert r.status_code == 200  # a request rejected before the backend may be retried with its id
        assert gw.accountant.counters["victim_a"].requests_completed == 2
        _clean(gw)


# ------------------------------------------------------------------ in-process (live-runner) path


def _req(rid: str, tenant: str, n_in=10, n_out=10) -> Request:
    return Request(request_id=rid, tenant_id=tenant, arrival_time_s=0.0, prompt_text="x", input_token_count=n_in,
                   max_output_tokens=n_out, workload_class="victim", slo_type=SLOType.INTERACTIVE,
                   ttft_deadline_ms=1000.0, seed=0, trace_id="t")


def test_core_rate_limiter_and_queue_caps_shared_path():
    rl = RateLimits(per_tenant={"a": {"tpm": 50}}).build(["a", "b"])
    gw = Gateway(make_policy("fcfs", max_inflight=1), ["a", "b"], RunRecorder("e", "r"), rate_limiter=rl,
                 max_queue_per_tenant=2)
    assert gw.offer(_req("a1", "a"), 0.0, None)  # reserves 20
    assert gw.offer(_req("a2", "a"), 0.0, None)  # 40
    assert not gw.offer(_req("a3", "a"), 0.0, None)  # tenant queue full (2)
    assert gw.reject_reasons["a3"] == "tenant_queue_full"
    sent = gw.dispatch(0.0, None)
    assert [r.request_id for r in sent] == ["a1"]
    gw.on_terminal("a1", 1.0, EventType.COMPLETED, output_tokens=2, prompt_tokens=10)  # actual 12, not 20
    assert rl.tenants["a"].usage(1.0) == (2, 32)
    gw.on_terminal("a2", 1.0, EventType.TIMED_OUT, detail="gateway_queue_timeout")  # never sent -> refund
    assert rl.tenants["a"].usage(1.0) == (1, 12)
    assert not gw.offer(_req("a4", "a", n_in=20, n_out=20), 1.0, None)  # 12 + 40 = 52 > 50
    assert gw.reject_reasons["a4"] == "rate_limited:tenant_tpm"
    assert gw.offer(_req("b1", "b", n_in=20, n_out=20), 1.0, None)  # other tenant unaffected


def test_core_defaults_unchanged_without_limits():
    gw = Gateway(make_policy("fcfs"), ["a"], RunRecorder("e", "r"))
    assert gw.rate_limiter is None and gw.max_queue_per_tenant is None
    for i in range(50):
        assert gw.offer(_req(f"r{i}", "a"), 0.0, None)
    assert len(gw.dispatch(0.0, None)) == 50  # pass-through, as before


# ------------------------------------------------------------------ per-request cached tokens


async def test_gateway_records_zero_hit_cached_tokens(backend_url):
    """Gateway-server path (/v1/chat/completions): a cold request's cached_tokens=0 is recorded as 0 (mock mirrors
    the patched target); a warm repeat records its hits. Same recorder column as the live-runner path."""
    async with _gw(backend_url) as (c, gw, _):
        body = _chat(words=40, max_tokens=2)
        body["messages"][0]["content"] = "zero hit probe " + " ".join(f"w{i}" for i in range(40))
        for stream in (False, True):
            b = body | ({"stream": True} if stream else {})
            assert (await c.post("/v1/chat/completions", json=b, headers=H["a"])).status_code == 200
        vals = [r["cached_tokens_reported"] for r in gw.recorder.rows.values()]
        assert vals[0] == 0 and vals[1] is not None and vals[1] > 0, vals
        _clean(gw)
