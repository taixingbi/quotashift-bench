"""Prometheus text parsing + vLLM metric-name resolution with fallbacks.

vLLM metric names change across versions (e.g. `vllm:gpu_cache_usage_perc`
was replaced by `vllm:kv_cache_usage_perc` in V1). We never hardcode a single
name: each logical metric lists candidate names, and `resolve()` records which
one the *running* server actually exposes. Missing metrics resolve to None and
are reported, never invented.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

_LINE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([^\s]+)(?:\s+\d+)?$")
_LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')

# logical name -> ordered candidate metric names (gauges/counters)
VLLM_METRIC_CANDIDATES: dict[str, tuple[str, ...]] = {
    "num_requests_running": ("vllm:num_requests_running",),
    "num_requests_waiting": ("vllm:num_requests_waiting",),
    "kv_cache_usage_perc": ("vllm:kv_cache_usage_perc", "vllm:gpu_cache_usage_perc"),
    "num_preemptions_total": ("vllm:num_preemptions_total", "vllm:num_preemptions"),
    "prompt_tokens_total": ("vllm:prompt_tokens_total", "vllm:prompt_tokens"),
    "generation_tokens_total": ("vllm:generation_tokens_total", "vllm:generation_tokens"),
    "prefix_cache_queries_total": ("vllm:prefix_cache_queries_total", "vllm:gpu_prefix_cache_queries_total"),
    "prefix_cache_hits_total": ("vllm:prefix_cache_hits_total", "vllm:gpu_prefix_cache_hits_total"),
}
VLLM_HISTOGRAM_CANDIDATES: dict[str, tuple[str, ...]] = {
    "ttft_seconds": ("vllm:time_to_first_token_seconds",),
    "itl_seconds": ("vllm:inter_token_latency_seconds", "vllm:time_per_output_token_seconds"),
    "e2e_seconds": ("vllm:e2e_request_latency_seconds",),
    "queue_time_seconds": ("vllm:request_queue_time_seconds",),
    "prefill_time_seconds": ("vllm:request_prefill_time_seconds",),
    "decode_time_seconds": ("vllm:request_decode_time_seconds",),
}


@dataclass
class Sample:
    name: str
    labels: dict[str, str]
    value: float


def parse_prometheus_text(text: str) -> list[Sample]:
    out: list[Sample] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue  # tolerate unknown lines rather than crash the run
        name, lbl, val = m.group(1), m.group(2) or "", m.group(3)
        try:
            v = float(val.replace("+Inf", "inf").replace("-Inf", "-inf"))
        except ValueError:
            continue
        labels = {k: bytes(v2, "utf-8").decode("unicode_escape") for k, v2 in _LABEL.findall(lbl)}
        out.append(Sample(name, labels, v))
    return out


@dataclass
class MetricSnapshot:
    values: dict[str, float | None]
    resolved_names: dict[str, str | None]
    histograms: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    histogram_sums: dict[str, tuple[float, float]] = field(default_factory=dict)  # (sum, count)

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(k for k, v in self.values.items() if v is None)


def resolve(samples: list[Sample]) -> MetricSnapshot:
    by_name: dict[str, list[Sample]] = {}
    for s in samples:
        by_name.setdefault(s.name, []).append(s)
    values: dict[str, float | None] = {}
    names: dict[str, str | None] = {}
    for logical, cands in VLLM_METRIC_CANDIDATES.items():
        values[logical], names[logical] = None, None
        for c in cands:
            if c in by_name:
                # sum over label sets (e.g. multiple model_name / engine labels)
                values[logical] = float(sum(s.value for s in by_name[c]))
                names[logical] = c
                break
    hists: dict[str, list[tuple[float, float]]] = {}
    sums: dict[str, tuple[float, float]] = {}
    for logical, cands in VLLM_HISTOGRAM_CANDIDATES.items():
        for c in cands:
            bk = by_name.get(c + "_bucket")
            if bk:
                agg: dict[float, float] = {}
                for s in bk:
                    le = float(s.labels.get("le", "inf").replace("+Inf", "inf"))
                    agg[le] = agg.get(le, 0.0) + s.value
                hists[logical] = sorted(agg.items())
                names[logical] = c
                ssum = sum(s.value for s in by_name.get(c + "_sum", []))
                scnt = sum(s.value for s in by_name.get(c + "_count", []))
                sums[logical] = (ssum, scnt)
                break
        names.setdefault(logical, None)
    return MetricSnapshot(values, names, hists, sums)


def hist_delta(after: list[tuple[float, float]], before: list[tuple[float, float]] | None) -> list[tuple[float, float]]:
    """Per-interval histogram (cumulative counters are monotone; reset => use `after`)."""
    if not before:
        return after
    b = dict(before)
    out = [(le, c - b.get(le, 0.0)) for le, c in after]
    if any(c < 0 for _, c in out):
        return after  # counter reset (server restart) -> treat as fresh
    return out


def finite(x: float | None) -> float | None:
    return None if x is None or math.isnan(x) else x
