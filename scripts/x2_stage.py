"""Protocol X2 stage driver (docs/PROTOCOL_X2_DRAFT.md rev 2 sections 4-8). One stage = (platform, phase in calA | main).

    uv run python scripts/x2_stage.py --platform g0m0 --phase calA --mock --out-root /tmp/x2 --shorten 10
    QUOTASHIFT_APPROVED=x2_cal_g0m0 uv run python scripts/x2_stage.py --platform g0m0 --phase calA --live
    QUOTASHIFT_APPROVED=x2_main_g0m0 uv run python scripts/x2_stage.py --platform g0m0 --phase main --live

Reuses the frozen v5 block runner and rules unchanged (scripts/v5_stage.py run_block: verified pre-block prefix-cache
reset, `quotashift experiment`, gate summary; stop at the first failed block; at most one rerun per failed block with a
documented reason and a pre-generated `__r2` file; server identity before every block; live budget stop at
1.3 x the stage estimate). X2 additions:
  * every arm is wrapped by the X2 boundary-snapshot procedure (QUOTASHIFT_X2_BOUNDARY: before-snapshot, 15 s guard,
    arm, after-snapshot), with the platform's own qualified transport; an arm whose snapshots FAIL (OOM, vLLM restart,
    MemAvailable < 1 GiB) fails its block (v5 rerun rule);
  * order: calA needs PASSED qualification; main needs a completed calA + RATES.json (low feasible);
  * live runs need: QUOTASHIFT_APPROVED=x2_<cal|main>_<plat>, an interactive "yes" (or the in-VPC token), X2 Freeze
    Commit 1 (pin_x2 --check, which also re-verifies v5 and X1), the phase pin, a clean tree.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_x2  # noqa: E402
import v5_stage as vs  # noqa: E402  (frozen rules; imported unchanged)

X2 = REPO / "experiments" / "x2"
PHASES = ("calA", "main")
TOKEN = {"calA": "x2_cal_{plat}", "main": "x2_main_{plat}"}
APPROVAL_ENV = vs.APPROVAL_ENV


def say(msg: str) -> None:
    vs.say(msg)


def block_files(plat: str, phase: str, root: Path = X2) -> list[Path]:
    return sorted(p for p in (root / plat / phase).glob("x2_*.yaml"))


def stage_reports(reports_root: Path, plat: str, phase: str) -> Path:
    return reports_root / plat / phase


def boundary_config(plat: str, *, mode: str, guard_s: float | None = None) -> dict:
    """The platform's production snapshot procedure (docs/X2_INSTRUMENTATION_SPEC.md section 3)."""
    from quotashift.x2.snapshot import GUARD_S
    g = GUARD_S if guard_s is None else guard_s
    if mode == "mock":
        return {"transport": "mock", "guard_s": g}
    t = build_x2.PLATFORMS[plat]["snapshot_transport"]
    if t == "ssh":
        host = os.environ.get("QUOTASHIFT_X2_SSH_HOST")
        if not host:
            raise SystemExit("QUOTASHIFT_X2_SSH_HOST (ssh alias of the G0 host) is required for a live G0 stage")
        return {"transport": "ssh", "host": host, "guard_s": g}
    return {"transport": "http", "url": os.environ.get("QUOTASHIFT_X2_SNAPSHOT_URL",
                                                       "http://vllm.quotashift.internal:9500/"), "guard_s": g}


def phase_prereqs(plat: str, phase: str, reports_root: Path, root: Path = X2) -> list[str]:
    p: list[str] = []
    q = root / plat / "QUALIFICATION.json"
    if not q.exists() or json.loads(q.read_text()).get("status") != "pass":
        p.append(f"{plat}: qualification (Phase 1 + Q1) has not passed")
    if phase == "main":
        plog = vs.read_log(stage_reports(reports_root, plat, "calA"))
        if not plog or plog.get("status") != "completed":
            p.append(f"{plat}/calA has not completed (status {plog.get('status') if plog else None})")
        rates = root / plat / "RATES.json"
        if not rates.exists():
            p.append(f"{rates} missing (chosen after calibration A)")
        elif not json.loads(rates.read_text()).get("low_feasible", False):
            p.append(f"{plat}: low point infeasible: no main stage (reported, never substituted)")
    if not block_files(plat, phase, root):
        p.append(f"no generated YAMLs under {root / plat / phase}")
    return p


