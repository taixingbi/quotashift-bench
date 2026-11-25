"""quotashift command-line interface.

    python -m quotashift.cli doctor
    python -m quotashift.cli validate experiments/smoke.yaml
    python -m quotashift.cli dry-run experiments/stateful_sequences.yaml [--control]
    python -m quotashift.cli run-local experiments/smoke.yaml --mock
    python -m quotashift.cli budget experiments/a1_burst_arrivals.yaml
    python -m quotashift.cli experiment experiments/a1_burst_arrivals.yaml --reps 5 --mock
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
import os
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
    out: dict = {
        "scenario_id": sc.scenario_id,
        "phase_order": order or [p.name for p in sc.phases],
        "total_requests": len(items),
        "schedule_sha256": sc.schedule_hash(phase_order=order),
        "per_tenant": per_tenant,
        "note": "DRY RUN: nothing sent. Synthetic schedule only.",
    }
    # Matched-budget comparison against the pre-registered control (reporting only;
    # `quotashift budget` is the fail-closed gate).
    if order is None and sc.competing_tenants:
        from quotashift.budget import budget_report, summarize_trace

        try:
            from quotashift.local import budget_view, paired_traces
            from quotashift.scenario import CONTROL_DIMENSIONS

            atk_items, control, label = paired_traces(sc, sc.seed)
            out["control"] = {
                "control": label,
                "protocol_version": sc.protocol_version,
                "control_dimensions": CONTROL_DIMENSIONS.get(sc.comparison.primary_control),
                "report": budget_report(summarize_trace(budget_view(sc, atk_items, sc.seed)), summarize_trace(control),
                                        sc.comparison),
            }
        except (ValidationError, ValueError, FileNotFoundError) as e:
            out["control"] = {"error": str(e)}
    _print(out)
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
    if target is not None:
        ok, msg = check_prefix_caching(sc, target)
        if not ok:
            print(msg, file=sys.stderr)
            return 3
    out = run_scenario_local(sc, Path(a.results_root), phase_order=None, target=target, path=a.path, seed=a.seed)
    s = json.loads((out / "metrics_summary.json").read_text())
    _print({"run_dir": str(out), "offered": s.get("offered"), "status_counts": s.get("status_counts"),
            "accounting_conserved": s.get("accounting_conserved"), "event_validation_ok": s.get("event_validation_ok"),
            "worst_tenant_slo_attainment": s.get("worst_tenant_slo_attainment"),
            "synthetic_backend": s.get("synthetic_backend"), "path": s.get("path"),
            "engine_prefix_cache_hit_ratio": (s.get("engine_counters") or {}).get("prefix_cache_hit_ratio"),
            "unrelated_traffic_suspected": (s.get("engine_counters") or {}).get("unrelated_traffic_suspected"),
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


# ---------------------------------------------------------------- budget


def cmd_budget(a: argparse.Namespace) -> int:
    """Fail-closed matched-budget gate for a scenario and its control."""
    from quotashift.budget import BudgetMismatch, summarize_trace, verify_matched_budget
    from quotashift.scenario import load_scenario

    try:
        sc = load_scenario(_resolve(a.config))
    except (ValidationError, ValueError) as e:
        print(f"INVALID: {a.config}\n{e}", file=sys.stderr)
        return 2
    from quotashift.local import paired_traces

    try:
        atk_items, control, label = paired_traces(sc, sc.seed)
    except (ValueError, FileNotFoundError) as e:
        print(f"control unavailable: {e}", file=sys.stderr)
        return 2
    from quotashift.local import budget_view

    attack = summarize_trace(budget_view(sc, atk_items, sc.seed))
    ctl = summarize_trace(control)
    try:
        report = verify_matched_budget(attack, ctl, sc.comparison)
    except BudgetMismatch as e:
        _print({"scenario_id": sc.scenario_id, "control": label, "matched": False, "report": e.report})
        print(str(e), file=sys.stderr)
        return 2
    from quotashift.scenario import CONTROL_DIMENSIONS

    _print({"scenario_id": sc.scenario_id, "control": label, "matched": True, "report": report,
            "protocol_version": sc.protocol_version,
            "control_dimensions": CONTROL_DIMENSIONS.get(sc.comparison.primary_control)})
    return 0


# ---------------------------------------------------------------- experiment (Phase 5)


def cmd_experiment(a: argparse.Namespace) -> int:
    """Run an attack/control pair over N seeds and write the attack-effect report."""
    from quotashift.evaluation.attack_effect import (
        analyze_pair,
        run_metrics,
        secondary_endpoints,
        write_report,
    )
    from quotashift.evaluation.validity import apply_gates, run_manifest_provenance, validity_gates
    from quotashift.local import run_matched_pairs
    from quotashift.scenario import load_scenario
    from quotashift.targets import active_target, load_target, model_revision_provenance
    from quotashift.workload.tokenize import TokenizedContextInvalid

    if a.mock == a.live:
        print("experiment requires exactly one of --mock or --live.", file=sys.stderr)
        return 3
    target = None
    if a.live:
        target = load_target(a.target) if a.target else active_target()
        if target.kind == "aws" and os.environ.get("QUOTASHIFT_IN_VPC_RUNNER") != "1":
            # AWS targets are private VPC endpoints: only the approval-gated runner task inside the VPC (which sets
            # QUOTASHIFT_IN_VPC_RUNNER=1, infra/terraform compute.tf) may drive them. Never from a workstation.
            print("experiment --live supports self-hosted targets only (AWS targets run only inside the VPC runner "
                  "task started by scripts/aws_ops.sh).", file=sys.stderr)
            return 3
    try:
        sc = load_scenario(_resolve(a.config))
    except (ValidationError, ValueError) as e:
        print(f"INVALID: {a.config}\n{e}", file=sys.stderr)
        return 2
    if not sc.competing_tenants:
        print("experiment needs a scenario with competing_tenants (an attack scenario).", file=sys.stderr)
        return 2

    out_dir = Path(a.out) if a.out else (REPO / "reports" / sc.scenario_id)
    if (out_dir / "manifest.json").exists() and not a.force:
        print(f"refusing to overwrite existing report {out_dir} (historical results are immutable); "
              "use --out <new dir> or --force", file=sys.stderr)
        return 3
    if target is not None:
        ok, msg = check_prefix_caching(sc, target)
        if not ok:
            print(msg, file=sys.stderr)
            return 3
    results_root = Path(a.results_root)
    from quotashift.local import (
        CacheResetUnverified,
        FrozenTraceMismatch,
        LifecycleLeak,
        ServerRestarted,
        WarmCacheRerun,
    )
    from quotashift.runtime.runner import EngineNotReady

    if target is not None:
        from quotashift.targets import write_target_snapshot

        snap = write_target_snapshot(target, out_dir / "target_snapshot")
        if not snap["check"].get("ok"):
            print(f"preflight failed: {snap['check'].get('problems')} (snapshot in {out_dir / 'target_snapshot'})",
                  file=sys.stderr)
            return 3
    try:
        pairs = run_matched_pairs(sc, results_root, reps=a.reps, target=target, path=a.path,
                                  allow_warm_rerun=a.allow_warm_rerun)
    except WarmCacheRerun as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 3
    except (LifecycleLeak, CacheResetUnverified, ServerRestarted, EngineNotReady) as e:
        print(f"STOPPED: {type(e).__name__}: {e}", file=sys.stderr)
        return 4
    except TokenizedContextInvalid as e:
        print(f"REFUSED (tokenized context, nothing sent): {e}", file=sys.stderr)
        return 3
    except FrozenTraceMismatch as e:
        print(f"REFUSED (frozen v4 trace mismatch, nothing sent): {e}", file=sys.stderr)
        return 3
    pairs["budget_tolerance"] = sc.comparison.budget_tolerance
    attack = [run_metrics(pairs["attack"][s], sc.scenario_id, "attack", s) for s in pairs["seeds"]]
    control = [run_metrics(pairs["control"][s], sc.scenario_id, "control", s) for s in pairs["seeds"]]
    analysis = analyze_pair(
        attack, control, metric=sc.comparison.degradation_metric,
        threshold=sc.comparison.preregistered_threshold, direction=sc.comparison.effect_direction)
    secondary = secondary_endpoints(attack, control, threshold=sc.comparison.preregistered_threshold)
    run_dirs = [*pairs["attack"].values(), *pairs["control"].values()]
    prov = run_manifest_provenance(run_dirs)
    if target is not None:
        prov.update(model_revision_provenance(target))
    pairs["provenance"] = prov
    validity = validity_gates(
        attack, control, analysis, max_model_len=sc.model_max_len, prompt_token_unit=sc.prompt_token_unit,
        designed_early_termination=sc.lifecycle is not None, provenance=prov,
        tokenization=pairs.get("tokenization"), synthetic=target is None, protocol_version=sc.protocol_version,
        ignore_eos=sc.ignore_eos, feasibility_gates=sc.comparison.feasibility_gates,
        expected_cap=sc.safety.max_global_inflight, path=a.path)
    if validity.get("regime") is not None:
        analysis["regime"] = validity["regime"]
    analysis = apply_gates(analysis, validity)
    cmds = [
        f"uv run quotashift budget {a.config}",
        f"uv run quotashift experiment {a.config} --reps {a.reps} --{'mock' if a.mock else 'live'} --path {a.path}",
    ]
    written = write_report(sc.scenario_id, pairs, analysis, attack, control, out_dir, commands=cmds,
                           secondary=secondary, validity=validity)
    _print({
        "scenario_id": sc.scenario_id, "control": pairs["control_label"], "seeds": pairs["seeds"],
        "metric": analysis["metric"], "mean_ratio": analysis["mean_ratio"],
        "classification": analysis.get("classification"), "effect_direction": analysis.get("effect_direction"),
        "ratio_ci95": analysis["ratio_ci95"], "attack_success_rate": analysis["attack_success_rate"],
        "synthetic_backend": target is None, "validity_passed": validity["passed"], "regime": validity.get("regime"),
        **written,
    })
    if not validity["passed"]:
        failed = [c["name"] for c in validity["checks"] if c["severity"] == "fail" and not c["passed"]]
        print(f"INVALID: validity gates failed: {failed} (classification set to 'invalid'; report written)",
              file=sys.stderr)
        return 5
    return 0


def check_prefix_caching(sc, target) -> tuple[bool, str]:  # noqa: ANN001
    """Fail closed when the scenario pre-registers a prefix-caching state the server does not have."""
    if sc.expect_prefix_caching == "any":
        return True, "any"
    import httpx

    from quotashift.instrumentation.prom import parse_prometheus_text, resolve

    try:
        snap = resolve(parse_prometheus_text(httpx.get(target.backend_url.rstrip("/") + "/metrics", timeout=5).text))
    except httpx.HTTPError as e:
        return False, f"cannot read server cache config ({type(e).__name__}); expected prefix caching {sc.expect_prefix_caching}"
    val = (snap.info.get("vllm:cache_config_info") or {}).get("enable_prefix_caching")
    if val is None:
        return False, "server does not expose vllm:cache_config_info; cannot verify prefix-caching state"
    actual = "on" if val.lower() == "true" else "off"
    if actual != sc.expect_prefix_caching:
        return False, (f"scenario expects prefix caching {sc.expect_prefix_caching} but server has it {actual}; "
                       "restart vLLM with the pre-registered setting")
    return True, actual


def cmd_gpu_exporter(a: argparse.Namespace) -> int:
    """Run ON the GPU host: expose nvidia-smi readings as Prometheus text (binds loopback by default)."""
    import uvicorn
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    from quotashift.instrumentation.gpu import GpuSampler, exporter_metrics_text

    sampler = GpuSampler(index=a.gpu_index)
    if not sampler.available:
        print("nvidia-smi not found on this host; run the exporter on the GPU host", file=sys.stderr)
        return 2

    async def metrics(_req):  # noqa: ANN001, ANN202
        return PlainTextResponse(exporter_metrics_text(sampler))

    uvicorn.run(Starlette(routes=[Route("/metrics", metrics)]), host=a.host, port=a.port, log_level="warning")
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
    rl.add_argument("--path", choices=["gateway", "direct"], default="gateway",
                    help="gateway: admission/quota/queueing in front of vLLM (default); direct: pass-through")
    rl.add_argument("--seed", type=int, default=None, help="override the scenario seed")
    rl.set_defaults(fn=cmd_run_local)

    tg = sub.add_parser("target", help="list/show/switch/check the backend target (aws|selfhost)")
    tg.add_argument("action", choices=["list", "show", "use", "check"], nargs="?", default="show")
    tg.add_argument("name", nargs="?", default=None)
    tg.set_defaults(fn=cmd_target)

    bg = sub.add_parser("budget", help="fail-closed matched-budget gate (scenario vs its control)")
    bg.add_argument("config")
    bg.set_defaults(fn=cmd_budget)

    ex = sub.add_parser("experiment", help="Phase 5: run attack/control over N seeds + write report")
    ex.add_argument("config")
    ex.add_argument("--reps", type=int, default=5)
    ex.add_argument("--mock", action="store_true", help="in-process mock engine (zero cost)")
    ex.add_argument("--live", action="store_true", help="send to the active (or --target) self-hosted vLLM")
    ex.add_argument("--target", default=None)
    ex.add_argument("--results-root", default=str(REPO / "results"))
    ex.add_argument("--out", default=None, help="report dir (default: reports/<scenario_id>)")
    ex.add_argument("--path", choices=["gateway", "direct"], default="gateway")
    ex.add_argument("--force", action="store_true", help="allow overwriting an existing report dir")
    ex.add_argument("--allow-warm-rerun", action="store_true",
                    help="re-send identical prompts to the same vLLM server start (warm prefix cache); "
                         "never for a measurement, only for deliberate harness checks")
    ex.set_defaults(fn=cmd_experiment)

    ge = sub.add_parser("gpu-exporter", help="run ON the GPU host: nvidia-smi -> Prometheus /metrics")
    ge.add_argument("--host", default="127.0.0.1")
    ge.add_argument("--port", type=int, default=9835)
    ge.add_argument("--gpu-index", type=int, default=0)
    ge.set_defaults(fn=cmd_gpu_exporter)

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
