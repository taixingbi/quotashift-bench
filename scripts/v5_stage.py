"""Protocol v5 stage driver (docs/PROTOCOL_V5_DRAFT.md §8, §9 item 10, §10). `scripts/run_v5.sh` wraps this file.

    scripts/run_v5.sh smoke|A|B --mock --out-root <dir> [--shorten 10]   # dry run on the in-process mock (plumbing)
    scripts/run_v5.sh smoke|A|B --live                                   # owner-approved stage only (see below)
    scripts/run_v5.sh A --live --rerun <block> --reason "<text>"         # the single permitted rerun of a failed block

Per stage it runs the frozen block files in a fixed order (sorted file names). Per block it:
  1. checks the vLLM server start equals the stage's recorded start (live; §8 rule 3), before the block;
  2. resets and verifies the prefix cache, writing <report>/prerun_cache_reset.json (live);
  3. runs `quotashift experiment` with the file's own repetitions and --path;
  4. stops the stage on a non-zero exit, any failed fail-severity gate, or a server start that changed (checked
     again from the block's manifest);
  5. stops after the block if cumulative wall time exceeds 1.3x the stage estimate (§8 rule 6).
State is in <reports>/STAGE_LOG.json. Completed blocks are never rerun. A failed block may be rerun exactly once,
with a reason, from its pre-generated `experiments/v5/reruns/<block>__r2.yaml` (new isolation salt, same frozen
schedule); the failed report is kept. A second failure, or any other stop, needs owner review.

--live refuses unless: QUOTASHIFT_APPROVED=v5_stage_<smoke|A|B> and the operator types `yes`; the protocol is frozen
(docs/PROTOCOL_V5.md with a FROZEN status, experiments/v5/FROZEN_TRACES.json); the host verification record
experiments/v5/HOST_VERIFICATION.json passes; the tree is clean; raw output paths are git-ignored; the previous stage
completed (A needs smoke, B needs A). --mock never writes under reports/v5 or results/.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
V5 = REPO / "experiments" / "v5"
sys.path.insert(0, str(REPO / "scripts"))
import build_v5  # noqa: E402

STAGES = {"smoke": ("smoke", None), "A": ("stage_a", "smoke"), "B": ("stage_b", "A")}
ARM_MIN_PER_120S = 2.6       # §7: measured v4 wall time per 120 s arm incl. settle, drain, cache reset
TOKENIZE_MIN = 2.0           # §7: per block
BUDGET_FACTOR = 1.3          # §8 rule 6
APPROVAL_ENV = "QUOTASHIFT_APPROVED"
HOST_RECORD = V5 / "HOST_VERIFICATION.json"
MIN_MAX_NUM_SEQS = 64


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def say(msg: str) -> None:
    print(f"[{ts()}] {msg}", flush=True)


def block_files(stage: str) -> list[Path]:
    return sorted((V5 / STAGES[stage][0]).glob("*.yaml"))


def estimate_min(path: Path) -> float:
    d = yaml.safe_load(path.read_text())
    return 2 * d["comparison"]["repetitions"] * ARM_MIN_PER_120S * d["runtime_seconds"] / 120 + TOKENIZE_MIN


# ---------------------------------------------------------------- live preconditions (fail closed)
def host_record_problems(rec: dict | None) -> list[str]:
    """P1 host verification (§10): read on the host by the owner. Required fields and rules."""
    if rec is None:
        return [f"{HOST_RECORD.relative_to(REPO)} missing (pre-stage P1: host verification)"]
    p = []
    for k in ("vllm_version", "launch_command", "max_num_seqs", "max_num_batched_tokens", "verified_by", "verified_utc"):
        if rec.get(k) in (None, ""):
            p.append(f"host record lacks {k}")
    if rec.get("vllm_version") not in (None, "0.17.1"):
        p.append(f"vllm_version {rec.get('vllm_version')} != 0.17.1 (target profile)")
    if isinstance(rec.get("max_num_seqs"), int) and rec["max_num_seqs"] < MIN_MAX_NUM_SEQS and not rec.get("c32_dropped"):
        p.append(f"max_num_seqs {rec['max_num_seqs']} < {MIN_MAX_NUM_SEQS} and C = 32 not dropped before the freeze")
    if not rec.get("model_snapshot_sha") and not rec.get("model_revision_waiver"):
        p.append("model snapshot hash not verified and no written owner waiver (model_revision_waiver)")
    # evidence levels (P1 owner decisions 2026-11-23): only these are acceptable, and each weaker level must carry the
    # owner's recorded acceptance
    if rec.get("model_snapshot_sha"):
        lvl = rec.get("model_snapshot_evidence_level")
        ev = rec.get("model_snapshot_evidence") or {}
        if lvl not in ("verified_direct", "verified_by_exclusion"):
            p.append(f"model snapshot evidence level {lvl!r} is not verified_direct / verified_by_exclusion")
        elif lvl == "verified_by_exclusion" and not ev.get("owner_accepted_by"):
            p.append("snapshot identified by exclusion without recorded owner acceptance")
    src = rec.get("max_num_seqs_source")
    if src not in ("argv", "startup_log", "inferred_from_source_default"):
        p.append(f"max_num_seqs source {src!r} not accepted (argv, startup_log, or the owner-approved source-default rule)")
    elif src == "inferred_from_source_default":
        inf = rec.get("max_num_seqs_inference") or {}
        if not (inf.get("all_conditions_hold") and inf.get("owner_approved_by") and inf.get("uncertainty")
                and inf.get("rule") == "vllm-0.17.1-openai-server-default-max-num-seqs"):
            p.append("max_num_seqs inferred from source defaults without the complete, owner-approved rule record")
    return p


def live_problems(stage: str, reports: Path, *, interactive_ok: bool) -> list[str]:
    p: list[str] = []
    if os.environ.get(APPROVAL_ENV) != f"v5_stage_{stage}":
        p.append(f"{APPROVAL_ENV} must be v5_stage_{stage} (owner approval for this stage only)")
    if not interactive_ok:
        p.append("operator did not confirm interactively")
    proto = REPO / "docs" / "PROTOCOL_V5.md"
    if not proto.exists() or "**Status:** FROZEN" not in proto.read_text():
        p.append("docs/PROTOCOL_V5.md with '**Status:** FROZEN' missing: Protocol v5 is not frozen")
    if not (V5 / "FROZEN_TRACES.json").exists():
        p.append("experiments/v5/FROZEN_TRACES.json missing (pre-stage P2)")
    rec = json.loads(HOST_RECORD.read_text()) if HOST_RECORD.exists() else None
    p += host_record_problems(rec)
    st = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    if st:
        p.append(f"git tree not clean ({len(st.splitlines())} entries)")
    p += ignored_problems(reports)
    return p   # stage order (A needs smoke, B needs A) is enforced by run_stage in every mode


def ignored_problems(reports: Path) -> list[str]:
    """Raw output must be git-ignored, or the first arm makes the tree dirty and fails every later provenance gate."""
    probes = [reports / "probe", REPO / "results" / "v5_probe__attack" / "x"]
    r = subprocess.run(["git", "check-ignore", *map(str, probes)], cwd=REPO, capture_output=True, text=True)
    ign = set(r.stdout.split())
    return [f"{q} is not git-ignored" for q in map(str, probes) if q not in ign]


# ---------------------------------------------------------------- stage log
def read_log(reports: Path) -> dict | None:
    f = reports / "STAGE_LOG.json"
    return json.loads(f.read_text()) if f.exists() else None


def write_log(reports: Path, log: dict) -> None:
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "STAGE_LOG.json").write_text(json.dumps(log, indent=1) + "\n")


# ---------------------------------------------------------------- mock derivation (plumbing only)
def shortened(src: Path, dst: Path, seconds: int) -> Path:
    """Mock dry run copy: no frozen traces (they need the live tokenizer), a shorter window, counts scaled down."""
    d = yaml.safe_load(src.read_text())
    d.pop("frozen_traces", None)
    f = seconds / d["runtime_seconds"]
    d["runtime_seconds"] = seconds
    for ph in d["phases"]:
        ph["duration_seconds"] = seconds
        ph["request_count"] = max(2, round(ph["request_count"] * f))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(yaml.safe_dump(d, sort_keys=False))
    return dst


# ---------------------------------------------------------------- block execution
def gate_summary(report: Path) -> tuple[bool, list[str], list[str]]:
    man = json.loads((report / "manifest.json").read_text())
    checks = (man.get("validity") or {}).get("checks") or []
    failed = [c["name"] for c in checks if c.get("severity") == "fail" and not c.get("passed")]
    starts = list((man.get("provenance") or {}).get("server_start") or [])
    return bool(checks) and not failed, failed, starts


def run_block(yaml_path: Path, *, mode: str, report: Path, results_root: Path, target=None) -> dict:  # noqa: ANN001
    d = yaml.safe_load(yaml_path.read_text())
    reps = d["comparison"]["repetitions"]
    rec: dict = {"file": str(yaml_path), "report": str(report), "reps": reps, "path": build_v5.path_of(yaml_path),
                 "started_utc": datetime.now(UTC).isoformat()}
    t0 = time.monotonic()
    if mode == "live":
        from quotashift.instrumentation.cache_reset import reset_and_verify
        cr = reset_and_verify(target.backend_url, target.model, tag=f"v5-block-{yaml_path.stem}")
        cr["note"] = "pre-block hygiene reset (not per-arm; scenario cache_reset unchanged)"
        report.mkdir(parents=True, exist_ok=True)
        (report / "prerun_cache_reset.json").write_text(json.dumps(cr, indent=2))
        rec["cache_reset_verified"] = bool(cr.get("verified"))
        if not cr.get("verified"):
            rec |= {"status": "failed", "reason": "cache reset not verified", "wall_s": time.monotonic() - t0}
            return rec
    cmd = [sys.executable, "-m", "quotashift.cli", "experiment", str(yaml_path), "--reps", str(reps), f"--{mode}",
           "--path", rec["path"], "--out", str(report), "--results-root", str(results_root)]
    rec["command"] = " ".join(cmd[2:])
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    report.mkdir(parents=True, exist_ok=True)
    (report / "driver_stderr.txt").write_text(r.stderr)
    rec["rc"], rec["wall_s"] = r.returncode, time.monotonic() - t0
    if not (report / "manifest.json").exists():
        rec |= {"status": "failed", "reason": f"no report (rc {r.returncode}): {r.stderr.strip()[-300:]}"}
        return rec
    ok, failed, starts = gate_summary(report)
    rec |= {"failed_gates": failed, "server_start": starts,
            "status": "passed" if ok and r.returncode == 0 else "failed",
            "reason": None if ok and r.returncode == 0 else f"rc {r.returncode}; failed gates {failed}"}
    return rec


def run_stage(stage: str, *, mode: str, reports: Path, results_root: Path, work: Path | None = None,
              shorten: int | None = None, rerun: str | None = None, reason: str | None = None, target=None,  # noqa: ANN001
              server_start_fn: Callable[[], float | None] | None = None,
              runner: Callable[..., dict] = run_block) -> int:
    """Returns 0 when the stage completed, 4 when it stopped (log says why), 3 when it refused to start."""
    files = block_files(stage)
    est = {f.stem: estimate_min(f) for f in files}
    stage_est = sum(est.values())
    log = read_log(reports) or {"stage": stage, "mode": mode, "status": "new", "blocks": {}, "server_start": None,
                                "stage_estimate_min": stage_est, "order": [f.stem for f in files]}
    if log["mode"] != mode:
        say(f"REFUSED: stage log at {reports} is from a {log['mode']} run")
        return 3
    prev = STAGES[stage][1]   # §8 rule 7: A runs only after the smokes pass; B only if every A block is valid
    if prev is not None:
        plog = read_log(reports.parent / STAGES[prev][0])
        if not plog or plog.get("status") != "completed":
            say(f"REFUSED: stage {prev} has not completed (status {plog.get('status') if plog else None})")
            return 3
    if rerun is not None:
        b = log["blocks"].get(rerun)
        if b is None or b.get("status") != "failed":
            say(f"REFUSED: --rerun {rerun}: the block has not failed in this stage")
            return 3
        if f"{rerun}{build_v5.RERUN}" in log["blocks"]:
            say(f"REFUSED: {rerun} was already rerun once (§8 rule 2: a second failure needs owner review)")
            return 3
        if not reason:
            say("REFUSED: a rerun needs a documented --reason")
            return 3
    elif log["status"] == "stopped":
        say(f"REFUSED: stage stopped earlier ({log.get('stopped_reason')}); only --rerun of a failed block or owner "
            "review may continue it")
        return 3
    elif log["status"] == "completed":
        say(f"stage {stage} already completed")
        return 0
    log["status"] = "running"
    log.setdefault("started_utc", datetime.now(UTC).isoformat())
    write_log(reports, log)

    queue: list[tuple[str, Path, str | None]] = []
    if rerun is not None:
        queue.append((f"{rerun}{build_v5.RERUN}", V5 / "reruns" / f"{rerun}{build_v5.RERUN}.yaml", rerun))
    queue += [(f.stem, f, None) for f in files if f.stem not in log["blocks"]]
    total = len(files)
    for sid, f, rerun_of in queue:
        done = sum(_block_ok(log, g.stem) for g in files)
        spent = sum(b.get("wall_s", 0.0) for b in log["blocks"].values()) / 60
        say(f"block {done + 1}/{total} {sid}: start; stage elapsed {spent:.1f} min of {stage_est:.1f} min estimated "
            f"(this block ≈ {est.get(build_v5.base_id(sid), 0):.1f} min)")
        if server_start_fn is not None:   # §8 rule 3, before the block
            now_start = server_start_fn()
            if log["server_start"] is None:
                log["server_start"] = now_start
            if now_start is None or now_start != log["server_start"]:
                return _stop(reports, log, f"server_identity: start {now_start} != stage start {log['server_start']} "
                                           f"before {sid}")
        src = f
        if mode == "mock":
            assert work is not None
            src = shortened(f, work / f"{sid}.yaml", shorten) if shorten else shortened(
                f, work / f"{sid}.yaml", yaml.safe_load(f.read_text())["runtime_seconds"])
        rec = runner(src, mode=mode, report=reports / sid, results_root=results_root, target=target)
        rec |= {"rerun_of": rerun_of, "reason": rec.get("reason") if rerun_of is None else
                f"{rec.get('reason') or 'passed'} | rerun reason: {reason}"}
        log["blocks"][sid] = rec
        write_log(reports, log)
        say(f"block {sid}: {rec['status']} in {rec.get('wall_s', 0) / 60:.1f} min"
            + (f" — {rec.get('reason')}" if rec["status"] != "passed" else ""))
        if rec["status"] != "passed":
            return _stop(reports, log, f"{sid} failed: {rec.get('reason')}")
        if server_start_fn is not None and rec.get("server_start") != [str(log["server_start"])]:
            return _stop(reports, log, f"server_identity: {sid} manifest server start {rec.get('server_start')} != "
                                       f"stage start {log['server_start']}")
        spent = sum(b.get("wall_s", 0.0) for b in log["blocks"].values()) / 60
        if mode == "live" and spent > BUDGET_FACTOR * stage_est:
            return _stop(reports, log, f"budget: {spent:.1f} min > {BUDGET_FACTOR} x {stage_est:.1f} min (§8 rule 6)")
    pending = [f.stem for f in files if not _block_ok(log, f.stem)]
    if pending:
        return _stop(reports, log, f"blocks not valid: {pending}")
    log["status"], log["completed_utc"] = "completed", datetime.now(UTC).isoformat()
    write_log(reports, log)
    say(f"stage {stage} COMPLETED ({total} blocks)" + ("" if stage == "smoke" else
        f"; analysis: uv run python scripts/v5_analysis.py --stage {stage}"))
    return 0


def _block_ok(log: dict, sid: str) -> bool:
    b, r = log["blocks"].get(sid), log["blocks"].get(f"{sid}{build_v5.RERUN}")
    return bool(b and b.get("status") == "passed") or bool(b and r and r.get("status") == "passed")


def _stop(reports: Path, log: dict, why: str) -> int:
    log["status"], log["stopped_reason"], log["stopped_utc"] = "stopped", why, datetime.now(UTC).isoformat()
    write_log(reports, log)
    say(f"STAGE STOPPED: {why}")
    return 4


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=tuple(STAGES))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--mock", action="store_true")
    g.add_argument("--live", action="store_true")
    ap.add_argument("--out-root", default=None, help="mock only: where reports/, results/ and derived YAMLs go")
    ap.add_argument("--shorten", type=int, default=None, help="mock only: window in seconds (default: as frozen)")
    ap.add_argument("--rerun", default=None)
    ap.add_argument("--reason", default=None)
    a = ap.parse_args()
    if a.mock:
        if not a.out_root:
            print("--mock needs --out-root (mock output never goes under reports/v5 or results/)", file=sys.stderr)
            return 3
        root = Path(a.out_root).resolve()
        if root == REPO or REPO in root.parents:
            print("--out-root must be outside the repository", file=sys.stderr)
            return 3
        return run_stage(a.stage, mode="mock", reports=root / "reports" / STAGES[a.stage][0], results_root=root / "results",
                         work=root / "yaml", shorten=a.shorten, rerun=a.rerun, reason=a.reason)
    if a.shorten:
        print("--shorten is mock only", file=sys.stderr)
        return 3
    reports = REPO / "reports" / "v5" / STAGES[a.stage][0]
    files = block_files(a.stage)
    est = sum(estimate_min(f) for f in files)
    print(f"Protocol v5 stage {a.stage}: {len(files)} blocks, about {est / 60:.1f} h of self-hosted GPU time.")
    ok = sys.stdin.isatty() and input("Type 'yes' to run this stage on the live GPU: ").strip() == "yes"
    problems = live_problems(a.stage, reports, interactive_ok=ok)
    if problems:
        print("REFUSED (nothing sent):\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return 3
    from quotashift.local import current_server_start
    from quotashift.targets import active_target
    target = active_target()
    return run_stage(a.stage, mode="live", reports=reports, results_root=REPO / "results", rerun=a.rerun,
                     reason=a.reason, target=target, server_start_fn=lambda: current_server_start(target))


if __name__ == "__main__":
    raise SystemExit(main())
