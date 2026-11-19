"""risksched command-line interface.

    python -m risksched.cli doctor
    python -m risksched.cli validate-env [--backend-url URL]
    python -m risksched.cli generate-workload --config configs/tenants/three_tenants.yaml --seed 11
    python -m risksched.cli run --config configs/experiments/smoke.yaml --scheduler fcfs --seed 11
    python -m risksched.cli profile --config configs/experiments/e0_smoke.yaml --backend mock
    python -m risksched.cli report --run-dir results/<exp>/<run>
    python -m risksched.cli compare --experiment smoke
    python -m risksched.cli mock-server --port 8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_doctor(_: argparse.Namespace) -> int:
    from risksched.instrumentation.gpu import GpuSampler
    from risksched.instrumentation.provenance import git_info, package_versions

    tools = {}
    for t in ("terraform", "docker", "aws", "nvidia-smi", "uv", "git"):
        path = shutil.which(t)
        ver = None
        if path:
            try:
                ver = subprocess.run([t, "--version"], capture_output=True, text=True, timeout=10).stdout.splitlines()[0]
            except Exception:  # noqa: BLE001
                ver = "unknown"
        tools[t] = {"path": path, "version": ver}
    _print({
        "python": sys.version,
        "packages": package_versions(),
        "git": git_info(REPO),
        "tools": tools,
        "gpu": GpuSampler().static_info(),
        "notes": [
            "No AWS API calls are made by doctor.",
            "Real-GPU E0 requires an NVIDIA GPU host running a pinned vLLM server (see docs/REPRODUCIBILITY.md).",
        ],
    })
    return 0


def cmd_validate_env(a: argparse.Namespace) -> int:
    from risksched.serving.openai_backend import OpenAICompatBackend

    ok = True
    checks = {}
    for f in ("configs/tenants/three_tenants.yaml", "configs/experiments/smoke.yaml", "configs/experiments/e0.yaml"):
        checks[f] = (REPO / f).exists()
        ok &= checks[f]
    from risksched.config import load_experiment, load_workload
    from risksched.profiling.e0 import load_profile_config

    try:
        load_workload(REPO / "configs/tenants/three_tenants.yaml")
        load_experiment(REPO / "configs/experiments/smoke.yaml")
        load_profile_config(REPO / "configs/experiments/e0.yaml")
        load_profile_config(REPO / "configs/experiments/e0_smoke.yaml")
        checks["config_schema_validation"] = True
    except Exception as e:  # noqa: BLE001
        checks["config_schema_validation"] = f"FAILED: {e}"
        ok = False
    if a.backend_url:
        async def probe():
            be = OpenAICompatBackend(a.backend_url, a.model or "unknown")
            try:
                info = await be.info()
                snap = await be.scrape_metrics()
                return info, (snap.resolved_names if snap else None), (snap.missing if snap else None)
            finally:
                await be.aclose()
        info, names, missing = asyncio.run(probe())
        checks["backend_info"] = info
        checks["resolved_metric_names"] = names
        checks["missing_metrics"] = missing
        ok &= names is not None
    _print({"ok": ok, "checks": checks})
    return 0 if ok else 1


def cmd_generate_workload(a: argparse.Namespace) -> int:
    from risksched.config import load_workload
    from risksched.workload.generator import generate_trace, write_trace_jsonl

    wl = load_workload(Path(a.config))
    items = generate_trace(wl, a.seed)
    out = Path(a.out) if a.out else REPO / "results" / "traces" / f"{wl.workload_id}_s{a.seed}.jsonl"
    h = write_trace_jsonl(items, out)
    per = {}
    for it in items:
        per[it.request.tenant_id] = per.get(it.request.tenant_id, 0) + 1
    _print({"trace": str(out), "sha256": h, "n_requests": len(items), "per_tenant": per,
            "note": "synthetic-template prompts: token-trace simulation, not semantic replay"})
    return 0


def cmd_run(a: argparse.Namespace) -> int:
    from risksched.config import load_experiment
    from risksched.evaluation.plots import plot_run
    from risksched.runtime.runner import run_experiment

    cfg_path = Path(a.config)
    cfg = load_experiment(cfg_path)
    if a.backend:
        cfg = cfg.model_copy(update={"backend": cfg.backend.model_copy(update={"kind": a.backend})})
    out = run_experiment(cfg, a.scheduler, a.seed, Path(a.results_root), config_base=REPO, base_url_override=a.backend_url)
    plot_run(out)
    s = json.loads((out / "metrics_summary.json").read_text())
    _print({"run_dir": str(out), "offered": s.get("offered"), "status_counts": s.get("status_counts"),
            "accounting_conserved": s.get("accounting_conserved"), "event_validation_ok": s.get("event_validation_ok"),
            "slo_goodput_rps": s.get("slo_goodput_rps"), "worst_tenant_slo_attainment": s.get("worst_tenant_slo_attainment"),
            "synthetic_backend": s.get("synthetic_backend")})
    return 0 if s.get("accounting_conserved") and s.get("event_validation_ok") else 2


def cmd_profile(a: argparse.Namespace) -> int:
    from risksched.profiling.e0 import load_profile_config, run_profile

    cfg = load_profile_config(Path(a.config))
    if a.backend:
        cfg = cfg.model_copy(update={"backend": cfg.backend.model_copy(update={"kind": a.backend})})
    if cfg.backend.kind == "vllm" and not a.i_understand_gpu_costs:
        print("Refusing: real-GPU profiling needs --i-understand-gpu-costs (and an approved, running vLLM endpoint).",
              file=sys.stderr)
        return 3
    out = run_profile(cfg, a.seed, Path(a.results_root), base_url_override=a.backend_url,
                      only_rate_sweep=a.only_rate_sweep, skip_rate_sweep=a.skip_rate_sweep)
    s = json.loads((out / "summary.json").read_text())
    _print({"run_dir": str(out), **{k: s.get(k) for k in ("cell_status_counts", "estimated_saturation_knee_rps",
                                                           "controlled_saturation_observed", "synthetic_backend")}})
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    import pandas as pd

    from risksched.evaluation.plots import plot_e0, plot_run
    from risksched.instrumentation.recorder import validate_events
    from risksched.schema import RequestEvent

    d = Path(a.run_dir)
    if (d / "cells.parquet").exists():
        figs = plot_e0(d)
        _print({"figures": [str(f) for f in figs], "summary": json.loads((d / "summary.json").read_text())})
        return 0
    ev = pd.read_parquet(d / "events.parquet")
    ev = ev.astype(object).where(ev.notna(), None)  # parquet NaN -> None for nullable fields
    rq = pd.read_parquet(d / "requests.parquet")
    events = [RequestEvent.model_validate(r) for r in ev.to_dict("records")]
    errs = validate_events(events, set(rq["request_id"]))
    figs = plot_run(d)
    s = json.loads((d / "metrics_summary.json").read_text())
    _print({"run_dir": str(d), "revalidated_event_errors": len(errs), "figures": [str(f) for f in figs],
            "summary": {k: s[k] for k in ("offered", "status_counts", "slo_goodput_rps", "offered_success_fraction",
                                          "worst_tenant_slo_attainment", "jain_slo_attainment", "synthetic_backend")}})
    return 0 if not errs else 2


def cmd_compare(a: argparse.Namespace) -> int:
    import pandas as pd

    root = Path(a.results_root) / a.experiment
    rows = []
    for s in sorted(root.glob("*/metrics_summary.json")):
        j = json.loads(s.read_text())
        rows.append({"run": s.parent.name, "scheduler": j.get("scheduler", {}).get("name"),
                     "offered": j.get("offered"), "slo_goodput_rps": j.get("slo_goodput_rps"),
                     "offered_success_fraction": j.get("offered_success_fraction"),
                     "worst_tenant_slo_attainment": j.get("worst_tenant_slo_attainment"),
                     "ttft_p95_ms": (j.get("ttft_ms") or {}).get("p95"),
                     "synthetic": j.get("synthetic_backend")})
    if not rows:
        print(f"no runs under {root}", file=sys.stderr)
        return 1
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print("\nNOTE: descriptive per-run table only; no inferential statistics (Milestone 2+ adds paired bootstrap CIs).")
    return 0


def cmd_mock_server(a: argparse.Namespace) -> int:
    import uvicorn

    from risksched.serving.engine_model import EngineParams
    from risksched.serving.mock_server import MockVLLM, build_app

    params = EngineParams(max_model_len=a.max_model_len)
    uvicorn.run(build_app(MockVLLM(params, model_name=a.model)), host=a.host, port=a.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="risksched")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    v = sub.add_parser("validate-env")
    v.add_argument("--backend-url")
    v.add_argument("--model")
    v.set_defaults(fn=cmd_validate_env)
    g = sub.add_parser("generate-workload")
    g.add_argument("--config", required=True)
    g.add_argument("--seed", type=int, required=True)
    g.add_argument("--out")
    g.set_defaults(fn=cmd_generate_workload)
    for name, fn in (("run", cmd_run), ("profile", cmd_profile)):
        r = sub.add_parser(name)
        r.add_argument("--config", required=True)
        r.add_argument("--seed", type=int, default=11)
        r.add_argument("--backend", choices=["mock", "mock_http", "vllm"])
        r.add_argument("--backend-url")
        r.add_argument("--results-root", default=str(REPO / "results"))
        if name == "run":
            r.add_argument("--scheduler", default="fcfs")
        else:
            r.add_argument("--i-understand-gpu-costs", action="store_true")
            r.add_argument("--only-rate-sweep", action="store_true")
            r.add_argument("--skip-rate-sweep", action="store_true")
        r.set_defaults(fn=fn)
    rp = sub.add_parser("report")
    rp.add_argument("--run-dir", required=True)
    rp.set_defaults(fn=cmd_report)
    c = sub.add_parser("compare")
    c.add_argument("--experiment", required=True)
    c.add_argument("--results-root", default=str(REPO / "results"))
    c.set_defaults(fn=cmd_compare)
    m = sub.add_parser("mock-server")
    m.add_argument("--host", default="127.0.0.1")
    m.add_argument("--port", type=int, default=8000)
    m.add_argument("--model", default="mock-model")
    m.add_argument("--max-model-len", type=int, default=8192)
    m.set_defaults(fn=cmd_mock_server)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
