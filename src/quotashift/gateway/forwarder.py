"""Backend forwarder: the only egress path out of the gateway.

Enforces the allowlisted private backend (no external URLs, ever) and forwards
only `/v1/chat/completions`. The client request body may not carry a target/URL
override; such fields are rejected. Redirects are disabled so a 3xx cannot bounce
the request to an external host.
"""

from __future__ import annotations

from typing import Any

import httpx

from quotashift.scenario import endpoint_is_private

# Body keys a client is never allowed to set (they could redirect egress).
_FORBIDDEN_BODY_KEYS = frozenset({"url", "base_url", "api_base", "target", "endpoint", "host"})


class ForwardError(Exception):
    def __init__(self, status: int, payload: dict) -> None:
        super().__init__(payload.get("error", {}).get("reason", "forward_error"))
        self.status = status
        self.payload = payload


class Forwarder:
    def __init__(self, backend_url: str, model: str, connect_timeout_s: float = 10.0,
                 request_timeout_s: float = 120.0) -> None:
        ok, reason = endpoint_is_private(backend_url)
        if not ok:
            raise ValueError(f"backend_url rejected (private hosts only): {reason}")
        self.backend_url = backend_url.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(
            base_url=self.backend_url,
            timeout=httpx.Timeout(request_timeout_s, connect=connect_timeout_s),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=256, max_keepalive_connections=64),
        )

    @staticmethod
    def validate_body(body: dict) -> None:
        bad = _FORBIDDEN_BODY_KEYS & set(body)
        if bad:
            raise ForwardError(400, {"error": {"type": "invalid_request", "reason": f"forbidden body keys: {sorted(bad)}"}})

    async def chat(self, body: dict[str, Any]) -> httpx.Response:
        self.validate_body(body)
        payload = dict(body)
        payload["model"] = self.model  # pin the model; ignore any client value
        payload["stream"] = False  # Phase 1 records usage from the final body
        try:
            return await self._client.post("/v1/chat/completions", json=payload)
        except httpx.HTTPError as e:
            raise ForwardError(502, {"error": {"type": "backend_unreachable", "reason": f"{type(e).__name__}"}}) from e

    async def healthz(self) -> bool:
        try:
            r = await self._client.get("/health", timeout=5.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
