"""Internal-only multi-tenant gateway (FastAPI) for QuotaShift.

Routes: GET /healthz, POST /v1/chat/completions, GET /metrics.

The gateway authenticates a synthetic tenant, enforces fixed authorized budgets
(request/token/in-flight caps), attributes usage per tenant, and forwards to one
private, allowlisted vLLM backend. It is deliberately *not* a scheduler or a
defense (plan non-goals): quotas are fixed and identical across a scenario and its
control. It fails closed — missing caps or a non-private backend prevent startup.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from quotashift.gateway.accounting import Accountant, BudgetExceeded, Caps, DuplicateRequest
from quotashift.gateway.forwarder import Forwarder
from quotashift.gateway.identity import Identity, TenantRegistry
from quotashift.gateway.ledger import TokenLedger

REQUEST_ID_HEADER = "x-quotashift-request-id"


def _estimate_input_tokens(body: dict) -> int:
    """Whitespace-word estimate over chat messages (matches the mock engine)."""
    n = 0
    for m in body.get("messages") or []:
        c = m.get("content", "")
        if isinstance(c, list):
            c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
        n += len(str(c).split())
    return max(1, n)


class GatewayApp:
    def __init__(self, registry: TenantRegistry, caps: Caps, backend_url: str, model: str,
                 run_deadline_s: float | None = None, default_max_output: int = 128) -> None:
        self.registry = registry
        self.caps = caps
        self.default_max_output = default_max_output
        self.forwarder = Forwarder(backend_url, model, request_timeout_s=120.0)
        # Fixed per-tenant token quota = global in-flight budget, applied equally and
        # without borrowing (isolation). Every known tenant gets a ledger entry.
        per_req = caps.max_input_tokens_per_request + caps.max_output_tokens_per_request
        quota = caps.max_global_inflight * per_req
        self.ledger = TokenLedger({t: quota for t in registry.tenants}, allow_borrow=False)
        self.accountant = Accountant(caps=caps, ledger=self.ledger)
        self.inflight = asyncio.Semaphore(caps.max_global_inflight)
        self.run_deadline_s = run_deadline_s
        self._t0 = time.monotonic()
        self._lock = asyncio.Lock()

    def _deadline_hit(self) -> bool:
        return self.run_deadline_s is not None and (time.monotonic() - self._t0) > self.run_deadline_s

    async def chat(self, request: Request, authorization: str | None, x_request_id: str | None) -> Response:
        ident: Identity | None = self.registry.resolve(authorization)
        if ident is None:
            return JSONResponse({"error": {"type": "unauthorized", "reason": "unknown or missing tenant key"}}, status_code=401)
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse({"error": {"type": "invalid_request", "reason": "body is not valid JSON"}}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"error": {"type": "invalid_request", "reason": "body must be a JSON object"}}, status_code=400)

        request_id = (x_request_id or "").strip() or f"{ident.tenant_id}-{uuid.uuid4().hex[:16]}"
        input_tokens = _estimate_input_tokens(body)
        raw_out = body.get("max_completion_tokens", body.get("max_tokens", self.default_max_output))
        max_output = int(raw_out if raw_out is not None else self.default_max_output)

        if self._deadline_hit():
            self.accountant._abort("run_deadline")  # noqa: SLF001 - same module intent
            return JSONResponse({"error": {"type": "budget_exhausted", "reason": "run_deadline"}}, status_code=429)

        async with self._lock:
            try:
                self.accountant.admit(ident.tenant_id, request_id, input_tokens, max_output)
            except DuplicateRequest:
                return JSONResponse({"error": {"type": "duplicate_request", "reason": request_id}}, status_code=409)
            except BudgetExceeded as e:
                self.accountant._c(ident.tenant_id).requests_rejected += 1  # noqa: SLF001
                return JSONResponse(e.as_error(), status_code=429)

        ok = False
        out_tokens = 0
        in_tokens = input_tokens
        status = 502
        payload: dict = {"error": {"type": "backend_error", "reason": "unknown"}}
        try:
            async with self.inflight:
                resp = await self.forwarder.chat(body)
            status = resp.status_code
            if status == 200:
                payload = resp.json()
                usage = payload.get("usage") or {}
                out_tokens = int(usage.get("completion_tokens") or 0)
                in_tokens = int(usage.get("prompt_tokens") or input_tokens)
                ok = True
            else:
                payload = {"error": {"type": "backend_error", "reason": f"http_{status}"}}
        except Exception as e:  # noqa: BLE001 - forwarder raises ForwardError; stay fail-closed
            status = getattr(e, "status", 502)
            payload = getattr(e, "payload", {"error": {"type": "backend_error", "reason": type(e).__name__}})
        finally:
            async with self._lock:
                self.accountant.record(ident.tenant_id, request_id, in_tokens, out_tokens, ok)

        headers = {"x-quotashift-tenant": ident.tenant_id, "x-quotashift-request-id": request_id,
                   "x-quotashift-experiment": ident.experiment_id, "x-quotashift-run": ident.run_id}
        return JSONResponse(payload, status_code=status, headers=headers)

    def metrics_text(self) -> str:
        lines = ["# QuotaShift gateway metrics (synthetic tenants; internal testbed)",
                 f"quotashift_gateway_aborted {int(self.accountant.aborted)}",
                 f"quotashift_gateway_total_admitted {self.accountant.total_admitted}"]
        for t, c in sorted(self.accountant.counters.items()):
            lbl = f'{{tenant="{t}"}}'
            lines += [
                f"quotashift_requests_admitted{lbl} {c.requests_admitted}",
                f"quotashift_requests_completed{lbl} {c.requests_completed}",
                f"quotashift_requests_rejected{lbl} {c.requests_rejected}",
                f"quotashift_input_tokens_total{lbl} {c.input_tokens}",
                f"quotashift_output_tokens_total{lbl} {c.output_tokens}",
            ]
        return "\n".join(lines) + "\n"


def build_app(gw: GatewayApp) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await gw.forwarder.aclose()

    app = FastAPI(title="quotashift-gateway", docs_url=None, redoc_url=None, lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok", "backend_ok": await gw.forwarder.healthz(),
                             "aborted": gw.accountant.aborted})

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
    """Build the app from env vars (container entrypoint). Fails closed on bad config."""
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
    gw = GatewayApp(registry, caps, backend_url=backend_url, model=model,
                    run_deadline_s=float(deadline) if deadline else None)
    return build_app(gw)