def live_problems(plat: str, phase: str, *, interactive_ok: bool, root: Path = X2,
                  reports_root: Path = REPO / "reports" / "x2") -> list[str]:
    p: list[str] = []
    token = TOKEN[phase].format(plat=plat)
    if os.environ.get(APPROVAL_ENV) != token:
        p.append(f"{APPROVAL_ENV} must be {token} (owner approval for this stage only)")
    if not interactive_ok and os.environ.get("QUOTASHIFT_IN_VPC_RUNNER") != "1":
        p.append("operator did not confirm interactively")
    chk = subprocess.run([sys.executable, str(REPO / "scripts" / "pin_x2.py"), "--check"], cwd=REPO,
                         capture_output=True, text=True)
    if chk.returncode != 0:
        p.append(f"X2 Freeze Commit 1 not in place or pins changed: {chk.stdout.strip()[-200:]}{chk.stderr.strip()[-200:]}")
    import pin_x2
    p += pin_x2.phase_pin_problems(plat, phase, root=root, reports_root=reports_root)
    if os.environ.get("QUOTASHIFT_IN_VPC_RUNNER") != "1":
        st = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True).stdout.strip()
        if st:
            p.append(f"git tree not clean ({len(st.splitlines())} entries)")
    return p


def snapshot_failures(report: Path, results_root: Path) -> list[str]:
    """Arms of this block whose boundary snapshots FAILED (fail severity) or are missing."""
    man = report / "manifest.json"
    if not man.exists():
        return []
    import v5_analysis as va  # frozen; run-dir resolution identical to the v5 loader

    m = json.loads(man.read_text())
    bad = []
    for arm, runs in (m.get("run_dirs") or {}).items():
        for seed, d in runs.items():
            f = va._resolve_run(d) / "x2_host_snapshots.json"
            if not f.exists():
                bad.append(f"{arm}/{seed}: no boundary snapshot")
                continue
            st = json.loads(f.read_text())["flags"]["status"]
            if st == "fail":
                bad.append(f"{arm}/{seed}: snapshot fail {json.loads(f.read_text())['flags']['fails']}")
    return bad


