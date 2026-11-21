"""Protocol v3 controlled prefix reuse (A7, A9-prefix). docs/A7_A9_EXPERIMENT_DESIGN.md.

Every prefix is derived from H(salt, scenario, seed, ARM, tenant[, rid]), so prefixes are reused only within
one arm and never across arms (no cross-arm cache contamination). Prefix words come from the single-token
nonce vocabulary and REPLACE the leading filler words, so each request's word count and planned
`input_token_count` are unchanged; the request-unique "[req <rid>]" marker follows the prefix.

- victims: each victim tenant has one shared prefix of `victim_prefix_tokens` (realistic tenant system prompt).
- competitor `shared`: all competitor requests of the arm share one prefix; `unique`: one prefix per request.
- Requests without a prefix (length 0, or control mode `none`) get the v2 per-request nonce instead.
"""

from __future__ import annotations

import hashlib

import numpy as np

from quotashift.schema import TraceItem
from quotashift.workload.isolation import NONCE_VOCAB, apply_arm_nonce


def _rng(*parts: object) -> np.random.Generator:
    return np.random.default_rng(int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16], 16))


def prefix_words(n: int, *parts: object) -> list[str]:
    idx = _rng(*parts).integers(0, len(NONCE_VOCAB), size=n)
    return [NONCE_VOCAB[i] for i in idx]


def apply_prefix_structure(items: list[TraceItem], *, arm: str, victim_prefix_tokens: int,
                           competitor_prefix_tokens: int, competitor_mode: str, scenario_id: str, seed: int,
                           salt: str = "") -> list[TraceItem]:
    if competitor_mode not in ("shared", "unique", "none"):
        raise ValueError(f"unknown competitor prefix mode {competitor_mode!r}")
    base = (salt, scenario_id, seed, arm)
    shared: dict[tuple[str, str], list[str]] = {}
    out: list[TraceItem] = []
    plain: list[int] = []  # indices that get the v2 nonce instead
    for it in items:
        r = it.request
        cls = r.workload_class
        if cls == "victim":
            n, key = victim_prefix_tokens, ("victim", r.tenant_id)
        elif cls == "competitor" and competitor_mode != "none":
            n = competitor_prefix_tokens
            key = ("competitor", r.tenant_id) if competitor_mode == "shared" else ("competitor_unique", r.request_id)
        else:
            n, key = 0, ("", "")
        if n <= 0:
            plain.append(len(out))
            out.append(it)
            continue
        if r.prompt_text is None:
            raise ValueError("prefix structure needs synthetic_text prompts")
        if key not in shared:
            shared[key] = prefix_words(n, *base, *key)
        words = r.prompt_text.split(" ")
        head, filler = words[:2], words[2:]
        k = min(n, len(filler))  # short prompts share the first k words of the same prefix
        new = shared[key][:k] + head + filler[k:]
        if key[0] == "competitor_unique":
            del shared[key]
        out.append(TraceItem(request=r.model_copy(update={"prompt_text": " ".join(new)}), oracle=it.oracle))
    if plain:
        nonce = apply_arm_nonce([out[i] for i in plain], arm=arm, scenario_id=scenario_id, seed=seed, salt=salt)
        for i, it in zip(plain, nonce, strict=True):
            out[i] = it
    return out


def shared_prefix_fraction(items: list[TraceItem], workload_class: str, block: int = 16) -> float:
    """Fraction of a class's requests whose first `block` words equal another request's (diagnostic)."""
    firsts = [" ".join(it.request.prompt_text.split(" ")[:block]) for it in items
              if it.request.workload_class == workload_class and it.request.prompt_text]
    if not firsts:
        return 0.0
    from collections import Counter

    c = Counter(firsts)
    return sum(v for v in c.values() if v > 1) / len(firsts)
