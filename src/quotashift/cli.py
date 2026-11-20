"""quotashift command-line interface.

    python -m quotashift.cli doctor
    python -m quotashift.cli validate experiments/smoke.yaml
    python -m quotashift.cli dry-run experiments/stateful_sequences.yaml [--control]
    python -m quotashift.cli run-local experiments/smoke.yaml --mock
    python -m quotashift.cli target {list,show,use <aws|selfhost>,check}
    python -m quotashift.cli run-local experiments/smoke.yaml --live   # active target (selfhost only)
    python -m quotashift.cli summarize --input results/ --output reports/
    python -m quotashift.cli mock-server --port 8000

Attack-only, in-lab workload characterization. No external targets; mock results
are simulator plumbing (`synthetic_backend: true`), never GPU measurements.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() or p.exists() else (REPO / p)


# ---------------------------------------------------------------- doctor


def cmd_doctor(_: argparse.Namespace) -> int:
    from quotashift.instrumentation.gpu import GpuSampler
    from quotashift.instrumentation.provenance import git_info, package_versions

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
            "QuotaShift is attack-side characterization only; mock runs are not GPU measurements.",
        ],
    })
    return 0


# ---------------------------------------------------------------- validate / dry-run


def cmd_validate(a: argparse.Namespace) -> int:
    from quotashift.scenario import load_scenario

    try:
        sc = load_scenario(_resolve(a.config))
    except (ValidationError, ValueError) as e:
        print(f"INVALID: {a.config}\n{e}", file=sys.stderr)
        return 2
    _print({"valid": True, "scenario_id": sc.scenario_id, "model": sc.model,
            "victims": sc.victim_tenants, "competitors": sc.competing_tenants,
            "runtime_s": sc.runtime_seconds, "phases": [p.name for p in sc.phases],
            "schedule_sha256": sc.schedule_hash(),
            "safety": sc.safety.model_dump()})
    return 0


def cmd_dry_run(a: argparse.Namespace) -> int:
    from quotashift.scenario import load_scenario

    try:
        sc = load_scenario(_resolve(a.config))
    except (ValidationError, ValueError) as e:
        print(f"INVALID: {a.config}\n{e}", file=sys.stderr)
        return 2
    order = None
    if a.control and sc.phases:
        order = [p.name for p in reversed(sc.phases)]  # deterministic shuffled-phase control
    items = sc.build_trace(phase_order=order)
    per_tenant: dict[str, dict] = {}
    for it in items:
        r = it.request
        d = per_tenant.setdefault(r.tenant_id, {"requests": 0, "input_tokens": 0, "requested_output_tokens": 0})
        d["requests"] += 1
        d["input_tokens"] += r.input_token_count
        d["requested_output_tokens"] += r.max_output_tokens
    _print({
        "scenario_id": sc.scenario_id,
        "phase_order": order or [p.name for p in sc.phases],
        "total_requests": len(items),
        "schedule_sha256": sc.schedule_hash(phase_order=order),
        "per_tenant": per_tenant,
        "note": "DRY RUN: nothing sent. Synthetic schedule only.",
    })
    return 0


# ---------------------------------------------------------------- run-local


def cmd_run_local(a: argparse.Namespace) -> int:
    from quotashift.local import run_scenario_local
    from quotashift.scenario import load_scenario
    from quotashift.targets import active_target, load_target

    if a.mock == a.live:
        print("run-local requires exactly one of --mock or --live.", file=sys.stderr)
        return 3
    target = None
    if a.live:
        target = load_target(a.target) if a.target else active_target()
        if target.kind == "aws":
            # AWS runs go through the approval-gated generator task (scripts/aws_ops.sh).
            print("run-local --live supports self-hosted targets only; AWS runs use scripts/aws_ops.sh.",
                  file=sys.stderr)
            return 3
    sc = load_scenario(_resolve(a.config))
    out = run_scenario_local(sc, Path(a.results_root), phase_order=None, target=target)
    s = json.loads((out / "metrics_summary.json").read_text())
    _print({"run_dir": str(out), "offered": s.get("offered"), "status_counts": s.get("status_counts"),
            "accounting_conserved": s.get("accounting_conserved"), "event_validation_ok": s.get("event_validation_ok"),
            "worst_tenant_slo_attainment": s.get("worst_tenant_slo_attainment"),
            "synthetic_backend": s.get("synthetic_backend"),
            "target": target.name if target else "mock"})
    return 0 if s.get("accounting_conserved") and s.get("event_validation_ok") else 2


# ---------------------------------------------------------------- target


def cmd_target(a: argparse.Namespace) -> int:
    from quotashift import targets as T

    try:
        if a.action == "list":
            _print({"targets": T.list_targets(), "active": T.active_target_name()})
        elif a.action == "use":
            if not a.name:
                print("usage: quotashift target use <name>", file=sys.stderr)
                return 2
            prof = T.set_active(a.name)
            _print({"active": prof.name, **prof.model_dump()})
        else:
            prof = T.load_target(a.name) if a.name else T.active_target()
            out: dict = {"active": T.active_target_name(), "target": prof.model_dump()}
            if a.action == "check":
                out["check"] = T.check_target(prof)
                _print(out)
                return 0 if out["check"].get("ok") else 1
            _print(out)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    return 0


# ---------------------------------------------------------------- summarize


def cmd_summarize(a: argparse.Namespace) -> int:
    import csv

    root = _resolve(a.input)
    out_dir = Path(a.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for sj in sorted(root.rglob("metrics_summary.json")):
        s = json.loads(sj.read_text())
        run = sj.parent.name
        scenario = sj.parent.parent.name
        for tenant, pt in (s.get("per_tenant") or {}).items():
            rows.append({
                "scenario": scenario, "run": run, "tenant": tenant,
                "offered": pt.get("offered"), "slo_met": pt.get("slo_met"),
                "slo_attainment": pt.get("slo_attainment"),
                "ttft_p95_ms": pt.get("ttft_p95_ms"), "tpot_p95_ms": pt.get("tpot_p95_ms"),
                "service_tokens": pt.get("service_tokens"),
                "synthetic_backend": s.get("synthetic_backend"),
            })
    if not rows:
        print(f"no metrics_summary.json under {root}", file=sys.stderr)
        return 1
    csv_path = out_dir / "summary.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    md = ["# QuotaShift summary", "",
          "Per-tenant outcomes across runs. Mock runs are simulator outputs, not GPU measurements.", "",
          "| scenario | run | tenant | offered | slo_attainment | ttft_p95_ms | service_tokens |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['scenario']} | {r['run']} | {r['tenant']} | {r['offered']} | "
                  f"{r['slo_attainment']} | {r['ttft_p95_ms']} | {r['service_tokens']} |")
    (out_dir / "summary.md").write_text("\n".join(md) + "\n")
    _print({"rows": len(rows), "csv": str(csv_path), "md": str(out_dir / "summary.md")})
    return 0


# ---------------------------------------------------------------- mock-server


def cmd_mock_server(a: argparse.Namespace) -> int:
    import uvicorn

    from quotashift.serving.engine_model import EngineParams
    from quotashift.serving.mock_server import MockVLLM, build_app

    params = EngineParams(max_model_len=a.max_model_len)
    uvicorn.run(build_app(MockVLLM(params, model_name=a.model)), host=a.host, port=a.port, log_level="warning")
    return 0


# ---------------------------------------------------------------- argparse


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="quotashift")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)

    for name, fn in (("validate", cmd_validate), ("dry-run", cmd_dry_run)):
        s = sub.add_parser(name)
        s.add_argument("config")
        if name == "dry-run":
            s.add_argument("--control", action="store_true", help="use the shuffled-phase control order")
        s.set_defaults(fn=fn)

    rl = sub.add_parser("run-local")
    rl.add_argument("config")
    rl.add_argument("--mock", action="store_true", help="in-process mock engine (zero cost)")
    rl.add_argument("--live", action="store_true", help="send to the active (or --target) self-hosted vLLM")
    rl.add_argument("--target", default=None, help="target profile name (default: active target)")
    rl.add_argument("--results-root", default=str(REPO / "results"))
    rl.set_defaults(fn=cmd_run_local)

    tg = sub.add_parser("target", help="list/show/switch/check the backend target (aws|selfhost)")
    tg.add_argument("action", choices=["list", "show", "use", "check"], nargs="?", default="show")
    tg.add_argument("name", nargs="?", default=None)
    tg.set_defaults(fn=cmd_target)

    sm = sub.add_parser("summarize")
    sm.add_argument("--input", required=True)
    sm.add_argument("--output", required=True)
    sm.set_defaults(fn=cmd_summarize)

    ms = sub.add_parser("mock-server")
    ms.add_argument("--host", default="127.0.0.1")
    ms.add_argument("--port", type=int, default=8000)
    ms.add_argument("--model", default="mock-model")
    ms.add_argument("--max-model-len", type=int, default=8192)
    ms.set_defaults(fn=cmd_mock_server)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
