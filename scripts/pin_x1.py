"""X1 artifact pinning (rev 4 section 10, stage X1-G).

    uv run python scripts/pin_x1.py --candidate      # non-binding freeze CANDIDATE list -> reports/x1/FREEZE_CANDIDATE_SHA256.json
    QUOTASHIFT_APPROVED=x1_freeze1 uv run python scripts/pin_x1.py --write   # Freeze Commit 1 (owner-approved only)
    uv run python scripts/pin_x1.py --check          # verify experiments/x1/FROZEN_SHA256.json (live runs require it)
    QUOTASHIFT_APPROVED=x1_freeze_<phase>_<plat> uv run python scripts/pin_x1.py --pin-phase <plat> <phase>
                                                     # per-phase pin (calA / calB / main = Freeze 3) after its traces

Pinned at Freeze Commit 1: the protocol, the X1 analysis / generator / predictor / stage driver / host sampler, the
preflight rules, the tokenization probe and the export gate. The frozen v5 modules X1 imports are not re-pinned here:
`--check` (and `--candidate`) require them to still match experiments/v5/FROZEN_SHA256.json, so X1 can never run on a
changed v5 rule. Later X1 freezes (traces, rates, predictions) are pinned by their own manifests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "experiments" / "x1" / "FROZEN_SHA256.json"
CANDIDATE = REPO / "reports" / "x1" / "FREEZE_CANDIDATE_SHA256.json"
V5_PINS = REPO / "experiments" / "v5" / "FROZEN_SHA256.json"
FILES = (
    "docs/PROTOCOL_X1_CROSS_PLATFORM_DRAFT.md",
    "scripts/build_x1.py", "scripts/x1_analysis.py", "scripts/x1_predictions.py", "scripts/x1_stage.py",
    "scripts/x1_host_sampler.py", "scripts/pin_x1.py", "scripts/freeze_x1_traces.py", "scripts/x1_iam_verify.py",
    "src/quotashift/x1/__init__.py", "src/quotashift/x1/preflight.py", "src/quotashift/x1/tokenize_probe.py",
    "src/quotashift/x1/export_gate.py",
)
V5_DEPENDENCIES = ("scripts/v5_analysis.py", "scripts/v5_fcfs_predictions.py", "scripts/build_v5.py",
                   "scripts/v5_stage.py", "scripts/freeze_v5.py", "scripts/freeze_v4.py")
X1 = REPO / "experiments" / "x1"
REPORTS = REPO / "reports" / "x1"


def sha(rel: str) -> str:
    return hashlib.sha256((REPO / rel).read_bytes()).hexdigest()


def v5_dependency_problems() -> list[str]:
    pins = json.loads(V5_PINS.read_text())
    pins = pins.get("files", pins)
    return [f"v5 dependency {r} changed since the v5 freeze" for r in V5_DEPENDENCIES if pins.get(r) != sha(r)]


def manifest(kind: str) -> dict:
    return {"kind": kind, "created_utc": datetime.now(UTC).isoformat(), "files": {r: sha(r) for r in FILES},
            "v5_dependencies_verified_against": str(V5_PINS.relative_to(REPO)),
            "v5_dependencies": {r: sha(r) for r in V5_DEPENDENCIES}}


def check(path: Path = MANIFEST) -> list[str]:
    if not path.exists():
        return [f"{path.name} missing: X1 Freeze Commit 1 has not been made"]
    m = json.loads(path.read_text())
    p = [f"{r} changed since freeze" for r, h in m["files"].items() if not (REPO / r).exists() or sha(r) != h]
    return p + v5_dependency_problems()


def _sha_path(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def phase_pin_record(plat: str, phase: str, root: Path = X1) -> dict:
    sys.path.insert(0, str(REPO / "scripts"))
    import freeze_x1_traces as fx

    d = root / plat
    rec = {"created_utc": datetime.now(UTC).isoformat(),
           "files": {str(f.relative_to(d)): _sha_path(f) for f in fx.phase_files(plat, phase, root)},
           "schedule": _sha_path(d / fx.SCHED_FILE[phase]), "traces": _sha_path(d / fx.TRACE_FILE[phase])}
    if phase in ("calB", "main"):
        rec["rates"] = _sha_path(d / "RATES.json")
    if phase == "main":
        rec["predictions"] = _sha_path(d / "FCFS_PREDICTIONS.json")
    return rec


def pin_phase_problems(plat: str, phase: str, *, root: Path = X1, reports_root: Path = REPORTS,
                       results_root: Path = REPO / "results") -> list[str]:
    """Preconditions for pinning a phase: Freeze 1 in place, the ordering rules, the phase's frozen files present."""
    sys.path.insert(0, str(REPO / "scripts"))
    import freeze_x1_traces as fx

    p = [x for x in check() if root == X1]          # Freeze 1 must exist for the canonical tree
    p += fx.ordering_problems(plat, phase, root=root, reports_root=reports_root, results_root=results_root)
    for name in (fx.SCHED_FILE[phase], fx.TRACE_FILE[phase]):
        if not (root / plat / name).exists():
            p.append(f"{name} missing (run scripts/freeze_x1_traces.py first)")
    if phase == "main" and not (root / plat / "FCFS_PREDICTIONS.json").exists():
        p.append("FCFS_PREDICTIONS.json missing (Freeze 3 pins predictions, rates and main traces together)")
    pins = root / plat / "PHASE_PINS.json"
    if pins.exists() and phase in json.loads(pins.read_text()):
        p.append(f"{plat}/{phase} already pinned (pins are never overwritten)")
    return p


