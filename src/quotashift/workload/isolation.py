"""Protocol v2 prefix-cache isolation: per-arm salted-hash prompt nonce (ADR-Q13).

Problem (measured on the historical v1 runs): the control arm replayed byte-identical victim
prompts right after the attack arm, so vLLM's prefix cache served the control far more often
(e.g. A5 attack 0.02 vs control 0.98 hit ratio), biasing attack/control ratios upward.

v2 nonce, applied to EVERY request of BOTH arms (victim and competitor):
- 4 nonce words are placed at the very start of the prompt (first KV block), REPLACING the first
  4 filler words, so the planned `input_token_count` is unchanged and matched budgets are
  preserved exactly (word count identical; see `tests/unit/test_isolation.py`).
- Word i is drawn from one shared vocabulary of common English words with
  index = (H(salt, scenario, seed, rid, i) + arm_offset_i) mod |V|, where H is SHA-256. The
  vocabulary and its distribution are identical for both arms (no systematic arm difference);
  word 0 uses offset 0 (attack) vs |V|/2 (control), so the FIRST token always differs between
  arms for the same request id, i.e. no shared first KV block. Different request ids differ
  in H, so requests within an arm do not share a prefix either (up to hash collisions).
- Token-id prompts get 4 replaced ids by the same rule (range [1000, 30000)).

Nonces do not *guarantee* zero cache hits (e.g. chat templates, shared system prompts, hash
collisions, or reuse of the same `isolation_salt` across repeated experiments while the server
cache is warm). Observed per-arm hit ratios are always recorded and must be checked.
"""

from __future__ import annotations

import hashlib

from quotashift.schema import TraceItem

# Common English words; each is a single token (with or without leading space) in most BPE
# vocabularies. Verified against the live Qwen2.5 tokenizer before use (scripts/check_nonce_vocab.py).
NONCE_VOCAB: tuple[str, ...] = tuple("""
the of and to in is it that for on with as was at by be this from or are an not have but all can one has
were more will their there what about which when out up time so some them other into two make like see way
look over first water long day may down side been now find any new work part take get place made live where
after back little only round man year came show every good give our under name very through just form much
great think say help low line turn cause same mean move right boy old too does tell set three want air well
also play small end put home read hand port large spell add even land here must big high such follow act why
ask men change went light kind off need house picture try us again animal point mother world near build self
earth father head stand own page should country found answer school grow study still learn plant cover food
""".split())
ARMS = ("attack", "control")
N_NONCE = 4


def _h(*parts: object) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16], 16)


def nonce_words(rid: str, *, arm: str, scenario_id: str, seed: int, salt: str = "") -> list[str]:
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {ARMS}")
    v = len(NONCE_VOCAB)
    words = []
    for i in range(N_NONCE):
        if i == 0:  # shared hash, arm-specific offset: first token always differs between arms
            idx = (_h(salt, scenario_id, seed, rid, 0) + (0 if arm == "attack" else v // 2)) % v
        else:
            idx = _h(salt, scenario_id, seed, rid, i, arm) % v
        words.append(NONCE_VOCAB[idx])
    return words


def _nonce_ids(rid: str, *, arm: str, scenario_id: str, seed: int, salt: str) -> list[int]:
    span = 29000
    out = []
    for i in range(N_NONCE):
        off = (0 if arm == "attack" else span // 2) if i == 0 else 0
        h = _h(salt, scenario_id, seed, rid, i) if i == 0 else _h(salt, scenario_id, seed, rid, i, arm)
        out.append(1000 + (h + off) % span)
    return out


def apply_arm_nonce(items: list[TraceItem], *, arm: str, scenario_id: str, seed: int,
                    salt: str = "") -> list[TraceItem]:
    """Return a copy of `items` with the v2 nonce applied; planned token counts unchanged."""
    out: list[TraceItem] = []
    for it in items:
        r = it.request
        upd: dict = {}
        if r.prompt_text is not None:
            words = r.prompt_text.split(" ")
            nw = nonce_words(r.request_id, arm=arm, scenario_id=scenario_id, seed=seed, salt=salt)
            # historical layout: "[req", "<rid>]", filler... -> nonce replaces the first filler words
            head, filler = words[:2], words[2:]
            if len(filler) >= N_NONCE:
                new = nw + head + filler[N_NONCE:]
            else:  # very short prompt: nonce replaces all filler; count grows by the shortfall
                new = nw + head
                upd["input_token_count"] = r.input_token_count + (N_NONCE - len(filler))
            upd["prompt_text"] = " ".join(new)
        if r.prompt_token_ids is not None:
            ids = list(r.prompt_token_ids)
            nid = _nonce_ids(r.request_id, arm=arm, scenario_id=scenario_id, seed=seed, salt=salt)
            k = min(N_NONCE, len(ids))
            upd["prompt_token_ids"] = tuple(nid[:k] + ids[k:])
        out.append(TraceItem(request=r.model_copy(update=upd), oracle=it.oracle))
    return out
