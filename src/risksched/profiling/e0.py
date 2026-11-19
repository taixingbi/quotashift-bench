"""E0: single-model / single-GPU resource profiling harness.

Two parts:
1. Closed-loop grid: prompt length x requested output x concurrency x trials.
   Unsupported cells (prompt + max_tokens > max_model_len) are recorded as
   `skipped_unsupported`; failing cells keep status `error`/`partial` rows.
   Nothing is interpolated or invented.
2. Open-loop rate sweep for one (prompt, output) shape: offered RPS vs
   completed RPS / SLO goodput / TTFT, used to locate the saturation knee.

Prompts are random token IDs (like vLLM's `random` benchmark dataset), unique
per request, so there are no cross-request prefix-cache hits. Requested
`max_tokens` and realized output tokens are recorded separately.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field

from risksched.config import BackendConfig, RunControl
from risksched.evaluation.metrics import derive_request_metrics, percentile
from risksched.gateway.core import Gateway
from risksched.instrumentation.gpu import GpuSampler
from risksched.instrumentation.provenance import build_manifest
from risksched.instrumentation.recorder import RunRecorder, validate_events
from risksched.runtime.clients import ClosedLoopClient, OpenLoopClient
from risksched.runtime.live import LiveConfig, run_live
from risksched.runtime.runner import REPO, SafetyError, local_mock_server, make_backend
from risksched.runtime.sim import SimConfig, run_simulation
from risksched.schedulers.simple import FCFSPassThrough
from risksched.schema import OracleInfo, Request, SLOType, TraceItem
from risksched.serving.engine_model import EngineModel


class RateSweep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_tokens: int
    output_tokens: int
    rates_rps: list[float]
    duration_s: float = 60.0
    trials: int = 3
    ttft_deadline_ms: float = 2000.0  # provisional reporting threshold, re-calibrated from E0
    tpot_target_ms: float | None = 100.0
    knee_completion_ratio: float = 0.95


class ProfileSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_lengths: list[int]
    output_lengths: list[int]
    concurrencies: list[int]
    trials: int = 3
    min_requests_per_cell: int = 16
    requests_per_slot: int = 2
    max_model_len: int = 8192
    ignore_eos: bool = True
    cell_timeout_s: float = 900.0
    request_timeout_s: float = 600.0
    warmup_requests: int = 4
    max_total_seconds: float = 4 * 3600.0
    vocab_low: int = 1000
    vocab_high: int = 30000
    rate_sweep: RateSweep | None = None


class ProfileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experiment_id: str = "e0"
    description: str = ""
    backend: BackendConfig = Field(default_factory=BackendConfig)
    run: RunControl = Field(default_factory=RunControl)
    profile: ProfileSpec


def load_profile_config(path: Path) -> ProfileConfig:
    return ProfileConfig.model_validate(yaml.safe_load(Path(path).read_text()))


def _make_item(tag: str, i: int, now: float, p: int, o: int, rng: np.random.Generator, spec: ProfileSpec,
               seed: int, ttft_ms: float, tpot_ms: float | None, realized: int | None = None) -> TraceItem:
    rid = f"{tag}-{i:06d}"
    ids = tuple(int(x) for x in rng.integers(spec.vocab_low, spec.vocab_high, size=p))
    req = Request(request_id=rid, tenant_id="profile", arrival_time_s=now, prompt_token_ids=ids,
                  input_token_count=p, max_output_tokens=o, workload_class="profile",
                  slo_type=SLOType.INTERACTIVE, ttft_deadline_ms=ttft_ms, tpot_target_ms=tpot_ms,
                  seed=seed, trace_id=tag)
    return TraceItem(request=req, oracle=OracleInfo(request_id=rid, realized_output_tokens=realized if realized is not None else o))


class _Runner:
    """Executes one load episode on the configured backend; fresh gateway each time."""

    def __init__(self, cfg: ProfileConfig, url: str | None) -> None:
        self.cfg = cfg
        self.url = url
        self.gpu = GpuSampler()

    def episode(self, client, run_id: str, end_time_s: float, request_timeout_s: float) -> tuple[pd.DataFrame, list[dict], dict]:
        rec = RunRecorder(self.cfg.experiment_id, run_id, clock="virtual" if self.cfg.backend.kind == "mock" else "monotonic")
        gw = Gateway(FCFSPassThrough(), ["profile"], rec, max_queue_wait_s=None)
        extra: dict[str, Any] = {}
        if self.cfg.backend.kind == "mock":
            engine = EngineModel(self.cfg.backend.engine)  # fresh engine per episode (no carry-over)
            ts = run_simulation(client, gw, engine, SimConfig(end_time_s=end_time_s, metrics_interval_s=0.25,
                                                               request_timeout_s=request_timeout_s))
        else:
            async def go():
                be = make_backend(self.cfg.backend, self.url)
                try:
                    before = await be.scrape_metrics()
                    rows = await run_live(client, gw, be, LiveConfig(end_time_s=end_time_s, metrics_interval_s=0.5,
                                                                      request_timeout_s=request_timeout_s,
                                                                      max_concurrency_cap=self.cfg.run.max_concurrency_cap),
                                          gpu=self.gpu)
                    after = await be.scrape_metrics()
                    return rows, before, after
                finally:
                    await be.aclose()
            ts, before, after = asyncio.run(go())
            if before and after:
                for k in ("num_preemptions_total", "prompt_tokens_total", "generation_tokens_total",
                          "prefix_cache_hits_total", "prefix_cache_queries_total"):
                    b, a = before.values.get(k), after.values.get(k)
                    extra[f"delta_{k}"] = (a - b) if (a is not None and b is not None) else None
                extra["resolved_metric_names"] = after.resolved_names
        errs = validate_events(rec.events, set(rec.rows))
        extra["event_validation_errors"] = len(errs)
        return pd.DataFrame(list(rec.rows.values())), ts, extra


def _cell_stats(df: pd.DataFrame, ts: list[dict], extra: dict) -> dict:
    d = derive_request_metrics(df)
    comp = d[d["terminal_status"] == "completed"]
    n = len(d)
    if len(comp):
        t_start = d["t_offered"].min()
        t_end = comp["t_terminal"].max()
        span = max(t_end - t_start, 1e-9)
    else:
        span = None
    tsd = pd.DataFrame(ts) if ts else pd.DataFrame()

    def col(c: str, f: str):
        if c not in tsd or tsd[c].dropna().empty:
            return None
        return float(getattr(tsd[c].dropna(), f)())

    preempt = extra.get("delta_num_preemptions_total")
    if preempt is None and "num_preemptions_total" in tsd and not tsd["num_preemptions_total"].dropna().empty:
        preempt = float(tsd["num_preemptions_total"].dropna().iloc[-1] - tsd["num_preemptions_total"].dropna().iloc[0])
    return {
        "n_requests": n,
        "n_completed": len(comp),
        "n_failed": int(n - len(comp)),
        "status_counts": json.dumps(d["terminal_status"].value_counts().to_dict()),
        "span_s": span,
        "req_per_s": len(comp) / span if span else None,
        "output_tok_per_s": float(comp["output_tokens"].sum() / span) if span else None,
        "total_tok_per_s": float((comp["output_tokens"].sum() + comp["input_token_count"].sum()) / span) if span else None,
        "ttft_p50_ms": percentile(comp["ttft_ms"], 50), "ttft_p95_ms": percentile(comp["ttft_ms"], 95),
        "ttft_p99_ms": percentile(comp["ttft_ms"], 99),
        "tpot_p50_ms": percentile(comp["tpot_ms"], 50), "tpot_p95_ms": percentile(comp["tpot_ms"], 95),
        "e2e_p50_ms": percentile(comp["e2e_ms"], 50), "e2e_p95_ms": percentile(comp["e2e_ms"], 95),
        "realized_output_mean": float(comp["output_tokens"].mean()) if len(comp) else None,
        "realized_eq_requested_frac": float((comp["output_tokens"] == comp["max_output_tokens"]).mean()) if len(comp) else None,
        "output_tokens_source": ",".join(sorted(set(map(str, comp["output_tokens_source"].dropna())))) or None,
        "kv_usage_max": col("kv_cache_usage_perc", "max"), "kv_usage_mean": col("kv_cache_usage_perc", "mean"),
        "engine_waiting_max": col("num_requests_waiting", "max"),
        "engine_running_max": col("num_requests_running", "max"),
        "preemptions": preempt,
        "gpu_util_mean": col("gpu_gpu_util_perc", "mean"), "gpu_mem_used_max_mib": col("gpu_mem_used_mib", "max"),
        "scrape_failures": int((~tsd["scrape_ok"]).sum()) if "scrape_ok" in tsd else None,
        "event_validation_errors": extra.get("event_validation_errors"),
        "resolved_metric_names": json.dumps(extra.get("resolved_metric_names")) if extra.get("resolved_metric_names") else None,
    }


def run_profile(cfg: ProfileConfig, seed: int, results_root: Path, base_url_override: str | None = None,
                only_rate_sweep: bool = False, skip_rate_sweep: bool = False) -> Path:
    spec = cfg.profile
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_id = f"{ts}_profile_{cfg.backend.kind}_{seed}"
    out = results_root / cfg.experiment_id / run_id
    (out / "figures").mkdir(parents=True)
    (out / "logs").mkdir()
    if cfg.backend.kind == "mock_http" and cfg.backend.time_scale != 1.0:
        raise SafetyError("mock_http profiling requires time_scale=1.0")

    def body(url: str | None) -> Path:
        runner = _Runner(cfg, url)
        rng = np.random.default_rng(seed)
        t_budget0 = time.time()
        cells, all_requests = [], []
        backend_info = None
        if url:
            async def info():
                be = make_backend(cfg.backend, url)
                try:
                    return await be.info()
                finally:
                    await be.aclose()
            backend_info = asyncio.run(info())

        # warm-up (recorded, excluded from cells): CUDA graphs / allocator / JIT
        if spec.warmup_requests and not only_rate_sweep:
            wc = ClosedLoopClient(1, spec.warmup_requests, lambda i, now: _make_item(
                "warmup", i, now, min(spec.prompt_lengths), min(spec.output_lengths), rng, spec, seed, 1e9, None))
            wdf, _, _ = runner.episode(wc, "warmup", spec.cell_timeout_s, spec.request_timeout_s)
            wdf["cell"] = "warmup"
            all_requests.append(wdf)

        grid = [] if only_rate_sweep else [
            (p, o, c, k) for p in spec.prompt_lengths for o in spec.output_lengths
            for c in spec.concurrencies for k in range(spec.trials)
        ]
        for p, o, c, k in grid:
            key = {"prompt_tokens": p, "max_tokens": o, "concurrency": c, "trial": k}
            if p + o > spec.max_model_len:
                cells.append(key | {"status": "skipped_unsupported", "reason": f"{p}+{o} > max_model_len {spec.max_model_len}"})
                continue
            if time.time() - t_budget0 > spec.max_total_seconds:
                cells.append(key | {"status": "aborted_budget", "reason": "max_total_seconds exceeded"})
                continue
            n_req = max(spec.min_requests_per_cell, c * spec.requests_per_slot)
            tag = f"p{p}-o{o}-c{c}-t{k}"
            client = ClosedLoopClient(c, n_req, lambda i, now, tag=tag, p=p, o=o: _make_item(
                tag, i, now, p, o, rng, spec, seed, 1e9, None))
            try:
                df, tsr, extra = runner.episode(client, tag, spec.cell_timeout_s, spec.request_timeout_s)
            except Exception as e:  # noqa: BLE001 - recorded as an explicit failed row
                cells.append(key | {"status": "error", "reason": f"{type(e).__name__}:{e}"[:300]})
                continue
            st = _cell_stats(df, tsr, extra)
            status = "ok" if st["n_completed"] == st["n_requests"] else ("partial" if st["n_completed"] else "error")
            cells.append(key | {"status": status, "reason": None} | st)
            df["cell"] = tag
            all_requests.append(df)

        sweep_rows = []
        rs = spec.rate_sweep
        if rs and not skip_rate_sweep:
            for rate in rs.rates_rps:
                for k in range(rs.trials):
                    if time.time() - t_budget0 > spec.max_total_seconds:
                        sweep_rows.append({"rate_rps": rate, "trial": k, "status": "aborted_budget"})
                        continue
                    srng = np.random.default_rng([seed, k, int(rate * 1000)])
                    arr, t = [], 0.0
                    while True:
                        t += srng.exponential(1.0 / rate)
                        if t >= rs.duration_s:
                            break
                        arr.append(t)
                    tag = f"rate{rate}-t{k}"
                    items = [_make_item(tag, i, a, rs.prompt_tokens, rs.output_tokens, srng, spec, seed,
                                        rs.ttft_deadline_ms, rs.tpot_target_ms) for i, a in enumerate(arr)]
                    try:
                        df, tsr, extra = runner.episode(OpenLoopClient(items), tag, rs.duration_s + spec.request_timeout_s,
                                                        spec.request_timeout_s)
                    except Exception as e:  # noqa: BLE001
                        sweep_rows.append({"rate_rps": rate, "trial": k, "status": "error", "reason": str(e)[:300]})
                        continue
                    d = derive_request_metrics(df)
                    comp = d[d["terminal_status"] == "completed"]
                    st = _cell_stats(df, tsr, extra)
                    sweep_rows.append({
                        "rate_rps": rate, "trial": k, "status": "ok", "offered": len(d),
                        "offered_rps": len(d) / rs.duration_s,
                        # all completions incl. drain (NOT a throughput measure past saturation)
                        "completed_eventually_rps": len(comp) / rs.duration_s,
                        # achieved throughput: completions inside the arrival window only
                        "completed_rps": int((comp["t_terminal"] <= rs.duration_s).sum()) / rs.duration_s,
                        "slo_goodput_rps": float(d["slo_met"].sum()) / rs.duration_s,
                        "success_fraction": float(d["slo_met"].mean()) if len(d) else None,
                        "ttft_p50_ms": percentile(comp["ttft_ms"], 50), "ttft_p95_ms": percentile(comp["ttft_ms"], 95),
                        "tpot_p50_ms": percentile(comp["tpot_ms"], 50), "tpot_p95_ms": percentile(comp["tpot_ms"], 95),
                        "output_tok_per_s": float(comp["output_tokens"].sum()) / rs.duration_s,
                        "kv_usage_max": st["kv_usage_max"],
                        "engine_waiting_max": st["engine_waiting_max"],
                        "preemptions": st["preemptions"],
                        "event_validation_errors": extra.get("event_validation_errors"),
                    })
                    df["cell"] = tag
                    all_requests.append(df)

        cells_df = pd.DataFrame(cells)
        sweep_df = pd.DataFrame(sweep_rows)
        cells_df.to_parquet(out / "cells.parquet", index=False)
        cells_df.to_csv(out / "cells.csv", index=False)
        if len(sweep_df):
            sweep_df.to_parquet(out / "rate_sweep.parquet", index=False)
            sweep_df.to_csv(out / "rate_sweep.csv", index=False)
        all_requests = [r.dropna(axis=1, how="all") for r in all_requests if len(r)]
        if all_requests:
            pd.concat(all_requests, ignore_index=True).to_parquet(out / "requests.parquet", index=False)
        summary = summarize_profile(cells_df, sweep_df, rs)
        summary["synthetic_backend"] = cfg.backend.is_mock
        summary["wall_seconds"] = time.time() - t_budget0
        (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
        cfg_resolved = cfg.model_dump(mode="json")
        (out / "config.resolved.yaml").write_text(yaml.safe_dump(cfg_resolved, sort_keys=False))
        manifest = build_manifest(repo=REPO, experiment_id=cfg.experiment_id, run_id=run_id,
                                  scheduler={"name": "fcfs", "role": "profiling passthrough"}, seed=seed,
                                  config_resolved=cfg_resolved, backend_kind=cfg.backend.kind,
                                  backend_info=backend_info or {"engine_params": cfg.backend.engine.model_dump()},
                                  trace_sha256=None, clock="virtual" if cfg.backend.kind == "mock" else "monotonic")
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
        from risksched.evaluation.plots import plot_e0
        plot_e0(out)
        return out

    if cfg.backend.kind == "mock_http" and not (base_url_override or cfg.backend.base_url):
        with local_mock_server(cfg.backend) as url:
            return body(url)
    if cfg.backend.kind == "mock":
        return body(None)
    return body(base_url_override or cfg.backend.base_url)


def summarize_profile(cells: pd.DataFrame, sweep: pd.DataFrame, rs: RateSweep | None) -> dict:
    out: dict[str, Any] = {}
    if len(cells):
        out["cell_status_counts"] = cells["status"].value_counts().to_dict()
        ok = cells[cells["status"] == "ok"]
        if len(ok):
            g = ok.groupby(["prompt_tokens", "max_tokens", "concurrency"])["output_tok_per_s"]
            out["max_output_tok_per_s_by_shape"] = {
                f"p{p}-o{o}": float(v) for (p, o), v in
                ok.groupby(["prompt_tokens", "max_tokens"])["output_tok_per_s"].max().items()
            }
            out["n_trials_per_cell_min"] = int(g.count().min())
            if "preemptions" in ok:
                pre = ok[ok["preemptions"].fillna(0) > 0]
                out["cells_with_preemption"] = pre[["prompt_tokens", "max_tokens", "concurrency"]].drop_duplicates().to_dict("records")
    if rs is not None and len(sweep) and "completed_rps" in sweep:
        # completed_rps = completions with terminal time inside the arrival window / window length
        okr = sweep[sweep["status"] == "ok"]
        agg = okr.groupby("rate_rps").agg(completed_rps=("completed_rps", "mean"), offered_rps=("offered_rps", "mean"),
                                          ttft_p95_ms=("ttft_p95_ms", "mean"), success=("success_fraction", "mean"),
                                          trials=("trial", "count")).reset_index()
        feasible = agg[(agg["completed_rps"] >= rs.knee_completion_ratio * agg["offered_rps"]) &
                       (agg["ttft_p95_ms"] <= rs.ttft_deadline_ms)]
        out["rate_sweep"] = agg.to_dict("records")
        out["estimated_saturation_knee_rps"] = float(feasible["rate_rps"].max()) if len(feasible) else None
        out["knee_rule"] = (f"max offered rate with mean completed_rps >= {rs.knee_completion_ratio} x offered "
                            f"and mean p95 TTFT <= {rs.ttft_deadline_ms} ms (provisional)")
        out["controlled_saturation_observed"] = bool(len(feasible) and len(feasible) < len(agg))
    return out