def phase_pin_problems(plat: str, phase: str, *, root: Path = X1, reports_root: Path = REPORTS) -> list[str]:
    """Stage-driver check before ANY live block: pinned, unchanged since, and pinned before the phase's first run."""
    pins = root / plat / "PHASE_PINS.json"
    if not pins.exists() or phase not in json.loads(pins.read_text()):
        return [f"{plat}/{phase} is not pinned (traces must be frozen and pinned before any {phase} run)"]
    rec = json.loads(pins.read_text())[phase]
    d = root / plat
    p = [f"{rel} changed since the {phase} pin" for rel, h in rec["files"].items()
         if not (d / rel).exists() or _sha_path(d / rel) != h]
    sys.path.insert(0, str(REPO / "scripts"))
    import freeze_x1_traces as fx

    for key, name in (("schedule", fx.SCHED_FILE[phase]), ("traces", fx.TRACE_FILE[phase]), ("rates", "RATES.json"),
                      ("predictions", "FCFS_PREDICTIONS.json")):
        if key in rec and (not (d / name).exists() or _sha_path(d / name) != rec[key]):
            p.append(f"{name} changed since the {phase} pin")
    log = reports_root / plat / phase / "STAGE_LOG.json"
    if log.exists():
        started = json.loads(log.read_text()).get("started_utc")
        if started and started < rec["created_utc"]:
            p.append(f"{plat}/{phase} started ({started}) before its pin ({rec['created_utc']})")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--candidate", action="store_true")
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--pin-phase", nargs=2, metavar=("PLATFORM", "PHASE"))
    a = ap.parse_args()
    if a.pin_phase:
        plat, phase = a.pin_phase
        if os.environ.get("QUOTASHIFT_APPROVED") != f"x1_freeze_{phase}_{plat}":
            print(f"REFUSED: needs QUOTASHIFT_APPROVED=x1_freeze_{phase}_{plat} (owner approval)", file=sys.stderr)
            return 3
        probs = pin_phase_problems(plat, phase)
        if probs:
            print("REFUSED:\n  " + "\n  ".join(probs), file=sys.stderr)
            return 3
        pins = X1 / plat / "PHASE_PINS.json"
        allp = json.loads(pins.read_text()) if pins.exists() else {}
        allp[phase] = phase_pin_record(plat, phase)
        pins.write_text(json.dumps(allp, indent=1) + "\n")
        print(f"pinned {plat}/{phase}")
        return 0
    if a.check:
        p = check()
        print("X1 frozen artifacts match their pins" if not p else "MISMATCH:\n  " + "\n  ".join(p))
        return 0 if not p else 1
    dep = v5_dependency_problems()
    if dep:
        print("REFUSED:\n  " + "\n  ".join(dep), file=sys.stderr)
        return 3
    if a.write:
        if os.environ.get("QUOTASHIFT_APPROVED") != "x1_freeze1":
            print("REFUSED: Freeze Commit 1 needs QUOTASHIFT_APPROVED=x1_freeze1 (owner approval)", file=sys.stderr)
            return 3
        if MANIFEST.exists():
            print(f"REFUSED: {MANIFEST.relative_to(REPO)} exists (freezes are never overwritten)", file=sys.stderr)
            return 3
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(manifest("X1 Freeze Commit 1"), indent=1) + "\n")
        print(f"wrote {MANIFEST.relative_to(REPO)}")
        return 0
    CANDIDATE.parent.mkdir(parents=True, exist_ok=True)
    m = manifest("X1 freeze CANDIDATE (not a freeze; Freeze Commit 1 not executed)")
    CANDIDATE.write_text(json.dumps(m, indent=1) + "\n")
    print(f"wrote {CANDIDATE.relative_to(REPO)} ({len(m['files'])} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
