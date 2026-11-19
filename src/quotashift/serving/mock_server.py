"""Mock vLLM OpenAI-compatible HTTP server (zero GPU cost).

Runs `EngineModel` in (scaled) real time. Exposes /v1/completions (streaming
and non-streaming), /v1/models, /version, /health, /tokenize and a
Prometheus-format /metrics using vLLM V1-style metric names. Every response
and metric page identifies itself as a MOCK.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import time
import uuid
import zlib

from starlette.applications import Starlette
from starlette.requests import Request as HTTPRequest
from starlette.responses import JSONResponse, PlainTextResponse, StreamingResponse
from starlette.routing import Route

from quotashift.serving.engine_model import EngineModel, EngineParams
from quotashift.serving.openai_backend import MOCK_ORACLE_HEADER

TTFT_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 40.0, 80.0)


class MockVLLM:
    def __init__(self, params: EngineParams, time_scale: float = 1.0, default_output_median: int = 128,
                 model_name: str = "mock-model") -> None:
        self.engine = EngineModel(params)
        self.time_scale = time_scale
        self.default_output_median = default_output_median
        self.model_name = model_name
        self.queues: dict[str, asyncio.Queue] = {}
        self.t_add: dict[str, float] = {}
        self.ttft_counts = [0] * (len(TTFT_BUCKETS) + 1)
        self.ttft_sum = 0.0
        self.wake = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            if not self.engine.has_work():
                self.wake.clear()
                await self.wake.wait()
                continue
            dt, evs = self.engine.step()
            await asyncio.sleep(dt * self.time_scale)
            for e in evs:
                if e.kind == "first_token" and e.rid in self.t_add:
                    self._observe_ttft(time.monotonic() - self.t_add[e.rid])
                q = self.queues.get(e.rid)
                if q is not None:
                    q.put_nowait(e)

    def _observe_ttft(self, v: float) -> None:
        self.ttft_sum += v
        for i, le in enumerate(TTFT_BUCKETS):
            if v <= le:
                self.ttft_counts[i] += 1
                return
        self.ttft_counts[-1] += 1

    def target_len(self, prompt_key: str, max_tokens: int, ignore_eos: bool, oracle: str | None) -> int:
        if ignore_eos:
            return max_tokens
        if oracle is not None:
            return max(1, min(int(oracle), max_tokens))
        # deterministic pseudo-length from prompt hash (lognormal, sigma=0.8)
        h = zlib.crc32(prompt_key.encode()) / 2**32
        z = math.sqrt(2) * _erfinv(2 * min(max(h, 1e-6), 1 - 1e-6) - 1)
        return max(1, min(max_tokens, int(round(self.default_output_median * math.exp(0.8 * z)))))

    def metrics_text(self) -> str:
        o = self.engine.observe()
        lines = [
            "# MOCK vLLM metrics (quotashift.serving.mock_server) - NOT a GPU measurement",
            f'vllm:num_requests_running{{model_name="{self.model_name}"}} {o["num_requests_running"]}',
            f'vllm:num_requests_waiting{{model_name="{self.model_name}"}} {o["num_requests_waiting"]}',
            f'vllm:kv_cache_usage_perc{{model_name="{self.model_name}"}} {o["kv_cache_usage_perc"]}',
            f'vllm:num_preemptions_total{{model_name="{self.model_name}"}} {o["num_preemptions_total"]}',
            f'vllm:prompt_tokens_total{{model_name="{self.model_name}"}} {o["prompt_tokens_total"]}',
            f'vllm:generation_tokens_total{{model_name="{self.model_name}"}} {o["generation_tokens_total"]}',
        ]
        cum = 0
        for le, c in zip(TTFT_BUCKETS, self.ttft_counts, strict=False):
            cum += c
            lines.append(f'vllm:time_to_first_token_seconds_bucket{{le="{le}",model_name="{self.model_name}"}} {cum}')
        cum += self.ttft_counts[-1]
        lines.append(f'vllm:time_to_first_token_seconds_bucket{{le="+Inf",model_name="{self.model_name}"}} {cum}')
        lines.append(f'vllm:time_to_first_token_seconds_sum{{model_name="{self.model_name}"}} {self.ttft_sum}')
        lines.append(f'vllm:time_to_first_token_seconds_count{{model_name="{self.model_name}"}} {cum}')
        return "\n".join(lines) + "\n"


def _erfinv(y: float) -> float:
    # Winitzki approximation (sufficient for a mock length sampler)
    a = 0.147
    ln = math.log(1 - y * y)
    t = 2 / (math.pi * a) + ln / 2
    return math.copysign(math.sqrt(math.sqrt(t * t - ln / a) - t), y)


def _messages_prompt(messages: list) -> tuple[int, str]:
    """Flatten chat messages to a word-count prompt for the mock engine."""
    parts: list[str] = []
    for m in messages:
        c = m.get("content", "")
        if isinstance(c, list):  # content parts (text/image) -> keep text only
            c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
        parts.append(f"{m.get('role', 'user')}: {c}")
    text = "\n".join(parts)
    return len(text.split()), text


def build_app(mock: MockVLLM) -> Starlette:
    async def _serve(request: HTTPRequest, n_prompt: int, key: str, body: dict, *, chat: bool):
        max_tokens = int(body.get("max_completion_tokens", body.get("max_tokens", 16)))
        target = mock.target_len(key, max_tokens, bool(body.get("ignore_eos")), request.headers.get(MOCK_ORACLE_HEADER))
        rid = f"cmpl-{uuid.uuid4().hex[:16]}"
        q: asyncio.Queue = asyncio.Queue()
        mock.queues[rid] = q
        ev = mock.engine.add_request(rid, n_prompt, max_tokens, target)
        if ev is not None:
            mock.queues.pop(rid, None)
            return JSONResponse({"error": {"message": f"MOCK: {ev.detail}", "type": "BadRequestError"}}, status_code=400)
        mock.t_add[rid] = time.monotonic()
        mock.wake.set()
        include_usage = bool((body.get("stream_options") or {}).get("include_usage"))
        obj = "chat.completion.chunk" if chat else "text_completion"

        def cleanup() -> None:
            mock.queues.pop(rid, None)
            mock.t_add.pop(rid, None)

        def _delta(text: str, finish: str | None) -> dict:
            content: object = {"content": text} if chat else text
            choice = {"index": 0, "finish_reason": finish, ("delta" if chat else "text"): content}
            return {"id": rid, "object": obj, "model": mock.model_name, "choices": [choice]}

        async def gen():
            finished = False
            try:
                while True:
                    e = await q.get()
                    if e.kind in ("first_token", "token"):
                        yield "data: " + json.dumps(_delta(" tok", None)) + "\n\n"
                    elif e.kind == "finished":
                        reason = "length" if e.generated >= max_tokens else "stop"
                        yield "data: " + json.dumps(_delta("", reason)) + "\n\n"
                        if include_usage:
                            yield "data: " + json.dumps({"id": rid, "object": obj, "choices": [],
                                                         "usage": {"prompt_tokens": n_prompt, "completion_tokens": e.generated,
                                                                   "total_tokens": n_prompt + e.generated}}) + "\n\n"
                        finished = True
                        yield "data: [DONE]\n\n"
                        return
            finally:
                if not finished:
                    mock.engine.abort(rid)  # client disconnect / early exit
                cleanup()

        if body.get("stream"):
            return StreamingResponse(gen(), media_type="text/event-stream")
        n = 0
        async for chunk in gen():
            if '" tok"' in chunk:
                n += 1
        full = " tok" * n
        if chat:
            msg = {"role": "assistant", "content": full}
            return JSONResponse({"id": rid, "object": "chat.completion", "model": mock.model_name,
                                 "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
                                 "usage": {"prompt_tokens": n_prompt, "completion_tokens": n, "total_tokens": n_prompt + n}})
        return JSONResponse({"id": rid, "object": "text_completion", "model": mock.model_name,
                             "choices": [{"index": 0, "text": full, "finish_reason": "stop"}],
                             "usage": {"prompt_tokens": n_prompt, "completion_tokens": n, "total_tokens": n_prompt + n}})

    async def completions(request: HTTPRequest):
        body = await request.json()
        prompt = body.get("prompt")
        if isinstance(prompt, list):
            n_prompt, key = len(prompt), ",".join(map(str, prompt[:64])) + f"#{len(prompt)}"
        elif isinstance(prompt, str):
            n_prompt, key = len(prompt.split()), prompt
        else:
            return JSONResponse({"error": {"message": "prompt must be str or list[int]"}}, status_code=400)
        return await _serve(request, n_prompt, key, body, chat=False)

    async def chat_completions(request: HTTPRequest):
        body = await request.json()
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            return JSONResponse({"error": {"message": "messages must be a non-empty list"}}, status_code=400)
        n_prompt, key = _messages_prompt(messages)
        return await _serve(request, max(1, n_prompt), key, body, chat=True)

    async def metrics(_: HTTPRequest):
        return PlainTextResponse(mock.metrics_text())

    async def health(_: HTTPRequest):
        return PlainTextResponse("")

    async def models(_: HTTPRequest):
        return JSONResponse({"object": "list", "data": [{"id": mock.model_name, "object": "model", "owned_by": "quotashift-mock",
                                                          "max_model_len": mock.engine.params.max_model_len}]})

    async def version(_: HTTPRequest):
        return JSONResponse({"version": "quotashift-mock-0.1", "mock": True, "engine_params": mock.engine.params.model_dump()})

    async def tokenize(request: HTTPRequest):
        body = await request.json()
        toks = [zlib.crc32(w.encode()) % 50000 for w in str(body.get("prompt", "")).split()]
        return JSONResponse({"count": len(toks), "max_model_len": mock.engine.params.max_model_len, "tokens": toks})

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        await mock.start()
        try:
            yield
        finally:
            await mock.stop()

    return Starlette(
        routes=[
            Route("/v1/completions", completions, methods=["POST"]),
            Route("/v1/chat/completions", chat_completions, methods=["POST"]),
            Route("/metrics", metrics),
            Route("/health", health),
            Route("/v1/models", models),
            Route("/version", version),
            Route("/tokenize", tokenize, methods=["POST"]),
        ],
        lifespan=lifespan,
    )
