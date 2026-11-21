"""Experiment orchestration: build gateway/backend, run, persist results.

Output layout: results/<experiment>/<timestamp>_<scheduler>_<seed>/
  manifest.json, config.resolved.yaml, trace.jsonl, requests.parquet,
  events.parquet, metrics_timeseries.parquet, metrics_summary.json, logs/
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import threading
import time
from pathlib import Path

import pandas as pd
import yaml

from quotashift.config import BackendConfig, ExperimentConfig
from quotashift.evaluation.metrics import summarize
from quotashift.gateway.core import Gateway
from quotashift.gateway.ledger import TokenLedger
from quotashift.instrumentation.engine_counters import cost_accounting, counter_deltas, engine_state
from quotashift.instrumentation.gpu import GpuSampler
from quotashift.instrumentation.provenance import build_manifest
from quotashift.instrumentation.recorder import RunRecorder, validate_events
from quotashift.runtime.clients import OpenLoopClient
from quotashift.runtime.live import LiveConfig, run_live
from quotashift.runtime.sim import SimConfig, run_simulation
from quotashift.schedulers.simple import make_policy
from quotashift.serving.engine_model import EngineModel
from quotashift.serving.openai_backend import OpenAICompatBackend
from quotashift.workload.generator import generate_trace, write_trace_jsonl

REPO = Path(__file__).resolve().parents[3]


class SafetyError(RuntimeError):
    pass


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


# ------------------------------------------------------------------ mock HTTP server helper


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def local_mock_server(bcfg: BackendConfig):
    """Start the mock vLLM server on 127.0.0.1 in a background thread."""
    import uvicorn

    from quotashift.serving.mock_server import MockVLLM, build_app

    port = _free_port()
    holder: dict = {}

    def target() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        mock = MockVLLM(bcfg.engine, time_scale=bcfg.time_scale, model_name=bcfg.model)
        server = uvicorn.Server(uvicorn.Config(build_app(mock), host="127.0.0.1", port=port, log_level="warning",
                                               loop="asyncio", lifespan="on"))
        holder["server"] = server
        try:
            loop.run_until_complete(server.serve())
        finally:
            loop.close()

    th = threading.Thread(target=target, daemon=True)
    th.start()
    deadline = time.time() + 15
    while time.time() < deadline:
        srv = holder.get("server")
        if srv is not None and srv.started:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("mock server failed to start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        holder["server"].should_exit = True
        th.join(timeout=10)


def make_backend(bcfg: BackendConfig, base_url: str) -> OpenAICompatBackend:
    return OpenAICompatBackend(
        base_url=base_url,
        model=bcfg.model,
        sampling=dict(bcfg.sampling),
        ignore_eos=bcfg.ignore_eos,
        send_mock_oracle_header=bcfg.is_mock,  # never for real vLLM
    )


# ------------------------------------------------------------------ persistence


def write_results(out_dir: Path, recorder: RunRecorder, timeseries: list[dict], manifest: dict,
                  cfg_resolved: dict, summary: dict, extra_logs: dict | None = None) -> None:
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)
    (out_dir / "figures").mkdir(exist_ok=True)
    pd.DataFrame(list(recorder.rows.values())).to_parquet(out_dir / "requests.parquet", index=False)
    pd.DataFrame([e.model_dump(mode="json") for e in recorder.events]).to_parquet(out_dir / "events.parquet", index=False)
    pd.DataFrame(timeseries).to_parquet(out_dir / "metrics_timeseries.parquet", index=False)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    (out_dir / "config.resolved.yaml").write_text(yaml.safe_dump(cfg_resolved, sort_keys=False))
    (out_dir / "metrics_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    for name, content in (extra_logs or {}).items():
        (out_dir / "logs" / name).write_text(content)


# ------------------------------------------------------------------ main entry


def run_experiment(cfg: ExperimentConfig, scheduler: str, seed: int, results_root: Path,
                   config_base: Path, base_url_override: str | None = None,
                   trace_override: list | None = None, lifecycle_plans: dict | None = None) -> Path:
    if scheduler not in cfg.schedulers:
        raise KeyError(f"scheduler {scheduler!r} not configured in experiment (have {sorted(cfg.schedulers)})")
    wl = cfg.resolved_workload(config_base)
    # trace_override: a pre-compiled schedule (e.g. a phased QuotaShift scenario) whose
    # arrivals cannot be expressed as a single per-tenant profile. Metadata/weights/
    # duration still come from `wl`.
    items = trace_override if trace_override is not None else generate_trace(wl, seed)
    if len(items) > cfg.run.max_requests_cap:
        raise SafetyError(f"trace has {len(items)} requests > max_requests_cap={cfg.run.max_requests_cap}")
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    run_id = f"{ts}_{scheduler}_{seed}"
    out_dir = results_root / cfg.experiment_id / run_id
    out_dir.mkdir(parents=True, exist_ok=False)
    trace_sha = write_trace_jsonl(items, out_dir / "trace.jsonl")

    clock = "virtual" if cfg.backend.kind == "mock" else "monotonic"
    recorder = RunRecorder(cfg.experiment_id, run_id, clock=clock)
    tenants = [t.tenant_id for t in wl.tenants]
    ledger = TokenLedger(dict(cfg.gateway.ledger.quotas), cfg.gateway.ledger.allow_borrow) if cfg.gateway.ledger else None
    policy = make_policy(scheduler, **cfg.schedulers[scheduler])
    g = cfg.gateway
    gw = Gateway(policy, tenants, recorder, ledger=ledger, max_queue_wait_s=g.max_queue_wait_s,
                 tenant_weights={t.tenant_id: t.priority_weight for t in wl.tenants},
                 rate_limiter=g.rate_limits.build(tenants) if g.rate_limits else None,
                 max_queue_per_tenant=g.max_queue_per_tenant, max_queue_total=g.max_queue_total)
    b = cfg.backend
    gpu = GpuSampler(source=b.gpu_source, exporter_url=b.gpu_exporter_url, smi_prefix=b.gpu_smi_prefix)
    gpu_info = gpu.static_info() | {"gpu_type": b.gpu_type}
    engine_before = engine_after = None
    end_time = wl.duration_s + cfg.run.drain_s
    if lifecycle_plans and cfg.backend.kind == "mock":
        raise SafetyError("lifecycle plans (cancel/timeout/retry) need an HTTP backend (mock_http or vllm); "
                          "the in-process simulator cannot cancel streams")
    if lifecycle_plans:
        from quotashift.workload.lifecycle import LifecycleClient

        client = LifecycleClient(items, lifecycle_plans, recorder.state)
    else:
        client = OpenLoopClient(items)
    idle_power: float | None = None
    idle_baseline: dict | None = None
    gpu_tail: dict | None = None
    engine_drain_s: float | None = None
    engine_end_state: dict | None = None
    backend_info = None
    t_wall0 = time.time()

    if cfg.backend.kind == "mock":
        engine = EngineModel(cfg.backend.engine)
        timeseries = run_simulation(client, gw, engine, SimConfig(
            end_time_s=end_time, metrics_interval_s=cfg.run.metrics_interval_s,
            request_timeout_s=cfg.run.request_timeout_s))
        backend_info = {"engine_params": cfg.backend.engine.model_dump()}
    else:
        if end_time * (cfg.backend.time_scale if cfg.backend.kind == "mock_http" else 1.0) > cfg.run.max_experiment_seconds:
            raise SafetyError("planned run exceeds max_experiment_seconds")
        live_cfg = LiveConfig(end_time_s=end_time, metrics_interval_s=cfg.run.metrics_interval_s,
                              request_timeout_s=cfg.run.request_timeout_s,
                              max_concurrency_cap=cfg.run.max_concurrency_cap)

        async def go(url: str):
            nonlocal engine_before, engine_after, idle_power, idle_baseline, gpu_tail, engine_drain_s, \
                engine_end_state
            be = make_backend(cfg.backend, url)
            try:
                info = await be.info()
                if gpu.available:  # settled idle board power right before the arm (for dynamic energy)
                    from quotashift.instrumentation.gpu import settle_idle_power

                    idle_baseline = await settle_idle_power(gpu)
                    idle_power = idle_baseline["idle_power_w"]
                engine_before = await be.scrape_metrics()  # per-arm before/after counter snapshots
                ts_rows = await run_live(client, gw, be, live_cfg, gpu=gpu)
                # engine-side cleanup: wait (bounded) until vLLM reports nothing running/waiting
                t_end, t0d = time.monotonic() + 10.0, time.monotonic()
                snap = await be.scrape_metrics()
                while snap is not None and time.monotonic() < t_end and (
                        (snap.values.get("num_requests_running") or 0) > 0
                        or (snap.values.get("num_requests_waiting") or 0) > 0):
                    await asyncio.sleep(0.25)
                    snap = await be.scrape_metrics()
                engine_drain_s = time.monotonic() - t0d
                engine_after = snap
                engine_end_state = engine_state(snap)
                if gpu.available and idle_power is not None:
                    # post-arm tail: the GPU keeps load clocks (~130 W on the 3090) for ~16 s after work ends;
                    # that energy is caused by this arm but falls outside the arm window. Bounded wait (90 s).
                    from quotashift.instrumentation.gpu import settle_idle_power

                    gpu_tail = await settle_idle_power(gpu)
                return info, ts_rows
            finally:
                await be.aclose()

        if cfg.backend.kind == "mock_http" and not (base_url_override or cfg.backend.base_url):
            if cfg.backend.time_scale != 1.0:
                raise SafetyError("live mock_http runs require time_scale=1.0 so recorded latencies are in real seconds")
            with local_mock_server(cfg.backend) as url:
                backend_info, timeseries = asyncio.run(go(url))
        else:
            backend_info, timeseries = asyncio.run(go(base_url_override or cfg.backend.base_url))

    errs = validate_events(recorder.events, set(recorder.rows))
    df = pd.DataFrame(list(recorder.rows.values()))
    summary = summarize(df, window_s=wl.duration_s, warmup_s=cfg.run.warmup_s) if len(df) else {"offered": 0}
    summary["event_validation_errors"] = errs[:50]
    summary["event_validation_ok"] = not errs
    summary["lifecycle_violations"] = recorder.violations[:50]
    summary["wall_seconds"] = time.time() - t_wall0
    summary["scheduler"] = policy.describe()
    summary["synthetic_backend"] = cfg.backend.is_mock
    summary["path"] = cfg.path
    if cfg.backend.kind != "mock":
        done = df[df["terminal_status"] == "completed"] if len(df) else df
        cp = int(_num(done["prompt_tokens_reported"]).sum()) if len(df) else 0
        cg = int(_num(done["output_tokens"]).sum()) if len(df) else 0
        # requests that reached the engine but did not complete report no usage: bound their work
        nc = df[df["t_sent"].notna() & (df["terminal_status"] != "completed")] if len(df) else df
        p_up: float | None = 0.0
        g_up: float | None = 0.0
        if len(nc):
            planned_done = float(done["input_token_count"].sum()) if len(done) else 0.0
            ratio = (cp / planned_done) if planned_done > 0 else None  # real tokens per planned (whitespace) token
            p_up = None if ratio is None else 1.25 * ratio * float(nc["input_token_count"].sum())
            g_up = float(nc["max_output_tokens"].sum())  # cannot exceed the requested cap
        summary["engine_counters"] = counter_deltas(engine_before, engine_after,
                                                    client_prompt_tokens=cp, client_generation_tokens=cg,
                                                    noncompleted_prompt_upper=p_up, noncompleted_generation_upper=g_up)
    rows_df = df if len(df) else pd.DataFrame(columns=["workload_class", "input_token_count", "max_output_tokens"])
    auth = int((rows_df["input_token_count"] + rows_df["max_output_tokens"]).sum()) if len(df) else 0
    comp_auth = int((rows_df.loc[rows_df["workload_class"] == "competitor", "input_token_count"]
                     + rows_df.loc[rows_df["workload_class"] == "competitor", "max_output_tokens"]).sum()) if len(df) else 0
    summary["cost_accounting"] = cost_accounting(timeseries if cfg.backend.kind != "mock" else [],
                                                 idle_power_w=idle_power, authorized_tokens=auth,
                                                 competitor_authorized_tokens=comp_auth)
    from quotashift.instrumentation.gpu import trapezoid_j

    ca = summary["cost_accounting"]
    ca["gpu_idle_baseline"] = {k: v for k, v in (idle_baseline or {}).items() if k != "series"} or None
    if gpu_tail is not None and idle_power is not None:
        ser = gpu_tail.get("series") or []
        e_tail = trapezoid_j(ser)
        span = (ser[-1][0] - ser[0][0]) if len(ser) >= 2 else 0.0
        ca["gpu_tail"] = {k: v for k, v in gpu_tail.items() if k not in ("series", "idle_power_w")} | {
            "energy_j": e_tail, "dynamic_energy_j": (e_tail - idle_power * span) if e_tail is not None else None,
            "span_s": span, "note": "after the arm's engine drain until the GPU is idle again; secondary"}
        dyn = ca.get("gpu_dynamic_energy_j")
        tail_dyn = ca["gpu_tail"]["dynamic_energy_j"]
        ca["gpu_dynamic_energy_with_tail_j"] = (dyn + tail_dyn) if dyn is not None and tail_dyn is not None else None
    from quotashift.evaluation.cache_hits import cached_token_summary

    summary["cached_tokens"] = cached_token_summary(df)  # per-request prefix hits, per tenant/class, with coverage
    if cfg.backend.kind != "mock":
        from quotashift.evaluation.cache_hits import engine_reconciliation

        summary["cached_tokens"]["engine_reconciliation"] = engine_reconciliation(
            summary["cached_tokens"], df, summary.get("engine_counters"))
    cutoff = int((df["terminal_detail"] == "run_cutoff").sum()) if len(df) else 0
    end_running = (engine_end_state or {}).get("num_requests_running")
    checks = {
        "ledger_reserved_at_end": ledger.total_reserved if ledger is not None else 0,
        "rate_limit_reservations_at_end": len(gw.rate_limiter.reserved) if gw.rate_limiter else 0,
        "gateway_inflight_at_end": len(gw.inflight), "gateway_queued_at_end": gw.queued_count,
        "run_cutoff_cancellations": cutoff,
        "engine_running_after_drain": end_running, "engine_drain_s": engine_drain_s,
        "lifecycle_violations": len(recorder.violations),
    }
    checks["leak_detected"] = bool(checks["ledger_reserved_at_end"] or checks["rate_limit_reservations_at_end"]
                                   or checks["gateway_inflight_at_end"] or checks["gateway_queued_at_end"]
                                   or checks["lifecycle_violations"] or (end_running or 0) > 0)
    summary["cleanup_checks"] = checks
    if lifecycle_plans:
        acts: dict[str, int] = {}
        for pl in lifecycle_plans.values():
            acts[pl.action] = acts.get(pl.action, 0) + 1
        cc = pd.to_numeric(df["cancel_close_s"], errors="coerce").dropna() if "cancel_close_s" in df else pd.Series(dtype=float)
        summary["lifecycle"] = {
            "planned_actions": acts, "retries_fired": getattr(client, "retries_fired", 0),
            "retries_not_needed": getattr(client, "retries_not_needed", 0),
            "cancel_close_s_p50": float(cc.quantile(0.5)) if len(cc) else None,
            "cancel_close_s_p95": float(cc.quantile(0.95)) if len(cc) else None,
            "terminal_detail_counts": df["terminal_detail"].fillna("none").value_counts().to_dict() if len(df) else {},
        }
    summary["actual_counts"] = {
        "requests_offered": int(len(df)),
        "requests_completed": int((df["terminal_status"] == "completed").sum()) if len(df) else 0,
        "prompt_tokens_reported": int(_num(df["prompt_tokens_reported"]).sum()) if len(df) else 0,
        "output_tokens": int(_num(df["output_tokens"]).sum()) if len(df) else 0,
        "requested_input_tokens": int(df["input_token_count"].sum()) if len(df) else 0,
        "requested_max_output_tokens": int(df["max_output_tokens"].sum()) if len(df) else 0,
    }
    cfg_resolved = cfg.model_dump(mode="json") | {"workload": wl.model_dump(mode="json")}
    manifest = build_manifest(repo=REPO, experiment_id=cfg.experiment_id, run_id=run_id, scheduler=policy.describe(),
                              seed=seed, config_resolved=cfg_resolved, backend_kind=cfg.backend.kind,
                              backend_info=backend_info, trace_sha256=trace_sha, clock=clock, gpu_info=gpu_info)
    ec = summary.get("engine_counters") or {}
    manifest["run_context"] = {
        "path": cfg.path,
        "admission_policy": policy.describe(),
        "rate_limits": g.rate_limits.model_dump() if g.rate_limits else None,
        "queue_caps": {"per_tenant": g.max_queue_per_tenant, "total": g.max_queue_total,
                       "max_queue_wait_s": g.max_queue_wait_s},
        "backend_identity": {"kind": cfg.backend.kind, "base_url": base_url_override or cfg.backend.base_url,
                             "model": cfg.backend.model, "model_revision": cfg.backend.model_revision,
                             "vllm_version": (backend_info or {}).get("/version")},
        "gpu_type": b.gpu_type,
        "prefix_caching_enabled": (ec.get("engine_state_at_start") or {}).get("prefix_caching_enabled"),
        "cache_config_info": (ec.get("engine_state_at_start") or {}).get("cache_config_info"),
        "unrelated_traffic_suspected": ec.get("unrelated_traffic_suspected"),
        "actual_counts": summary["actual_counts"],
    }
    write_results(out_dir, recorder, timeseries, manifest, cfg_resolved, summary)
    return out_dir
