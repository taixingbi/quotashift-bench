"""X2 Amendment A2 (DRAFT, not frozen): coverage-preserving stratified competitor arrivals.

docs/PROTOCOL_X2_AMENDMENT_A2.md. Owner decision 2026-11-26, after the g1m0 main freeze was refused by the frozen v4
arrival-coverage gate (the decode competitor sends N = 4 requests per 120 s arm at the selected low rate).

What changes, and only this: for a fixed-count competitor phase (`request_count` N over a window of T seconds), the
N arrival times are drawn one per stratum,

    t_k = t_offset + (k + U_k) * T / N,   k = 0 .. N-1,   U_k iid Uniform[0, 1)

from a dedicated, predeclared RNG stream (SeedSequence(entropy=seed, spawn_key=(crc32("<tenant>|<label>"), 103))),
then sorted chronologically. The frozen law (scenario.py `_fixed_count_items`) draws N iid Uniform[0, T) times from
stream 101. Everything else is the frozen code path, called unchanged:

  * request ids, counts, token shapes, prompt text (stream 102), SLO fields: produced by the frozen method; A2 only
    replaces each request's `arrival_time_s` (the k-th request gets the k-th stratified time);
  * the same law applies to every fixed-count competitor phase: the attack, the token-matched control (`ctl_tmf`) and
    the independent A/A replicate (`<phase>~ind`); their distinct labels keep their streams independent;
  * victims (`_segment_items`, Poisson) are not touched.

A2 is opt-in and explicit: a scenario YAML selects it with `protocol_amendment: X2-A2` and
`competitor_arrival_law: stratified_v1`. Every other YAML is loaded by the frozen `load_scenario` unchanged; this
includes files that use the frozen schema's free-text `protocol_amendment` label for other amendments (v3.1: "3.1").
"""

from __future__ import annotations

import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

import numpy as np
import yaml
from pydantic import model_validator

from quotashift.scenario import ScenarioConfig
from quotashift.scenario import load_scenario as _frozen_load_scenario

PROTOCOL_ID = "X2-A2"
ARRIVAL_LAW = "stratified_v1"
STREAM_TAG = 103                      # frozen law: 101 = arrivals, 102 = prompt text; A2 arrivals use a new stream
AMENDMENT_KEYS = ("protocol_amendment", "competitor_arrival_law")


def stratum_rng(seed: int, tenant: str, label: str) -> np.random.Generator:
    key = zlib.crc32(f"{tenant}|{label}".encode())
    return np.random.default_rng(np.random.SeedSequence(entropy=seed, spawn_key=(key, STREAM_TAG)))


def stratified_times(n: int, duration: float, rng: np.random.Generator) -> np.ndarray:
    """One Uniform draw per equal-width stratum of [0, duration), sorted (already monotone; sorted for the contract)."""
    if n <= 0:
        raise ValueError("n must be > 0")
    u = rng.uniform(0.0, 1.0, size=n)
    return np.sort((np.arange(n) + u) * (duration / n))


class ScenarioConfigA2(ScenarioConfig):
    """ScenarioConfig with the A2 competitor arrival law. Selected only by the two explicit YAML keys."""

    protocol_amendment: Literal["X2-A2"]
    competitor_arrival_law: Literal["stratified_v1"]

    @model_validator(mode="after")
    def _a2_scope(self) -> ScenarioConfigA2:
        if self.protocol_version != 5:
            raise ValueError("X2-A2 applies to protocol_version 5 (X2) scenarios only")
        if not self.phases or not all(p.request_count is not None for p in self.phases):
            raise ValueError("X2-A2 needs fixed-count competitor phases (request_count); otherwise the law is moot")
        if self.comparison.primary_control not in ("token_matched_fixed", "independent_replicate"):
            raise ValueError("X2-A2 covers the X2 controls only (token_matched_fixed, independent_replicate)")
        return self

    def _fixed_count_items(self, tenant: str, *, in_tok: int, out_tok: int, n: int, t_offset: float, duration: float,
                           seed: int, label: str) -> list:
        items = super()._fixed_count_items(tenant, in_tok=in_tok, out_tok=out_tok, n=n, t_offset=t_offset,
                                           duration=duration, seed=seed, label=label)
        times = stratified_times(n, duration, stratum_rng(seed, tenant, label)) + t_offset
        out = []
        for it, t in zip(items, times, strict=True):
            req = it.request.model_copy(update={"arrival_time_s": float(t)})
            out.append(it.model_copy(update={"request": req}))
        return out


def is_a2(data: dict) -> bool:
    """A2 is selected by its own label or its own key. `protocol_amendment` alone is a frozen free-text label used
    by other amendments (v3.1 "3.1"), so its mere presence never selects A2."""
    return data.get("protocol_amendment") == PROTOCOL_ID or "competitor_arrival_law" in data


def load_scenario_any(path: str | Path) -> ScenarioConfig:
    """A2 YAMLs -> ScenarioConfigA2; every other YAML -> the frozen loader, unchanged."""
    p = Path(path)
    data = yaml.safe_load(p.read_text())
    if not (isinstance(data, dict) and is_a2(data)):
        return _frozen_load_scenario(p)
    sc = ScenarioConfigA2.model_validate(data)
    sc._source_dir = p.resolve().parent
    return sc


@contextmanager
def a2_loader() -> Iterator[None]:
    """For the A2 freeze/stage/validation drivers only, and only for the duration of the block: the frozen freeze code
    imports `quotashift.scenario.load_scenario` at call time, so pointing that name at the dispatcher lets the frozen
    gates run unchanged on A2 files. Non-A2 files still go to the frozen loader. The frozen name is restored on exit;
    the frozen X2/v5/X1 drivers never enter this context."""
    import quotashift.scenario as qs

    qs.load_scenario = load_scenario_any
    try:
        yield
    finally:
        qs.load_scenario = _frozen_load_scenario
