"""X2 Amendment A3 (DRAFT): sequential prompt-token counting for Mistral (docs/PROTOCOL_X2_AMENDMENT_A3.md).

Why: on vLLM 0.17.1 in mistral tokenizer mode, concurrent `POST /tokenize` calls sometimes return one extra trailing
`</s>` (EOS, id 2); sequential calls equal the pinned offline tokenizer, and `/v1/completions` prompt usage is exact
under concurrency (reports/x2/g1m1/diagnostic, docs/KNOWN_LIMITATIONS.md). The frozen counter
(`quotashift.workload.tokenize.VllmTokenizer`, pinned by v5) fans out over 16 workers, so the g1m1 calibration-A
freeze refused. The server-side mechanism is a hypothesis, not established.

What A3 changes, and only when activated:
  * `quotashift.workload.tokenize.VllmTokenizer` (the module attribute the frozen callers resolve at call time:
    local.run_matched_pairs pre-send verification, freeze_x2_traces, freeze_x2_a2_traces) is rebound to `a3_counter`.
  * `a3_counter(base_url, model)` returns the FROZEN class, unchanged, for every model not in `A3_MODELS` (Qwen
    g1m0/g0m0 keep their original behaviour bit for bit); for an A3 model it returns `SequentialMistralTokenizer`.
  * `SequentialMistralTokenizer` = the frozen class with workers=1 (one request in flight, same request body, same
    cache, same fail-closed HTTP behaviour) plus two extra fail-closed checks on every response: `count == len(tokens)`
    and no trailing EOS id. It never corrects a count; a suspicious response raises `TokenizedContextInvalid`.
Nothing else changes: calibrate_trace / verify_trace / exact-equality gates, prompts, seeds, schedules, rates.

Activation: environment variable QUOTASHIFT_TOKEN_COUNTER=X2-A3, set only by scripts/x2_a3.py and inherited by the
`quotashift experiment` block subprocesses. `quotashift/workload/__init__.py` calls `activate_from_env()`; with the
variable unset this module is not even imported. Any other non-empty value fails closed.
"""

from __future__ import annotations

import os
from typing import Any

from quotashift.workload import tokenize as _frozen

ENV = "QUOTASHIFT_TOKEN_COUNTER"
ENV_VALUE = "X2-A3"
AMENDMENT = "X2-A3"
# model id -> special-token ids of its pinned tokenizer (Mistral-7B-Instruct-v0.3 @ c170c708, tokenizer.model.v3:
# bos 1 `<s>`, eos 2 `</s>`; verified offline against the SentencePiece model, sha256 37f00374...)
A3_MODELS: dict[str, dict[str, int]] = {"mistralai/Mistral-7B-Instruct-v0.3": {"bos_id": 1, "eos_id": 2}}

FROZEN_VLLM_TOKENIZER = _frozen.VllmTokenizer  # captured before any rebinding


class SequentialMistralTokenizer(_frozen.VllmTokenizer):
    """Frozen `/tokenize` counter with exactly one request in flight and fail-closed response checks."""

    name = "vllm_tokenize_sequential_a3"

    def __init__(self, base_url: str, model: str, *, timeout_s: float = 30.0, **_ignored: Any) -> None:
        if model not in A3_MODELS:
            raise ValueError(f"A3 sequential counter is Mistral-only; {model} keeps the frozen counter")
        super().__init__(base_url, model, workers=1, timeout_s=timeout_s)  # workers is forced, never configurable
        self._special = A3_MODELS[model]
        self.guard_trips = 0
        self.identity: dict[str, Any] = {**self.identity, "amendment": AMENDMENT, "counting": "sequential", "workers": 1,
                         "guards": ["count==len(tokens)", f"no trailing eos_id {self._special['eos_id']}"]}

    def _one(self, text: str) -> int:
        r = self._client.post(f"{self.base_url}/tokenize", json={"model": self.model, "prompt": text})
        r.raise_for_status()
        self.calls += 1
        j = r.json()
        n, toks = int(j["count"]), j.get("tokens")
        if not isinstance(toks, list) or len(toks) != n:
            self.guard_trips += 1
            raise _frozen.TokenizedContextInvalid(f"A3: /tokenize count {n} disagrees with its token list")
        if toks and toks[-1] == self._special["eos_id"]:
            self.guard_trips += 1
            raise _frozen.TokenizedContextInvalid(
                f"A3: /tokenize returned a trailing EOS (id {self._special['eos_id']}) for a raw prompt; "
                "the known concurrency artifact; refusing to count")
        return n

    def __call__(self, texts: Any) -> list[int]:
        import hashlib

        keys = [hashlib.sha256(t.encode()).hexdigest() for t in texts]
        for k, t in zip(keys, texts, strict=True):  # strictly sequential: no executor at all
            if k not in self._cache:
                self._cache[k] = self._one(t)
        return [self._cache[k] for k in keys]


def a3_counter(base_url: str, model: str, **kw: Any) -> Any:
    """Drop-in for the frozen `VllmTokenizer(base_url, model)` call sites."""
    if model in A3_MODELS:
        return SequentialMistralTokenizer(base_url, model, **kw)
    return FROZEN_VLLM_TOKENIZER(base_url, model, **kw)


def install() -> None:
    _frozen.VllmTokenizer = a3_counter  # type: ignore[assignment, misc]


def uninstall() -> None:
    _frozen.VllmTokenizer = FROZEN_VLLM_TOKENIZER  # type: ignore[misc]


def active() -> bool:
    return _frozen.VllmTokenizer is a3_counter


def activate_from_env() -> bool:
    v = os.environ.get(ENV)
    if not v:
        return False
    if v != ENV_VALUE:
        raise RuntimeError(f"{ENV}={v!r} is not a recognised token-counter amendment (expected {ENV_VALUE!r})")
    install()
    return True
