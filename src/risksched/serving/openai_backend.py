"""Streaming adapter for OpenAI-compatible completion servers (vLLM, mock).

Realized output tokens are taken from the final `usage` chunk
(`stream_options.include_usage`). If usage is absent we fall back to the
number of non-empty content chunks and mark `output_tokens_source="chunks"`
(a chunk may contain >1 token, so this is a lower bound).
"""

from __future__ import annotations

import json
import time
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from risksched.instrumentation.prom import MetricSnapshot, parse_prometheus_text, resolve
from risksched.schema import Request

MOCK_ORACLE_HEADER = "x-mock-oracle-output-tokens"


@dataclass
class StreamResult:
    ok: bool
    output_tokens: int | None = None
    output_tokens_source: str | None = None
    prompt_tokens: int | None = None
    n_chunks: int = 0
    max_itl_s: float | None = None
    finish_reason: str | None = None
    error: str | None = None
    http_status: int | None = None


@dataclass
class OpenAICompatBackend:
    base_url: str
    model: str
    sampling: dict[str, Any] = field(default_factory=lambda: {"temperature": 0.0})
    ignore_eos: bool = False
    # Simulation-only side channel so a mock server reproduces trace ground truth.
    # MUST be False for real vLLM (validated in runner config).
    send_mock_oracle_header: bool = False
    connect_timeout_s: float = 10.0
    kind: str = "openai_compat"

    def __post_init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.base_url.rstrip("/"),
            timeout=httpx.Timeout(None, connect=self.connect_timeout_s),
            limits=httpx.Limits(max_connections=1024, max_keepalive_connections=256),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _body(self, req: Request) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "prompt": list(req.prompt_token_ids) if req.prompt_token_ids is not None else req.prompt_text,
            "max_tokens": req.max_output_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
            **self.sampling,
        }
        if "seed" not in body:
            # deterministic per-request sampling seed (independent of PYTHONHASHSEED)
            body["seed"] = (zlib.crc32(req.request_id.encode()) ^ req.seed) & 0x7FFFFFFF
        if self.ignore_eos:
            body["ignore_eos"] = True  # vLLM extension; forces realized == max_tokens
        return body

    async def stream(
        self,
        req: Request,
        on_first_token: Callable[[], None],
        oracle_output_tokens: int | None = None,
    ) -> StreamResult:
        headers = {}
        if self.send_mock_oracle_header and oracle_output_tokens is not None:
            headers[MOCK_ORACLE_HEADER] = str(oracle_output_tokens)
        res = StreamResult(ok=False)
        last_t: float | None = None
        max_itl = 0.0
        content_chunks = 0
        try:
            async with self._client.stream("POST", "/v1/completions", json=self._body(req), headers=headers) as r:
                res.http_status = r.status_code
                if r.status_code != 200:
                    body = (await r.aread()).decode(errors="replace")[:300]
                    res.error = f"http_{r.status_code}:{body}"
                    return res
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if chunk.get("usage"):
                        u = chunk["usage"]
                        res.output_tokens = u.get("completion_tokens")
                        res.prompt_tokens = u.get("prompt_tokens")
                        res.output_tokens_source = "usage"
                    for ch in chunk.get("choices") or []:
                        if ch.get("text"):
                            now = time.monotonic()
                            if last_t is None:
                                on_first_token()
                            else:
                                max_itl = max(max_itl, now - last_t)
                            last_t = now
                            content_chunks += 1
                        if ch.get("finish_reason"):
                            res.finish_reason = ch["finish_reason"]
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            res.error = f"{type(e).__name__}:{e}"[:300]
            res.n_chunks = content_chunks
            return res
        res.n_chunks = content_chunks
        res.max_itl_s = max_itl if content_chunks > 1 else None
        if res.output_tokens is None:
            res.output_tokens = content_chunks
            res.output_tokens_source = "chunks_lower_bound"
        res.ok = True
        return res

    async def scrape_metrics(self) -> MetricSnapshot | None:
        try:
            r = await self._client.get("/metrics", timeout=5.0)
            if r.status_code != 200:
                return None
            return resolve(parse_prometheus_text(r.text))
        except httpx.HTTPError:
            return None

    async def info(self) -> dict[str, Any]:
        out: dict[str, Any] = {"base_url": self.base_url, "model": self.model}
        for path in ("/version", "/v1/models"):
            try:
                r = await self._client.get(path, timeout=5.0)
                out[path] = r.json() if r.status_code == 200 else f"http_{r.status_code}"
            except Exception as e:  # noqa: BLE001 - provenance only
                out[path] = f"unavailable:{type(e).__name__}"
        return out

    async def tokenize(self, text: str) -> list[int] | None:
        try:
            r = await self._client.post("/tokenize", json={"model": self.model, "prompt": text}, timeout=30.0)
            if r.status_code != 200:
                return None
            return list(r.json().get("tokens", []))
        except httpx.HTTPError:
            return None
