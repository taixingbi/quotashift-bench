"""X2 in-VPC runner entry (G1 only; docs/X2_CAMPAIGN_RUNBOOK.md). NOT a frozen artifact: it only moves files and calls the
FROZEN X2 drivers, which re-check every pin (pin_x2 --check, phase pins) themselves before any live request.

    python scripts/x2_runner_entry.py run  -- python scripts/x2_stage.py --platform g1m0 --phase calA --live ...
    python scripts/x2_runner_entry.py hold --max-s 10800     # ECS Exec qualification: wait for /app/results/.x2_done
    python scripts/x2_runner_entry.py pack --platform g1m0 --out .x2_inputs/g1m0.tar.gz   # LOCAL (aws_ops x2-inputs)
    KIND=cal PLAT=g1m0 BUCKET=b python scripts/x2_runner_entry.py overrides -- [--rerun ID --reason TEXT]  # LOCAL

Inputs: the per-phase inputs tarball made by `scripts/aws_ops.sh x2-inputs` (the platform's committed experiments/x2/<p>/
and its earlier stage reports reports/x2/<p>/), downloaded by the task's `inputs-download` container to
/app/inputs/inputs.tar.gz. Its SHA-256 must equal QUOTASHIFT_X2_INPUTS_SHA256 (passed by aws_ops run-stage), else the
runner refuses before anything is sent. Only regular files under experiments/x2/<p>/ and reports/x2/<p>/ are extracted
(no absolute paths, no "..", no links).
Outputs: experiments/x2/<p>/ and reports/x2/<p>/ are copied to /app/results/x2_outputs/ on exit, which the
results-upload sidecar syncs to S3; the operator downloads them (aws_ops collect) and commits the non-raw records.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

APP = Path(os.environ.get("QUOTASHIFT_APP_ROOT", "/app"))
INPUTS = APP / "inputs" / "inputs.tar.gz"
RESULTS = APP / "results"
DONE = RESULTS / ".x2_done"
PLATFORMS = ("g1m0", "g1m1")


class Refused(SystemExit):
    def __init__(self, msg: str) -> None:
        print(f"REFUSED: {msg}", file=sys.stderr)
        super().__init__(3)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def allowed(name: str, plat: str) -> bool:
    parts = Path(name).parts
    return (not name.startswith("/") and ".." not in parts and len(parts) >= 3
            and parts[:3] in (("experiments", "x2", plat), ("experiments", "x2_a2", plat), ("reports", "x2", plat)))


def extract(plat: str, *, inputs: Path = INPUTS, want_sha: str | None = None, root: Path = APP) -> list[str]:
    want = want_sha if want_sha is not None else os.environ.get("QUOTASHIFT_X2_INPUTS_SHA256", "")
    if not want:
        raise Refused("QUOTASHIFT_X2_INPUTS_SHA256 not set")
    if not inputs.exists():
        raise Refused(f"{inputs} missing (inputs-download container)")
    got = sha256(inputs)
    if got != want:
        raise Refused(f"inputs sha256 {got} != expected {want}")
    out = []
    with tarfile.open(inputs, "r:gz") as tf:
        for m in tf.getmembers():
            if not (m.isfile() or m.isdir()) or not allowed(m.name, plat):
                raise Refused(f"unexpected member in inputs: {m.name!r}")
            if m.isfile():
                dst = root / m.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(m) as src, dst.open("wb") as f:  # type: ignore[union-attr]
                    shutil.copyfileobj(src, f)
                out.append(m.name)
    return out


def seed_reports(plat: str, root: Path = APP) -> None:
    """Earlier stage logs must be where the stage driver's --out-root looks (on the uploaded results volume)."""
    src, dst = root / "reports" / "x2" / plat, root / "results" / "reports" / "x2" / plat
    if src.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True)


def export(plat: str, root: Path = APP) -> None:
    dst = root / "results" / "x2_outputs"
    for rel in (Path("experiments") / "x2" / plat, Path("experiments") / "x2_a2" / plat, Path("reports") / "x2" / plat):
        if (root / rel).exists():
            shutil.copytree(root / rel, dst / rel, dirs_exist_ok=True)


