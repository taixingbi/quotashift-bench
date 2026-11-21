"""Admission-time input-token estimation for the HTTP gateway.

- `whitespace` (default; historical behaviour): whitespace words over chat message text.
- `vllm`: exact count from the backend's own tokenizer via vLLM `/tokenize` (chat template
  applied). Falls back to `whitespace` if the call fails; the source used is recorded per
  request (`input_tokens_source`) so estimates are never silently mixed with exact counts.

The estimate only sizes the reservation; reservations are reconciled to the backend's
reported `usage.prompt_tokens` when the request completes.
"""

from __future__ import annotations

from typing import Literal

Estimator = Literal["whitespace", "vllm"]


def whitespace_tokens(body: dict) -> int:
    n = 0
    for m in body.get("messages") or []:
        c = m.get("content", "") if isinstance(m, dict) else ""
        if isinstance(c, list):
            c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
        n += len(str(c).split())
    return max(1, n)


async def estimate_input_tokens(body: dict, mode: Estimator, forwarder) -> tuple[int, str]:  # noqa: ANN001
    if mode == "vllm":
        n = await forwarder.tokenize_chat(body.get("messages") or [])
        if n is not None and n > 0:
            return n, "vllm_tokenize"
        return whitespace_tokens(body), "whitespace_fallback"
    return whitespace_tokens(body), "whitespace"
