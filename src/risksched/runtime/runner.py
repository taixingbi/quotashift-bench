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

from risksched.config import BackendConfig, ExperimentConfig
from risksched.evaluation.metrics import summarize
from risksched.gateway.core import Gateway
from risksched.gateway.ledger import TokenLedger
from risksched.instrumentation.gpu import GpuSampler
from risksched.instrumentation.provenance import build_manifest
from risksched.instrumentation.recorder import RunRecorder, validate_events
from risksched.runtime.clients import OpenLoopClient
from risksched.runtime.live import LiveConfig, run_live
from risksched.runtime.sim import SimConfig, run_simulation
from risksched.schedulers.simple import make_policy
from risksched.serving.engine_model import EngineModel
from risksched.serving.openai_backend import OpenAICompatBackend
from risksched.workload.generator import generate_trace, write_trace_jsonl

REPO = Path(__file__).resolve().parents[3]


class SafetyError(RuntimeError):
    pass


# ------------------------------------------------------------------ mock HTTP server helper


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def local_mock_server(bcfg: BackendConfig):
    """Start the mock vLLM server on 127.0.0.1 in a background thread."""
    import uvicorn

    from risksched.serving.mock_server import MockVLLM, build_app

    port = _free_port()
    holder: dict = {}

    def target() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        mock = MockVLLM(bcfg.engine, time_scale=bcfg.time_scale, model_name=bcfg.model)
        server = uvicorn.Server(uvicorn.Config(build_app(mock), host="127.0.0.1", port=port, log_level="warning",
                                               loop="asyncio", lifespan="on"))
        holder["server"] = server
        loop.run_until_complete(server.serve())

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
                   config_base: Path, base_url_override: str | None = None) -> Path:
    if scheduler not in cfg.schedulers:
        raise KeyError(f"scheduler {scheduler!r} not configured in experiment (have {sorted(cfg.schedulers)})")
    wl = cfg.resolved_workload(config_base)
    items = generate_trace(wl, seed)
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
    gw = Gateway(policy, tenants, recorder, ledger=ledger, max_queue_wait_s=cfg.gateway.max_queue_wait_s,
                 tenant_weights={t.tenant_id: t.priority_weight for t in wl.tenants})
    end_time = wl.duration_s + cfg.run.drain_s
    client = OpenLoopClient(items)
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
            be = make_backend(cfg.backend, url)
            try:
                info = await be.info()
                ts_rows = await run_live(client, gw, be, live_cfg, gpu=GpuSampler())
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
    cfg_resolved = cfg.model_dump(mode="json") | {"workload": wl.model_dump(mode="json")}
    manifest = build_manifest(repo=REPO, experiment_id=cfg.experiment_id, run_id=run_id, scheduler=policy.describe(),
                              seed=seed, config_resolved=cfg_resolved, backend_kind=cfg.backend.kind,
                              backend_info=backend_info, trace_sha256=trace_sha, clock=clock)
    write_results(out_dir, recorder, timeseries, manifest, cfg_resolved, summary)
    return out_dir
