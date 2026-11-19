"""Deterministic, zero-cost mock of a vLLM-like continuous-batching engine.

PURPOSE: exercise the gateway/runner/accounting control loop and the E0
harness without a GPU. It is NOT a calibrated performance model: the default
step-cost coefficients are placeholders, not derived from any GPU measurement.
Every result produced with it is labelled `backend_kind=mock` and figures are
watermarked.

Modelled (qualitatively, after vLLM V1 docs): iteration-level batching, a
per-step token budget (`max_num_batched_tokens`) with chunked prefill,
`max_num_seqs`, paged KV blocks, FCFS or priority waiting queue, and
recompute-style preemption of the most recently admitted running request when
KV blocks run out.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict


class EngineParams(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kv_blocks_total: int = 4096
    block_size: int = 16
    max_num_seqs: int = 64
    max_num_batched_tokens: int = 2048
    max_model_len: int = 8192
    scheduling_policy: Literal["fcfs", "priority"] = "fcfs"
    # step_time = c0 + c_prefill*prefill_tokens + c_decode*decode_seqs + c_ctx*context_tokens
    c0_s: float = 0.004
    c_prefill_s: float = 0.00004
    c_decode_s: float = 0.0002
    c_ctx_s: float = 0.0000002
    calibration_note: str = "UNCALIBRATED placeholder coefficients (no GPU measurement)"


@dataclass
class _Seq:
    rid: str
    prompt_len: int
    target_out: int  # realized output length (mock "EOS"); engine-internal only
    priority: int
    arrival_seq: int
    prefilled: int = 0  # tokens of (prompt + generated-before-preemption) already prefilled
    generated: int = 0
    first_token_emitted: bool = False
    blocks: int = 0

    @property
    def context(self) -> int:
        return self.prompt_len + self.generated

    @property
    def prefill_target(self) -> int:
        # after recompute-preemption, prompt + already generated tokens must be re-prefilled
        return self.prompt_len + self.generated


@dataclass
class EngineEvent:
    rid: str
    kind: Literal["first_token", "token", "finished", "preempted", "rejected"]
    generated: int = 0
    detail: str | None = None


@dataclass
class EngineStats:
    num_preemptions_total: int = 0
    prompt_tokens_total: int = 0
    generation_tokens_total: int = 0
    steps_total: int = 0
    finished_total: int = 0


@dataclass
class EngineModel:
    params: EngineParams = field(default_factory=EngineParams)

    def __post_init__(self) -> None:
        self.waiting: deque[_Seq] = deque()
        self.running: list[_Seq] = []
        self.free_blocks = self.params.kv_blocks_total
        self.stats = EngineStats()
        self._arrival_counter = 0

    # ------------------------------------------------------------ public API
    def add_request(self, rid: str, prompt_len: int, max_tokens: int, target_out: int, priority: int = 0) -> EngineEvent | None:
        """Enqueue. `target_out` simulates where the model would emit EOS."""
        if prompt_len + max_tokens > self.params.max_model_len or prompt_len <= 0:
            return EngineEvent(rid, "rejected", detail="exceeds max_model_len")
        need = math.ceil((prompt_len + max_tokens) / self.params.block_size)
        if need > self.params.kv_blocks_total:
            # guarantees a lone request can always finish (no livelock)
            return EngineEvent(rid, "rejected", detail="prompt+max_tokens exceeds total KV capacity")
        self._arrival_counter += 1
        s = _Seq(rid, prompt_len, max(1, min(target_out, max_tokens)), priority, self._arrival_counter)
        self.waiting.append(s)
        if self.params.scheduling_policy == "priority":
            self.waiting = deque(sorted(self.waiting, key=lambda q: (q.priority, q.arrival_seq)))
        return None

    def abort(self, rid: str) -> bool:
        for s in list(self.waiting):
            if s.rid == rid:
                self.waiting.remove(s)
                return True
        for s in self.running:
            if s.rid == rid:
                self._free(s)
                self.running.remove(s)
                return True
        return False

    def has_work(self) -> bool:
        return bool(self.waiting or self.running)

    @property
    def kv_usage(self) -> float:
        return 1.0 - self.free_blocks / self.params.kv_blocks_total

    def observe(self) -> dict:
        return {
            "num_requests_running": len(self.running),
            "num_requests_waiting": len(self.waiting),
            "kv_cache_usage_perc": self.kv_usage,
            "num_preemptions_total": self.stats.num_preemptions_total,
            "prompt_tokens_total": self.stats.prompt_tokens_total,
            "generation_tokens_total": self.stats.generation_tokens_total,
        }

    # ------------------------------------------------------------ internals
    def _blocks_for(self, tokens: int) -> int:
        return math.ceil(tokens / self.params.block_size)

    def _free(self, s: _Seq) -> None:
        self.free_blocks += s.blocks
        s.blocks = 0

    def _grow(self, s: _Seq, tokens: int) -> bool:
        need = self._blocks_for(tokens) - s.blocks
        if need <= 0:
            return True
        if need > self.free_blocks:
            return False
        self.free_blocks -= need
        s.blocks += need
        return True

    def _preempt_one(self, exclude: _Seq) -> bool:
        cands = [s for s in self.running if s is not exclude]
        if not cands:
            return False
        victim = max(cands, key=lambda q: (q.priority, q.arrival_seq))  # lowest priority / newest
        self.running.remove(victim)
        self._free(victim)
        victim.prefilled = 0
        self.waiting.appendleft(victim)
        self.stats.num_preemptions_total += 1
        self._pending_events.append(EngineEvent(victim.rid, "preempted", victim.generated))
        return True

    def step(self) -> tuple[float, list[EngineEvent]]:
        """Run one engine iteration; returns (duration_s, events)."""
        self._pending_events: list[EngineEvent] = []
        p = self.params
        budget = p.max_num_batched_tokens
        decode_seqs = 0
        prefill_tokens = 0

        # 1) decode for running sequences that finished prefill
        for s in list(self.running):
            if s not in self.running or s.prefilled < s.prefill_target or budget <= 0:
                continue
            while not self._grow(s, s.context + 1):
                if not self._preempt_one(exclude=s):
                    break
            if s not in self.running or self._blocks_for(s.context + 1) > s.blocks:
                continue
            budget -= 1
            decode_seqs += 1
            s.generated += 1
            s.prefilled += 1
            self.stats.generation_tokens_total += 1
            self._emit_token(s)

        # 2) continue chunked prefill for running seqs, then admit waiting
        def do_prefill(s: _Seq) -> bool:
            nonlocal budget, prefill_tokens
            chunk = min(budget, s.prefill_target - s.prefilled)
            if chunk <= 0:
                return s.prefilled >= s.prefill_target
            if not self._grow(s, s.prefilled + chunk + (1 if s.prefilled + chunk >= s.prefill_target else 0)):
                return False
            s.prefilled += chunk
            budget -= chunk
            prefill_tokens += chunk
            self.stats.prompt_tokens_total += chunk
            if s.prefilled >= s.prefill_target:
                # prefill completion samples the next token in the same iteration
                s.generated += 1
                s.prefilled += 1
                self.stats.generation_tokens_total += 1
                self._emit_token(s)
            return True

        for s in list(self.running):
            if s in self.running and s.prefilled < s.prefill_target and budget > 0:
                do_prefill(s)
        while self.waiting and budget > 0 and len(self.running) < p.max_num_seqs:
            s = self.waiting[0]
            first_chunk = min(budget, s.prefill_target)
            if self._blocks_for(first_chunk + 1) > self.free_blocks:
                break  # head-of-line: wait for KV to free up
            self.waiting.popleft()
            self.running.append(s)
            do_prefill(s)

        context_tokens = sum(s.context for s in self.running)
        dt = p.c0_s + p.c_prefill_s * prefill_tokens + p.c_decode_s * decode_seqs + p.c_ctx_s * context_tokens
        self.stats.steps_total += 1
        return dt, self._pending_events

    def _emit_token(self, s: _Seq) -> None:
        if not s.first_token_emitted:
            s.first_token_emitted = True
            self._pending_events.append(EngineEvent(s.rid, "first_token", s.generated))
        else:
            self._pending_events.append(EngineEvent(s.rid, "token", s.generated))
        if s.generated >= s.target_out:
            self.running.remove(s)
            self._free(s)
            self.stats.finished_total += 1
            self._pending_events.append(EngineEvent(s.rid, "finished", s.generated))