TARGET = {"g1m0": "x2-g1-qwen", "g1m1": "x2-g1-mistral"}
A2_KINDS = ("a2_freeze_main", "a2_main")          # tokens x2a2_freeze_main_<p>, x2a2_main_<p>


def pack(plat: str, out: Path, repo: Path) -> str:
    """Deterministic inputs tarball (sorted, mtime 0, no owners) of experiments/x2/<p>/, experiments/x2_a2/<p>/
    (X2 Amendment A2, when present) and reports/x2/<p>/."""
    import gzip
    import io
    files = sorted(p for base in (repo / "experiments" / "x2" / plat, repo / "experiments" / "x2_a2" / plat,
                                  repo / "reports" / "x2" / plat) if base.exists()
                   for p in base.rglob("*") if p.is_file() and not p.is_symlink())
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for p in files:
            rel = p.relative_to(repo).as_posix()
            if not allowed(rel, plat):
                raise Refused(f"unexpected path {rel}")
            ti = tarfile.TarInfo(rel)
            data = p.read_bytes()
            ti.size, ti.mtime, ti.mode, ti.uid, ti.gid, ti.uname, ti.gname = len(data), 0, 0o644, 0, 0, "", ""
            tf.addfile(ti, io.BytesIO(data))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz:
        gz.write(buf.getvalue())
    return sha256(out)


def overrides(kind: str, plat: str, bucket: str, extra: list[str], env: dict) -> dict:
    """ECS run-task overrides for one X2 G1 stage (aws_ops.sh run-stage). Pure function; tested offline."""
    if plat not in PLATFORMS or kind not in ("qual", "cal", "main", "freeze_calA", "freeze_main", *A2_KINDS):
        raise Refused(f"no X2 G1 stage {kind!r} for {plat!r}")
    sha = env.get("QUOTASHIFT_X2_INPUTS_SHA256", "")
    tok = env.get("QUOTASHIFT_STAGE_APPROVAL", "")
    want = f"x2a2_{kind[3:]}_{plat}" if kind in A2_KINDS else f"x2_{kind}_{plat}"
    if tok != want or len(sha) != 64:
        raise Refused("stage token and inputs sha256 must match the requested stage")
    entry = ["python", "scripts/x2_runner_entry.py"]
    if kind == "a2_freeze_main":                    # X2 Amendment A2 (docs/PROTOCOL_X2_AMENDMENT_A2.md)
        if extra:
            raise Refused("trace freeze takes no extra arguments")
        cmd = [*entry, "run", "--", "python", "scripts/freeze_x2_a2_traces.py", "--platform", plat, "--live"]
    elif kind == "a2_main":
        if extra and not (len(extra) == 4 and extra[0] == "--rerun" and extra[2] == "--reason"):
            raise Refused("only '--rerun <block> --reason <text>' may be added to a stage")
        cmd = [*entry, "run", "--", "python", "scripts/x2_a2_stage.py", "--platform", plat, "--live", "--out-root",
               "/app/results/reports/x2", *extra]
    elif kind == "qual":
        if extra:
            raise Refused("qualification takes no extra arguments (one run, no retry)")
        cmd = [*entry, "qualify"]
    elif kind.startswith("freeze_"):
        if extra:
            raise Refused("trace freeze takes no extra arguments")
        cmd = [*entry, "run", "--", "python", "scripts/freeze_x2_traces.py", "--platform", plat, "--phase",
               kind.split("_", 1)[1], "--live"]
    else:
        if extra and not (len(extra) == 4 and extra[0] == "--rerun" and extra[2] == "--reason"):
            raise Refused("only '--rerun <block> --reason <text>' may be added to a stage")
        cmd = [*entry, "run", "--", "python", "scripts/x2_stage.py", "--platform", plat, "--phase",
               "calA" if kind == "cal" else "main", "--live", "--out-root", "/app/results/reports/x2", *extra]
    envs = [{"name": "QUOTASHIFT_APPROVED", "value": tok}, {"name": "QUOTASHIFT_X2_PLATFORM", "value": plat},
            {"name": "QUOTASHIFT_TARGET", "value": TARGET[plat]}, {"name": "QUOTASHIFT_X2_INPUTS_SHA256", "value": sha}]
    return {"containerOverrides": [
        {"name": "runner", "command": cmd, "environment": envs},
        {"name": "inputs-download", "command": ["s3", "cp", f"s3://{bucket}/inputs/{sha}.tar.gz", "/app/inputs/inputs.tar.gz",
                                                "--only-show-errors"]}]}


