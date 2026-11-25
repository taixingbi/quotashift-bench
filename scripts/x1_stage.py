"""Protocol X1 stage driver (rev 4 sections 3, 6, 8, 10). One stage = (platform, phase), phase in calA | calB | main.

    uv run python scripts/x1_stage.py --platform g0m0 --phase main --mock --out-root /tmp/x1 --shorten 10
    QUOTASHIFT_APPROVED=x1_main_g0m0 uv run python scripts/x1_stage.py --platform g0m0 --phase main --live

Reuses the v5 driver's block runner and rules unchanged (scripts/v5_stage.py: verified pre-block prefix-cache reset,
`quotashift experiment`, gate summary; stop at the first failed block; at most one rerun per failed block with a
documented reason and a pre-generated new-salt `__r2` file; server identity before and after every block; live budget
stop at 1.3 x the stage estimate). X1 order: calB needs a completed calA + RATES.json; main needs a completed calB +
the platform's frozen FCFS_PREDICTIONS.json. Live runs additionally need (live_problems): the stage approval token,
an interactive "yes" (or, inside the VPC runner, the token passed by the approval-gated `aws_ops.sh run-stage`),
X1 Freeze Commit 1 (`pin_x1.py --check`), the phase's frozen traces, the platform's preflight record, a clean tree.
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
import build_x1  # noqa: E402
import v5_stage as vs  # noqa: E402  (frozen rules; imported unchanged)

X1 = REPO / "experiments" / "x1"
PHASES = ("calA", "calB", "main")
PREV = {"calA": None, "calB": "calA", "main": "calB"}
APPROVAL_ENV = vs.APPROVAL_ENV


def say(msg: str) -> None:
    vs.say(msg)


def block_files(plat: str, phase: str, root: Path = X1) -> list[Path]:
    return sorted(p for p in (root / plat / phase).glob("x1_*.yaml"))


def stage_reports(reports_root: Path, plat: str, phase: str) -> Path:
    return reports_root / plat / phase


def phase_prereqs(plat: str, phase: str, reports_root: Path, root: Path = X1) -> list[str]:
    p: list[str] = []
    prev = PREV[phase]
    if prev is not None:
        plog = vs.read_log(stage_reports(reports_root, plat, prev))
        if not plog or plog.get("status") != "completed":
            p.append(f"{plat}/{prev} has not completed (status {plog.get('status') if plog else None})")
    if phase in ("calB", "main") and not (root / plat / "RATES.json").exists():
        p.append(f"{root / plat / 'RATES.json'} missing (chosen after calibration A)")
    if phase == "main" and not (root / plat / "FCFS_PREDICTIONS.json").exists():
        p.append(f"{root / plat / 'FCFS_PREDICTIONS.json'} missing (X1 Freeze Commit 3 precedes the main stage)")
    if not block_files(plat, phase, root):
        p.append(f"no generated YAMLs under {root / plat / phase}")
    return p


def live_problems(plat: str, phase: str, *, interactive_ok: bool, root: Path = X1,
                  reports_root: Path = REPO / "reports" / "x1") -> list[str]:
    p: list[str] = []
    token = f"x1_{phase}_{plat}"
    if os.environ.get(APPROVAL_ENV) != token:
        p.append(f"{APPROVAL_ENV} must be {token} (owner approval for this stage only)")
    if not interactive_ok and os.environ.get("QUOTASHIFT_IN_VPC_RUNNER") != "1":
        p.append("operator did not confirm interactively")
    chk = subprocess.run([sys.executable, str(REPO / "scripts" / "pin_x1.py"), "--check"], cwd=REPO,
                         capture_output=True, text=True)
    if chk.returncode != 0:
        p.append(f"X1 Freeze Commit 1 not in place or pins changed: {chk.stdout.strip()[-200:]}{chk.stderr.strip()[-200:]}")
    import pin_x1  # per-phase pin: traces frozen + pinned BEFORE any run of the phase; nothing changed since
    p += pin_x1.phase_pin_problems(plat, phase, root=root, reports_root=reports_root)
    rec = root / plat / "HOST_VERIFICATION.json"
    if not rec.exists():
        p.append(f"{rec} missing (P1 + preflight)")
    else:
        r = json.loads(rec.read_text())
        need = "phase2" if phase in ("calB", "main") else "phase1"
        if (r.get("preflight") or {}).get(need, {}).get("status") not in ("pass", "flag"):
            p.append(f"preflight {need} not passed for {plat}")
    if os.environ.get("QUOTASHIFT_IN_VPC_RUNNER") != "1":
        st = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True).stdout.strip()
        if st:
            p.append(f"git tree not clean ({len(st.splitlines())} entries)")
    return p


def run_stage(plat: str, phase: str, *, mode: str, reports_root: Path, results_root: Path, work: Path | None = None,
              shorten: int | None = None, rerun: str | None = None, reason: str | None = None, root: Path = X1,
              server_start_fn: Callable[[], float | None] | None = None, runner: Callable[..., dict] = vs.run_block,
              target=None) -> int:  # noqa: ANN001
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
    log = vs.read_log(reports) or {"stage": f"{plat}/{phase}", "mode": mode, "status": "new", "blocks": {},
                                   "server_start": None, "stage_estimate_min": stage_est, "order": [f.stem for f in files]}
    if log["mode"] != mode:
        say(f"REFUSED: stage log at {reports} is from a {log['mode']} run")
        return 3
    if rerun is not None:
        b = log["blocks"].get(rerun)
        if b is None or b.get("status") != "failed":
            say(f"REFUSED: --rerun {rerun}: the block has not failed in this stage")
            return 3
        if f"{rerun}{build_x1.RERUN}" in log["blocks"]:
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
    log["status"] = "running"
    log.setdefault("started_utc", datetime.now(UTC).isoformat())
    vs.write_log(reports, log)
    queue: list[tuple[str, Path, str | None]] = []
    if rerun is not None:
        queue.append((f"{rerun}{build_x1.RERUN}", root / plat / phase / "reruns" / f"{rerun}{build_x1.RERUN}.yaml", rerun))
    queue += [(f.stem, f, None) for f in files if f.stem not in log["blocks"]]
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
    pending = [f.stem for f in files if not vs._block_ok(log, f.stem)]
    if pending:
        return vs._stop(reports, log, f"blocks not valid: {pending}")
    log["status"], log["completed_utc"] = "completed", datetime.now(UTC).isoformat()
    vs.write_log(reports, log)
    say(f"stage {plat}/{phase} COMPLETED ({len(files)} blocks)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", choices=tuple(build_x1.PLATFORMS), required=True)
    ap.add_argument("--phase", choices=PHASES, required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--mock", action="store_true")
    g.add_argument("--live", action="store_true")
    ap.add_argument("--out-root", default=str(REPO / "reports" / "x1"))
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
            sys.stdin.isatty() and input(f"Type 'yes' to run X1 {a.platform}/{a.phase} live: ").strip() == "yes")
        probs = live_problems(a.platform, a.phase, interactive_ok=ok, reports_root=out)
        if probs:
            print("REFUSED:\n  " + "\n  ".join(probs), file=sys.stderr)
            return 3
        from quotashift.targets import active_target
        target = active_target()
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
                     reason=a.reason)


if __name__ == "__main__":
    raise SystemExit(main())
