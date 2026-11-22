"""Tokenizer-based prompt sizing and fail-closed context checks (protocol v3.1, ADR-Q17).

Why: historical traces plan `input_token_count` in whitespace words of pseudo-syllable filler; on Qwen2.5 each such
word is ~2.1 tokens, so the A9 long-context family (planned 1,136-3,584 words) exceeded the 3,840-token input limit
and 112/116 competitor requests got HTTP 400 (reports/v3/SUITE_S_FORENSIC_AUDIT.md).

Two operations, both on the exact traces that will be sent (after nonce / prefix structure):

- `calibrate_trace` (only for `prompt_token_unit: tokenizer` scenarios): edits each request's filler so the model
  tokenizer counts exactly `input_token_count` prompt tokens. The filler is the verified single-token vocabulary, so
  adding/removing one word changes the count by one; the first 2 words (the `[req <id>]` tag) and the protocol nonce
  (words 3-6) are never touched. `input_token_count` is never changed, so matched budgets stay exactly as planned.
- `verify_trace` (every live run, any unit): tokenizes every request and fails closed if prompt tokens +
  `max_output_tokens` exceed `max_model_len`, or (tokenizer unit) if any count differs from `input_token_count`.

The prompt goes to `/v1/completions` as raw text (no chat template), so the template overhead is zero by
construction; the live check counts everything that is sent, including the tag and the nonce.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from quotashift.schema import TraceItem

CountFn = Callable[[Sequence[str]], list[int]]
PROTECTED_WORDS = 6  # "[req", "<id>]" + 4 nonce words (v2+); never edited by calibration
MAX_CALIBRATION_ROUNDS = 6


class TokenizedContextInvalid(RuntimeError):
    """A planned request does not fit the model context, or its tokenized length disagrees with the plan."""


class WhitespaceTokenizer:
    """Offline/mock stand-in: the mock backend counts whitespace-separated words as tokens."""

    name = "whitespace"
    identity: dict[str, Any] = {"kind": "whitespace", "note": "mock / offline; not a model tokenizer"}

    def __call__(self, texts: Sequence[str]) -> list[int]:
        return [len(t.split()) for t in texts]


class VllmTokenizer:
    """Counts prompt tokens with the live server's own tokenizer (`POST /tokenize`), cached by text hash.

    Same call the completions endpoint makes (`add_special_tokens` default), so the count equals the
    `usage.prompt_tokens` vLLM will report. Any HTTP error raises (fail closed)."""

    name = "vllm_tokenize"

    def __init__(self, base_url: str, model: str, *, workers: int = 16, timeout_s: float = 30.0) -> None:
        import httpx

        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.Client(timeout=timeout_s)
        self._workers = workers
        self._cache: dict[str, int] = {}
        self.calls = 0
        self.identity = {"kind": "vllm /tokenize", "base_url": self.base_url, "model": model}

    def _one(self, text: str) -> int:
        r = self._client.post(f"{self.base_url}/tokenize", json={"model": self.model, "prompt": text})
        r.raise_for_status()
        self.calls += 1
        return int(r.json()["count"])

    def __call__(self, texts: Sequence[str]) -> list[int]:
        keys = [hashlib.sha256(t.encode()).hexdigest() for t in texts]
        todo = {k: t for k, t in zip(keys, texts, strict=True) if k not in self._cache}
        if todo:
            with ThreadPoolExecutor(self._workers) as ex:
                for k, n in zip(todo, ex.map(self._one, todo.values()), strict=True):
                    self._cache[k] = n
        return [self._cache[k] for k in keys]


def _filler_word(key: str, i: int) -> str:
    """Deterministic appended word; keyed on the ORIGINAL prompt text so identical prompts (e.g. A8 retry twins)
    stay byte-identical after calibration."""
    from quotashift.workload.isolation import NONCE_VOCAB

    return NONCE_VOCAB[int(hashlib.sha256(f"calib|{key}|{i}".encode()).hexdigest()[:8], 16) % len(NONCE_VOCAB)]


def calibrate_trace(items: list[TraceItem], count: CountFn) -> tuple[list[TraceItem], dict[str, Any]]:
    """Return items whose prompt text tokenizes to exactly `input_token_count`, plus a calibration report."""
    texts = [it.request.prompt_text for it in items]
    if any(t is None for t in texts):
        raise TokenizedContextInvalid("tokenizer calibration needs synthetic_text prompts")
    words = [t.split(" ") for t in texts]  # type: ignore[union-attr]
    keys = [hashlib.sha256(t.encode()).hexdigest()[:16] for t in texts]  # type: ignore[union-attr]
    target = [it.request.input_token_count for it in items]
    before = count([" ".join(w) for w in words])
    cur = list(before)
    extra = [0] * len(items)
    for _ in range(MAX_CALIBRATION_ROUNDS):
        off = [i for i in range(len(items)) if cur[i] != target[i]]
        if not off:
            break
        for i in off:
            d = target[i] - cur[i]
            rid = items[i].request.request_id
            if d > 0:
                for _k in range(d):
                    words[i].append(_filler_word(keys[i], extra[i]))
                    extra[i] += 1
            else:
                removable = len(words[i]) - PROTECTED_WORDS
                if removable < -d:
                    raise TokenizedContextInvalid(
                        f"{rid}: cannot shrink to {target[i]} tokens (tag + nonce alone exceed it)")
                del words[i][len(words[i]) + d:]
        new = count([" ".join(words[i]) for i in off])
        for i, n in zip(off, new, strict=True):
            cur[i] = n
    bad = [(items[i].request.request_id, target[i], cur[i]) for i in range(len(items)) if cur[i] != target[i]]
    if bad:
        raise TokenizedContextInvalid(f"{len(bad)} request(s) did not calibrate to their planned token count, "
                                      f"first: {bad[0]}")
    out = [TraceItem(request=it.request.model_copy(update={"prompt_text": " ".join(w)}), oracle=it.oracle)
           for it, w in zip(items, words, strict=True)]
    delta = [b - t for b, t in zip(before, target, strict=True)]
    return out, {"requests": len(items), "pre_calibration_minus_planned_min": min(delta, default=0),
                 "pre_calibration_minus_planned_max": max(delta, default=0),
                 "edited": sum(1 for d in delta if d != 0)}


def verify_trace(items: list[TraceItem], count: CountFn, *, max_model_len: int, exact: bool,
                 label: str = "") -> dict[str, Any]:
    """Tokenize every request; fail closed on context overflow or (exact) planned != tokenized."""
    texts = [it.request.prompt_text or "" for it in items]
    n = count(texts)
    over, mismatch = [], []
    max_ctx = 0
    by_class: dict[str, dict[str, int]] = {}
    for it, k in zip(items, n, strict=True):
        r = it.request
        ctx = k + r.max_output_tokens
        max_ctx = max(max_ctx, ctx)
        c = by_class.setdefault(r.workload_class, {"requests": 0, "planned_input": 0, "tokenized_input": 0,
                                                    "max_output": 0, "max_context": 0})
        c["requests"] += 1
        c["planned_input"] += r.input_token_count
        c["tokenized_input"] += k
        c["max_output"] += r.max_output_tokens
        c["max_context"] = max(c["max_context"], ctx)
        if ctx > max_model_len:
            over.append((r.request_id, k, r.max_output_tokens))
        if exact and k != r.input_token_count:
            mismatch.append((r.request_id, r.input_token_count, k))
    rep = {"label": label, "requests": len(items), "max_model_len": max_model_len, "max_context_tokens": max_ctx,
           "over_context": len(over), "planned_vs_tokenized_mismatch": len(mismatch), "exact_required": exact,
           "by_class": by_class, "ok": not over and not mismatch}
    if over:
        raise TokenizedContextInvalid(f"{label}: {len(over)} request(s) exceed max_model_len={max_model_len} "
                                      f"(prompt tokens + max_output), first: {over[0]}")
    if mismatch:
        raise TokenizedContextInvalid(f"{label}: {len(mismatch)} request(s) tokenize to a different length than "
                                      f"planned, first (id, planned, tokenized): {mismatch[0]}")
    return rep
