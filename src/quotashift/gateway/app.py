"""Internal-only multi-tenant gateway (FastAPI adapter) for QuotaShift.

Routes: GET /healthz, POST /v1/chat/completions (streaming and non-streaming), GET /metrics.

This is an HTTP *adapter* over the same admission/queue engine (`core.Gateway`) used by
the in-process live runner, so both execution paths share identity, hard caps, token
ledger, RPM/TPM windows, queueing, timeout and cleanup logic. It is deliberately *not* a
scheduler or a defense: quotas/limits are fixed and identical across a scenario and its
control. It fails closed — missing caps or a non-private backend prevent startup.

Request path:
  auth -> body checks -> input-token estimate -> hard caps + ledger reservation (Accountant)
  -> core.offer (queue capacity, RPM/TPM reservation, fixed policy) -> wait for dispatch
  (global in-flight cap, optional queue timeout) -> forward -> reconcile/charge actual usage.

Cleanup guarantees: a request that never reaches the backend (rate limited, queue full,
queue timeout, client disconnect while queued) is rolled back from every budget; a request
that reached the backend is settled exactly once, including streaming disconnects before or
during the body (see `_GuardedStream`).

Defaults reproduce the historical (Phase 1) adapter: FCFS in arrival order, no RPM/TPM,
no queue timeout or capacity, whitespace token estimate, reject `max_tokens` over cap.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import os
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from quotashift.gateway.accounting import Accountant, BudgetExceeded, Caps, DuplicateRequest
from quotashift.gateway.core import Gateway
from quotashift.gateway.forwarder import Forwarder, ForwardError
from quotashift.gateway.identity import Identity, TenantRegistry
from quotashift.gateway.ledger import TokenLedger
from quotashift.gateway.quotas import RateLimits
from quotashift.gateway.tokens import Estimator, estimate_input_tokens, whitespace_tokens
from quotashift.instrumentation.recorder import RunRecorder
from quotashift.schedulers.simple import make_policy
from quotashift.schema import EventType, SLOType
from quotashift.schema import Request as QSRequest
from quotashift.serving.openai_backend import cached_tokens_of

REQUEST_ID_HEADER = "x-quotashift-request-id"


def _estimate_input_tokens(body: dict) -> int:
    """Whitespace-word estimate over chat messages (historical default; matches the mock engine)."""
    return whitespace_tokens(body)


def _err(status: int, etype: str, reason: str, headers: dict[str, str] | None = None, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": {"type": etype, "reason": reason, **extra}}, status_code=status, headers=headers)


class _GuardedStream(StreamingResponse):
    """StreamingResponse whose cleanup runs even if the body generator never starts
    (client gone before the first byte) — the gap a generator `finally` cannot cover."""

    def __init__(self, content, cleanup, **kw) -> None:  # noqa: ANN001
        super().__init__(content, **kw)
        self._cleanup = cleanup

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._cleanup()


class GatewayApp:
    def __init__(self, registry: TenantRegistry, caps: Caps, backend_url: str, model: str,
                 run_deadline_s: float | None = None, default_max_output: int = 128, *,
                 policy: Literal["fcfs", "static_quota"] = "fcfs",
                 rate_limits: RateLimits | None = None,
                 queue_timeout_s: float | None = None,
                 max_queue_per_tenant: int | None = None,
                 max_queue_total: int | None = None,
                 token_estimator: Estimator = "whitespace",
                 request_timeout_s: float = 120.0) -> None:
        self.registry = registry
        self.caps = caps
        self.default_max_output = default_max_output
        self.token_estimator: Estimator = token_estimator
        self.queue_timeout_s = queue_timeout_s
        self.forwarder = Forwarder(backend_url, model, request_timeout_s=request_timeout_s)
        tenants = registry.tenants
        # Fixed per-tenant token quota = global in-flight budget, applied equally and
        # without borrowing (isolation). Every known tenant gets a ledger entry.
        per_req = caps.max_input_tokens_per_request + caps.max_output_tokens_per_request
        quota = caps.max_global_inflight * per_req
        self.ledger = TokenLedger({t: quota for t in tenants}, allow_borrow=False)
        self.accountant = Accountant(caps=caps, ledger=self.ledger)
        self._t0 = time.monotonic()
        self.recorder = RunRecorder("gateway_http", uuid.uuid4().hex[:12], clock="monotonic", strict=True)
        params: dict[str, Any] = {"max_inflight": caps.max_global_inflight} if policy == "fcfs" else {}
        self.core = Gateway(
            make_policy(policy, **params), tenants, self.recorder, ledger=None,
            max_queue_wait_s=None,  # queue timeout is enforced per waiter below
            rate_limiter=rate_limits.build(tenants) if rate_limits else None,
            max_queue_per_tenant=max_queue_per_tenant, max_queue_total=max_queue_total)
        self.policy_name = policy
        self.run_deadline_s = run_deadline_s
        self._waiters: dict[str, asyncio.Future[None]] = {}
        self._settled: set[str] = set()
        self._attempt = itertools.count()
        self.max_inflight_observed = 0
        self.reject_counts: dict[tuple[str, str], int] = {}

    # ---------------------------------------------------------------- helpers
    def now(self) -> float:
        return time.monotonic() - self._t0

    def _deadline_hit(self) -> bool:
        return self.run_deadline_s is not None and self.now() > self.run_deadline_s

    def _pump(self) -> None:
        for req in self.core.dispatch(self.now(), None):
            fut = self._waiters.get(req.request_id)
            if fut is not None and not fut.done():
                fut.set_result(None)
        self.max_inflight_observed = max(self.max_inflight_observed, len(self.core.inflight))

    def _reject(self, tenant: str, reason: str) -> None:
        self.reject_counts[(tenant, reason)] = self.reject_counts.get((tenant, reason), 0) + 1

    def _headers(self, ident: Identity, client_rid: str, **kw: Any) -> dict[str, str]:
        h = {"x-quotashift-tenant": ident.tenant_id, "x-quotashift-request-id": client_rid,
             "x-quotashift-experiment": ident.experiment_id, "x-quotashift-run": ident.run_id}
        h.update({f"x-quotashift-{k.replace('_', '-')}": str(v) for k, v in kw.items() if v is not None})
        return h

    def _settle(self, tenant: str, client_rid: str, irid: str, kind: EventType, *, ok: bool,
                prompt_tokens: int | None, output_tokens: int | None, est_input: int, detail: str | None) -> None:
        """Terminal accounting for a request that reached the backend. Exactly once."""
        if irid in self._settled:
            return
        self._settled.add(irid)
        self.core.on_terminal(irid, self.now(), kind, output_tokens=output_tokens if ok else None, detail=detail,
                              prompt_tokens=prompt_tokens)
        self.recorder.annotate(irid, prompt_tokens_reported=prompt_tokens)
        in_tok = prompt_tokens if prompt_tokens is not None else est_input
        self.accountant.record(tenant, client_rid, in_tok, output_tokens or 0, ok)
        self._waiters.pop(irid, None)
        self._pump()

    def _abandon(self, tenant: str, client_rid: str, irid: str, kind: EventType, detail: str) -> None:
        """Roll back a request that never reached the backend (queued -> timeout/cancel)."""
        if irid in self._settled:
            return
        self._settled.add(irid)
        self.core.on_terminal(irid, self.now(), kind, detail=detail)  # refunds RPM/TPM
        self.accountant.rollback(tenant, client_rid)
        self._waiters.pop(irid, None)
        self._reject(tenant, detail)
        self._pump()

    # ---------------------------------------------------------------- request path
    async def chat(self, request: Request, authorization: str | None, x_request_id: str | None) -> Response:
        ident: Identity | None = self.registry.resolve(authorization)
        if ident is None:
            return _err(401, "unauthorized", "unknown or missing tenant key")
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return _err(400, "invalid_request", "body is not valid JSON")
        if not isinstance(body, dict):
            return _err(400, "invalid_request", "body must be a JSON object")
        try:
            Forwarder.validate_body(body)
        except ForwardError as e:
            return JSONResponse(e.payload, status_code=e.status)
        tenant = ident.tenant_id
        client_rid = (x_request_id or "").strip()[:128] or f"{tenant}-{uuid.uuid4().hex[:16]}"
        stream = bool(body.get("stream", False))
        raw_out = body.get("max_completion_tokens", body.get("max_tokens", self.default_max_output))
        requested_max = int(raw_out if raw_out is not None else self.default_max_output)
        est_input, est_src = await estimate_input_tokens(body, self.token_estimator, self.forwarder)

        if self._deadline_hit():
            self.accountant._abort("run_deadline")  # noqa: SLF001 - same module intent
            return _err(429, "budget_exhausted", "run_deadline")
        if self.accountant.is_seen(client_rid):
            return _err(409, "duplicate_request", client_rid)
        try:
            self.accountant.admit(tenant, client_rid, est_input, requested_max)
        except DuplicateRequest:
            return _err(409, "duplicate_request", client_rid)
        except BudgetExceeded as e:
            self.accountant._c(tenant).requests_rejected += 1  # noqa: SLF001
            self._reject(tenant, e.reason)
            return JSONResponse(e.as_error(), status_code=429)

        irid = f"{client_rid}~{next(self._attempt)}"
        t = self.now()
        qreq = QSRequest(request_id=irid, tenant_id=tenant, arrival_time_s=t, prompt_text="<http>",
                         input_token_count=est_input, max_output_tokens=max(1, requested_max),
                         workload_class=ident.role, slo_type=SLOType.INTERACTIVE, ttft_deadline_ms=1e9,
                         seed=0, trace_id=f"http-{ident.experiment_id}")
        if not self.core.offer(qreq, t, None):
            reason = self.core.reject_reasons.pop(irid, "policy_reject")
            self.accountant.rollback(tenant, client_rid)
            self._reject(tenant, reason)
            if reason.startswith("rate_limited:"):
                retry = max(1, int(self.core.retry_after_s(tenant, self.now()) + 0.999))
                return _err(429, "rate_limited", reason.split(":", 1)[1],
                            self._headers(ident, client_rid) | {"retry-after": str(retry)})
            status = 503 if reason == "global_queue_full" else 429
            return _err(status, "overloaded", reason, self._headers(ident, client_rid))

        fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._waiters[irid] = fut
        self._pump()
        try:
            done, _ = await asyncio.wait({fut}, timeout=self.queue_timeout_s)
        except asyncio.CancelledError:
            if irid not in self.core.inflight:
                self._abandon(tenant, client_rid, irid, EventType.CANCELLED, "client_disconnect_queued")
            else:
                self._settle(tenant, client_rid, irid, EventType.CANCELLED, ok=False, prompt_tokens=None,
                             output_tokens=None, est_input=est_input, detail="client_disconnect")
            raise
        if not done:
            self._abandon(tenant, client_rid, irid, EventType.TIMED_OUT, "gateway_queue_timeout")
            return _err(503, "queue_timeout", f"waited > {self.queue_timeout_s}s", self._headers(ident, client_rid))
        queue_ms = (self.recorder.rows[irid]["t_sent"] - t) * 1000.0
        hdr = self._headers(ident, client_rid, admission="admitted", queue_ms=f"{queue_ms:.3f}",
                            reserved_tokens=est_input + requested_max, requested_max_tokens=requested_max,
                            input_tokens_estimate=est_input, input_tokens_source=est_src)
        if stream:
            return await self._forward_stream(ident, client_rid, irid, body, est_input, hdr)
        return await self._forward(ident, client_rid, irid, body, est_input, hdr)

    async def _forward(self, ident: Identity, client_rid: str, irid: str, body: dict, est_input: int,
                       hdr: dict[str, str]) -> Response:
        tenant = ident.tenant_id
        ok, out_tokens, in_tokens = False, 0, None
        status, payload = 502, {"error": {"type": "backend_error", "reason": "unknown"}}
        kind, detail = EventType.BACKEND_ERROR, None
        try:
            resp = await self.forwarder.chat(body)
            status = resp.status_code
            if status == 200:
                payload = resp.json()
                usage = payload.get("usage") or {}
                out_tokens = int(usage.get("completion_tokens") or 0)
                in_tokens = usage.get("prompt_tokens")
                self.recorder.annotate(irid, cached_tokens_reported=cached_tokens_of(usage))
                ok, kind = True, EventType.COMPLETED
            else:
                payload = {"error": {"type": "backend_error", "reason": f"http_{status}"}}
                detail = f"http_{status}"
        except ForwardError as e:
            status, payload, detail = e.status, e.payload, "forward_error"
        except asyncio.CancelledError:
            kind, detail = EventType.CANCELLED, "client_disconnect"
            raise
        finally:
            self._settle(tenant, client_rid, irid, kind, ok=ok, prompt_tokens=in_tokens,
                         output_tokens=out_tokens if ok else None, est_input=est_input, detail=detail)
        return JSONResponse(payload, status_code=status, headers=hdr)

    async def _forward_stream(self, ident: Identity, client_rid: str, irid: str, body: dict, est_input: int,
                              hdr: dict[str, str]) -> Response:
        tenant = ident.tenant_id
        client_wants_usage = bool((body.get("stream_options") or {}).get("include_usage"))
        try:
            upstream = await self.forwarder.open_stream(body)
        except asyncio.CancelledError:  # client gone while the upstream stream was opening
            self._settle(tenant, client_rid, irid, EventType.CANCELLED, ok=False, prompt_tokens=None,
                         output_tokens=None, est_input=est_input, detail="client_disconnect")
            raise
        except ForwardError as e:
            self._settle(tenant, client_rid, irid, EventType.BACKEND_ERROR, ok=False, prompt_tokens=None,
                         output_tokens=None, est_input=est_input, detail="forward_error")
            return JSONResponse(e.payload, status_code=e.status, headers=hdr)
        if upstream.status_code != 200:
            detail = (await upstream.aread())[:300].decode(errors="replace")
            await upstream.aclose()
            self._settle(tenant, client_rid, irid, EventType.BACKEND_ERROR, ok=False, prompt_tokens=None,
                         output_tokens=None, est_input=est_input, detail=f"http_{upstream.status_code}")
            return _err(upstream.status_code, "backend_error", f"http_{upstream.status_code}", hdr, detail=detail)
        state: dict[str, Any] = {"prompt": None, "out": None, "chunks": 0, "done": False}

        async def gen() -> AsyncIterator[bytes]:
            event: list[str] = []
            async for line in upstream.aiter_lines():
                if line:
                    event.append(line)
                    continue
                if not event:
                    continue
                data = "\n".join(ln[5:].strip() for ln in event if ln.startswith("data:"))
                emit = True
                if data == "[DONE]":
                    state["done"] = True
                elif data:
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        obj = {}
                    if obj.get("usage"):
                        state["prompt"] = obj["usage"].get("prompt_tokens")
                        self.recorder.annotate(irid, cached_tokens_reported=cached_tokens_of(obj["usage"]))
                        state["out"] = obj["usage"].get("completion_tokens")
                        if not obj.get("choices") and not client_wants_usage:
                            emit = False
                    for ch in obj.get("choices") or []:
                        d = ch.get("delta") or {}
                        if d.get("content") or ch.get("text"):
                            if state["chunks"] == 0:
                                self.core.on_first_token(irid, self.now())
                            state["chunks"] += 1
                if emit:
                    yield ("\n".join(event) + "\n\n").encode()
                event = []

        async def cleanup() -> None:
            with contextlib.suppress(Exception):
                await upstream.aclose()
            ok = bool(state["done"])
            out = state["out"] if state["out"] is not None else (state["chunks"] if ok else None)
            self.recorder.annotate(irid, n_stream_chunks=state["chunks"],
                                   output_tokens_source="usage" if state["out"] is not None else "chunks_lower_bound")
            self._settle(tenant, client_rid, irid, EventType.COMPLETED if ok else EventType.CANCELLED, ok=ok,
                         prompt_tokens=state["prompt"], output_tokens=out, est_input=est_input,
                         detail=None if ok else "client_disconnect_or_stream_error")

        return _GuardedStream(gen(), cleanup, media_type="text/event-stream", headers=hdr)

    # ---------------------------------------------------------------- metrics
    def metrics_text(self) -> str:
        lines = ["# QuotaShift gateway metrics (synthetic tenants; internal testbed). scope=per_tenant",
                 f"quotashift_gateway_aborted {int(self.accountant.aborted)}",
                 f"quotashift_gateway_total_admitted {self.accountant.total_admitted}",
                 f"quotashift_gateway_inflight {len(self.core.inflight)}",
                 f"quotashift_gateway_queued {self.core.queued_count}"]
        for t, c in sorted(self.accountant.counters.items()):
            lbl = f'{{tenant="{t}"}}'
            lines += [
                f"quotashift_requests_admitted{lbl} {c.requests_admitted}",
                f"quotashift_requests_completed{lbl} {c.requests_completed}",
                f"quotashift_requests_rejected{lbl} {c.requests_rejected}",
                f"quotashift_input_tokens_total{lbl} {c.input_tokens}",
                f"quotashift_output_tokens_total{lbl} {c.output_tokens}",
            ]
        for t, n in sorted(self.core.queue_lengths().items()):
            lines.append(f'quotashift_queue_depth{{tenant="{t}"}} {n}')
        for (t, reason), n in sorted(self.reject_counts.items()):
            lines.append(f'quotashift_rejections_total{{tenant="{t}",reason="{reason}"}} {n}')
        return "\n".join(lines) + "\n"


def build_app(gw: GatewayApp) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await gw.forwarder.aclose()

    app = FastAPI(title="quotashift-gateway", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok", "backend_ok": await gw.forwarder.healthz(),
                             "aborted": gw.accountant.aborted, "policy": gw.policy_name})

    @app.post("/v1/chat/completions")
    async def chat(request: Request,
                   authorization: str | None = Header(default=None),
                   x_quotashift_request_id: str | None = Header(default=None)) -> Response:
        return await gw.chat(request, authorization, x_quotashift_request_id)

    @app.get("/metrics")
    async def metrics() -> PlainTextResponse:
        return PlainTextResponse(gw.metrics_text())

    return app


def app_from_env() -> FastAPI:
    """Build the app from env vars (container entrypoint). Fails closed on bad config.

    Optional (default = historical behaviour): QUOTASHIFT_RATE_LIMITS (YAML of
    `quotas.RateLimits`), QUOTASHIFT_QUEUE_TIMEOUT_S, QUOTASHIFT_MAX_QUEUE_PER_TENANT,
    QUOTASHIFT_MAX_QUEUE_TOTAL, QUOTASHIFT_TOKEN_ESTIMATOR (whitespace|vllm),
    QUOTASHIFT_GATEWAY_POLICY (fcfs|static_quota).
    """
    registry = TenantRegistry.from_yaml(Path(os.environ["QUOTASHIFT_TENANTS"]))
    caps = Caps(
        max_total_requests=int(os.environ["QUOTASHIFT_MAX_TOTAL_REQUESTS"]),
        max_requests_per_tenant=int(os.environ["QUOTASHIFT_MAX_REQUESTS_PER_TENANT"]),
        max_input_tokens_per_request=int(os.environ["QUOTASHIFT_MAX_INPUT_TOKENS"]),
        max_output_tokens_per_request=int(os.environ["QUOTASHIFT_MAX_OUTPUT_TOKENS"]),
        max_global_inflight=int(os.environ["QUOTASHIFT_MAX_GLOBAL_INFLIGHT"]),
    )
    deadline = os.environ.get("QUOTASHIFT_RUN_DEADLINE_S")
    backend_url = os.environ.get("QUOTASHIFT_BACKEND_URL")
    model = os.environ.get("QUOTASHIFT_MODEL")
    if not (backend_url and model):
        # Fall back to the active target profile (configs/targets, QUOTASHIFT_TARGET).
        from quotashift.targets import active_target

        prof = active_target()
        backend_url, model = backend_url or prof.backend_url, model or prof.model
    rl_path = os.environ.get("QUOTASHIFT_RATE_LIMITS")
    rate_limits = RateLimits.model_validate(yaml.safe_load(Path(rl_path).read_text())) if rl_path else None

    def _opt(name: str, cast):  # noqa: ANN001, ANN202
        v = os.environ.get(name)
        return cast(v) if v else None

    gw = GatewayApp(registry, caps, backend_url=backend_url, model=model,
                    run_deadline_s=float(deadline) if deadline else None,
                    policy=os.environ.get("QUOTASHIFT_GATEWAY_POLICY", "fcfs"),  # type: ignore[arg-type]
                    rate_limits=rate_limits,
                    queue_timeout_s=_opt("QUOTASHIFT_QUEUE_TIMEOUT_S", float),
                    max_queue_per_tenant=_opt("QUOTASHIFT_MAX_QUEUE_PER_TENANT", int),
                    max_queue_total=_opt("QUOTASHIFT_MAX_QUEUE_TOTAL", int),
                    token_estimator=os.environ.get("QUOTASHIFT_TOKEN_ESTIMATOR", "whitespace"))  # type: ignore[arg-type]
    return build_app(gw)