def qualify_cmd(plat: str) -> list[str]:
    """The FROZEN qualification driver, unchanged, under util-linux `script` (Debian image), which gives it the TTY its
    operator check requires. The runner's main process answers the frozen "yes" prompt (owner-approved pseudo-terminal
    answer; experiments/x2/approvals/). Replaces ECS Exec, whose sessions kill every process they started when they end."""
    return ["script", "-qfec", f"python scripts/x2_qualify.py --platform {plat} --live", "/dev/null"]


def run_qualify(plat: str, *, cmd: list[str] | None = None, log: Path | None = None, cwd: Path = APP) -> int:
    if os.environ.get("QUOTASHIFT_APPROVED") != f"x2_qual_{plat}":
        raise Refused(f"QUOTASHIFT_APPROVED must be x2_qual_{plat}")
    if (cwd / "experiments" / "x2" / plat / "QUALIFICATION.json").exists():
        raise Refused(f"{plat}: a qualification record already exists (one run per platform; no retry)")
    log = log or (RESULTS / f"x2_qual_{plat}.log")
    log.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(cmd or qualify_cmd(plat), cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(b"yes\n")               # the frozen prompt's answer; stdin stays open until the driver exits
    proc.stdin.flush()
    with log.open("ab") as f:
        for line in iter(proc.stdout.readline, b""):
            f.write(line)
            f.flush()
            sys.stdout.buffer.write(line)
            sys.stdout.flush()
    rc = proc.wait()
    proc.stdin.close()
    return rc


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["pack"]:                        # local helper
        pa = argparse.ArgumentParser()
        pa.add_argument("--platform", choices=PLATFORMS, required=True)
        pa.add_argument("--out", required=True)
        x = pa.parse_args(args[1:])
        print(pack(x.platform, Path(x.out), Path(__file__).resolve().parents[1]))
        return 0
    if args[:1] == ["overrides"]:                   # local helper
        import json
        extra = args[1:]
        extra = extra[1:] if extra[:1] == ["--"] else extra
        print(json.dumps(overrides(os.environ.get("KIND", ""), os.environ.get("PLAT", ""), os.environ.get("BUCKET", ""),
                                   extra, dict(os.environ))))
        return 0
    argv = args
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    r = sub.add_parser("run")
    r.add_argument("cmd", nargs=argparse.REMAINDER)
    h = sub.add_parser("hold")
    h.add_argument("--max-s", type=int, default=10800)
    sub.add_parser("qualify")
    a = ap.parse_args(argv)
    plat = os.environ.get("QUOTASHIFT_X2_PLATFORM", "")
    if plat not in PLATFORMS:
        raise Refused(f"QUOTASHIFT_X2_PLATFORM must be one of {PLATFORMS} (G0 runs locally, never here)")
    if os.environ.get("QUOTASHIFT_IN_VPC_RUNNER") != "1":
        raise Refused("x2_runner_entry runs only inside the in-VPC runner")
    if not os.environ.get("QUOTASHIFT_TARGET", "").startswith("x2-g1-"):
        raise Refused("QUOTASHIFT_TARGET must be an x2-g1-* target")
    files = extract(plat)
    print(f"inputs verified: {len(files)} files for {plat}", flush=True)
    seed_reports(plat)
    rc = 0
    try:
        if a.mode == "run":
            cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
            if not cmd or not any(c.endswith(("x2_stage.py", "freeze_x2_traces.py", "x2_a2_stage.py",
                                              "freeze_x2_a2_traces.py")) for c in cmd):
                raise Refused("run accepts only the X2 (or X2-A2) stage driver or trace freeze")
            rc = subprocess.run(cmd, cwd=APP).returncode
        elif a.mode == "qualify":
            rc = run_qualify(plat)
        else:
            t_end = time.time() + a.max_s
            print(f"holding for ECS Exec (until {DONE} exists or {a.max_s} s)", flush=True)
            while not DONE.exists() and time.time() < t_end:
                time.sleep(5)
            rc = 0 if DONE.exists() else 4
    finally:
        export(plat)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