def run_stage(plat: str, phase: str, *, mode: str, reports_root: Path, results_root: Path, work: Path | None = None,
              shorten: int | None = None, rerun: str | None = None, reason: str | None = None, root: Path = X2,
              server_start_fn: Callable[[], float | None] | None = None, runner: Callable[..., dict] = vs.run_block,
              target=None, guard_s: float | None = None) -> int:  # noqa: ANN001
    """0 completed, 4 stopped (log says why), 3 refused."""
    reports = stage_reports(reports_root, plat, phase)
    pre = phase_prereqs(plat, phase, reports_root, root)
    if pre:
        for x in pre:
            say(f"REFUSED: {x}")
        return 3
    files = block_files(plat, phase, root)
    est = {f.stem: vs.estimate_min(f) for f in files}
    stage_est = sum(est.values())
    log = vs.read_log(reports) or {"stage": f"{plat}/{phase}", "protocol": "X2", "mode": mode, "status": "new",
                                   "blocks": {}, "server_start": None, "stage_estimate_min": stage_est,
                                   "order": [f.stem for f in files]}
    if log["mode"] != mode:
        say(f"REFUSED: stage log at {reports} is from a {log['mode']} run")
        return 3
    if rerun is not None:
        b = log["blocks"].get(rerun)
        if b is None or b.get("status") != "failed":
            say(f"REFUSED: --rerun {rerun}: the block has not failed in this stage")
            return 3
        if f"{rerun}{build_x2.RERUN}" in log["blocks"]:
            say(f"REFUSED: {rerun} was already rerun once (a second failure needs owner review)")
            return 3
        if not reason:
            say("REFUSED: a rerun needs a documented --reason")
            return 3
    elif log["status"] == "stopped":
        say(f"REFUSED: stage stopped earlier ({log.get('stopped_reason')}); only --rerun of a failed block may continue")
        return 3
    elif log["status"] == "completed":
        say(f"stage {plat}/{phase} already completed")
        return 0
    cfg = boundary_config(plat, mode=mode, guard_s=guard_s)
    os.environ["QUOTASHIFT_X2_BOUNDARY"] = json.dumps(cfg)          # inherited by the harness subprocess
    log["boundary"] = {k: v for k, v in cfg.items() if k != "host"}
    log["status"] = "running"
    log.setdefault("started_utc", datetime.now(UTC).isoformat())
    vs.write_log(reports, log)
    queue: list[tuple[str, Path, str | None]] = []
    if rerun is not None:
        queue.append((f"{rerun}{build_x2.RERUN}", root / plat / phase / "reruns" / f"{rerun}{build_x2.RERUN}.yaml", rerun))
    queue += [(f.stem, f, None) for f in files if f.stem not in log["blocks"]]
    try:
        for sid, f, rerun_of in queue:
            done = sum(vs._block_ok(log, g.stem) for g in files)
            spent = sum(b.get("wall_s", 0.0) for b in log["blocks"].values()) / 60
            say(f"block {done + 1}/{len(files)} {sid}: start; stage elapsed {spent:.1f} min of {stage_est:.1f} min estimated")
            if server_start_fn is not None:
                now = server_start_fn()
                if log["server_start"] is None:
                    log["server_start"] = now
                if now is None or now != log["server_start"]:
                    return vs._stop(reports, log, f"server_identity: start {now} != stage start {log['server_start']} "
                                                  f"before {sid}")
            src = f
            if mode == "mock":
                assert work is not None
                src = vs.shortened(f, work / f"{sid}.yaml", shorten or yaml.safe_load(f.read_text())["runtime_seconds"])
            rec = runner(src, mode=mode, report=reports / sid, results_root=results_root, target=target)
            snap_bad = snapshot_failures(reports / sid, results_root) if rec.get("status") == "passed" else []
            if snap_bad:
                rec |= {"status": "failed", "reason": f"x2 boundary snapshots: {snap_bad[:3]}"}
            rec |= {"rerun_of": rerun_of, "reason": rec.get("reason") if rerun_of is None else
                    f"{rec.get('reason') or 'passed'} | rerun reason: {reason}"}
            log["blocks"][sid] = rec
            vs.write_log(reports, log)
            say(f"block {sid}: {rec['status']} in {rec.get('wall_s', 0) / 60:.1f} min")
            if rec["status"] != "passed":
                return vs._stop(reports, log, f"{sid} failed: {rec.get('reason')}")
            if server_start_fn is not None and rec.get("server_start") != [str(log["server_start"])]:
                return vs._stop(reports, log, f"server_identity: {sid} manifest server start {rec.get('server_start')} != "
                                              f"stage start {log['server_start']}")
            spent = sum(b.get("wall_s", 0.0) for b in log["blocks"].values()) / 60
            if mode == "live" and spent > vs.BUDGET_FACTOR * stage_est:
                return vs._stop(reports, log, f"budget: {spent:.1f} min > {vs.BUDGET_FACTOR} x {stage_est:.1f} min")
    finally:
        os.environ.pop("QUOTASHIFT_X2_BOUNDARY", None)
    pending = [f.stem for f in files if not vs._block_ok(log, f.stem)]
    if pending:
        return vs._stop(reports, log, f"blocks not valid: {pending}")
    log["status"], log["completed_utc"] = "completed", datetime.now(UTC).isoformat()
    vs.write_log(reports, log)
    say(f"stage {plat}/{phase} COMPLETED ({len(files)} blocks)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", choices=tuple(build_x2.PLATFORMS), required=True)
    ap.add_argument("--phase", choices=PHASES, required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--mock", action="store_true")
    g.add_argument("--live", action="store_true")
    ap.add_argument("--out-root", default=str(REPO / "reports" / "x2"))
    ap.add_argument("--results-root", default=str(REPO / "results"))
    ap.add_argument("--shorten", type=int)
    ap.add_argument("--rerun")
    ap.add_argument("--reason")
    a = ap.parse_args()
    out = Path(a.out_root).resolve()
    if a.mock and (out == REPO or REPO in out.parents):
        print("REFUSED: mock output must live outside the repository", file=sys.stderr)
        return 3
    if a.live:
        ok = os.environ.get("QUOTASHIFT_IN_VPC_RUNNER") == "1" or (
            sys.stdin.isatty() and input(f"Type 'yes' to run X2 {a.platform}/{a.phase} live: ").strip() == "yes")
        probs = live_problems(a.platform, a.phase, interactive_ok=ok, reports_root=out)
        if probs:
            print("REFUSED:\n  " + "\n  ".join(probs), file=sys.stderr)
            return 3
        from quotashift.targets import active_target
        target = active_target()
        if target.model != build_x2.PLATFORMS[a.platform]["model"] or not target.name.startswith("x2-"):
            print(f"REFUSED: active target {target.name} ({target.model}) is not the X2 target of {a.platform}",
                  file=sys.stderr)
            return 3
        import httpx

        from quotashift.instrumentation.prom import parse_prometheus_text, resolve

        def start() -> float | None:
            try:
                return resolve(parse_prometheus_text(httpx.get(target.backend_url.rstrip("/") + "/metrics",
                                                               timeout=5).text)).values.get("process_start_time_seconds")
            except httpx.HTTPError:
                return None
        return run_stage(a.platform, a.phase, mode="live", reports_root=out, results_root=Path(a.results_root),
                         rerun=a.rerun, reason=a.reason, server_start_fn=start, target=target)
    work = out / "_work" / a.platform / a.phase
    return run_stage(a.platform, a.phase, mode="mock", reports_root=out, results_root=Path(a.results_root) if a.results_root
                     != str(REPO / "results") else out / "_results", work=work, shorten=a.shorten, rerun=a.rerun,
                     reason=a.reason, guard_s=0.0)


if __name__ == "__main__":
    raise SystemExit(main())
