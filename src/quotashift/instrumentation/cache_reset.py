"""Verified prefix-cache reset (protocol v3, optional, fail closed).

`POST /reset_prefix_cache` exists in vLLM's OpenAI server but may be disabled on a given deployment. A reset
is accepted only if VERIFIED with a probe: a unique synthetic prompt is sent twice (the second must produce
prefix-cache hits), the reset is requested, and the prompt is sent again (it must produce zero hits). Probe
requests use `max_tokens=1` and run only against the private target. Requires an otherwise idle server.
"""

from __future__ import annotations

import hashlib

import httpx

from quotashift.instrumentation.prom import parse_prometheus_text, resolve
from quotashift.workload.isolation import NONCE_VOCAB


def _hits(c: httpx.Client, url: str) -> tuple[float, float]:
    v = resolve(parse_prometheus_text(c.get(url + "/metrics", timeout=5).text)).values
    return v.get("prefix_cache_hits_total") or 0.0, v.get("prefix_cache_queries_total") or 0.0


def reset_and_verify(base_url: str, model: str, *, tag: str, probe_words: int = 96) -> dict:
    url = base_url.rstrip("/")
    h = int(hashlib.sha256(tag.encode()).hexdigest()[:12], 16)
    words = [NONCE_VOCAB[(h // (i + 1) + 7 * i) % len(NONCE_VOCAB)] for i in range(probe_words)]
    prompt = "probe " + " ".join(words)
    out: dict = {"endpoint": "/reset_prefix_cache", "verified": False}
    with httpx.Client(timeout=30) as c:
        def send() -> float:
            h0, _ = _hits(c, url)
            c.post(url + "/v1/completions", json={"model": model, "prompt": prompt, "max_tokens": 1,
                                                  "temperature": 0.0}).raise_for_status()
            h1, _ = _hits(c, url)
            return h1 - h0
        try:
            send()
            warm = send()
            r = c.post(url + "/reset_prefix_cache")
            out["reset_http_status"] = r.status_code
            if r.status_code != 200:
                out["reason"] = f"reset endpoint returned HTTP {r.status_code} (not enabled on this server?)"
                return out
            cold = send()
        except httpx.HTTPError as e:
            out["reason"] = f"{type(e).__name__}: {e}"
            return out
    out.update({"probe_hits_before_reset": warm, "probe_hits_after_reset": cold,
                "verified": warm > 0 and cold == 0})
    if not out["verified"]:
        out["reason"] = "probe did not show warm hits then zero hits after reset"
    return out
