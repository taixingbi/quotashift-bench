"""X2 artifact pinning (docs/PROTOCOL_X2_DRAFT.md rev 2 section 8). X2 Freeze Commit 1 is NOT executed.

    uv run python scripts/pin_x2.py --candidate      # non-binding CANDIDATE list -> reports/x2/FREEZE_CANDIDATE_SHA256.json
    QUOTASHIFT_APPROVED=x2_freeze1 uv run python scripts/pin_x2.py --write   # X2 Freeze Commit 1 (owner approval only)
    uv run python scripts/pin_x2.py --check          # verify experiments/x2/FROZEN_SHA256.json (live X2 runs require it)
    QUOTASHIFT_APPROVED=x2_freeze_<phase>_<plat> uv run python scripts/pin_x2.py --pin-phase <plat> <phase>

Freeze 1 pins the X2 protocol, instrumentation spec, sizing, generator, drivers, rules and analysis. It never touches
X1 or v5: --candidate, --write and --check also require the frozen v5 modules X2 imports to equal
experiments/v5/FROZEN_SHA256.json, and the X1 manifests (Freeze 1, Amendment A1) to still verify, so X2 cannot run on a
changed v5 rule and cannot be used to disturb X1's record.
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
MANIFEST = REPO / "experiments" / "x2" / "FROZEN_SHA256.json"
CANDIDATE = REPO / "reports" / "x2" / "FREEZE_CANDIDATE_SHA256.json"
V5_PINS = REPO / "experiments" / "v5" / "FROZEN_SHA256.json"
FILES = (
    "docs/PROTOCOL_X2_DRAFT.md", "docs/X2_INSTRUMENTATION_SPEC.md", "docs/X2_HOST_AUDIT.md",
    "scripts/build_x2.py", "scripts/x2_stage.py", "scripts/x2_qualify.py", "scripts/x2_select_rates.py",
    "scripts/x2_analysis.py", "scripts/freeze_x2_traces.py", "scripts/pin_x2.py", "scripts/x2_host_snapshot.py",
    "scripts/x2_q1_power.py", "reports/x2/Q1_POWER.json", "scripts/x2_verdict_power.py", "reports/x2/VERDICT_POWER.json",
    "src/quotashift/x2/__init__.py", "src/quotashift/x2/snapshot.py", "src/quotashift/x2/qualification.py",
    "src/quotashift/local.py",
    "configs/targets/x2-g0-qwen.yaml", "configs/targets/x2-g0-mistral.yaml",
    "configs/targets/x2-g1-qwen.yaml", "configs/targets/x2-g1-mistral.yaml",
    "infra/terraform/envs/research.x2.tfvars",
)
V5_DEPENDENCIES = ("scripts/v5_analysis.py", "scripts/build_v5.py", "scripts/v5_stage.py", "scripts/freeze_v5.py",
                   "scripts/freeze_v4.py")
X2 = REPO / "experiments" / "x2"
REPORTS = REPO / "reports" / "x2"


def sha(rel: str) -> str:
    return hashlib.sha256((REPO / rel).read_bytes()).hexdigest()


def v5_dependency_problems() -> list[str]:
    pins = json.loads(V5_PINS.read_text())
    pins = pins.get("files", pins)
    return [f"v5 dependency {r} changed since the v5 freeze" for r in V5_DEPENDENCIES if pins.get(r) != sha(r)]


def x1_problems() -> list[str]:
    """X1's frozen record must remain intact (Freeze 1 + Amendment A1, which also re-verifies Freeze 1 and v5)."""
    sys.path.insert(0, str(REPO / "scripts"))
    import pin_x1_amendment
    return [f"X1: {x}" for x in pin_x1_amendment.check()]


def manifest(kind: str) -> dict:
    return {"kind": kind, "created_utc": datetime.now(UTC).isoformat(), "files": {r: sha(r) for r in FILES},
            "v5_dependencies": {r: sha(r) for r in V5_DEPENDENCIES},
            "v5_manifest_sha256": hashlib.sha256(V5_PINS.read_bytes()).hexdigest(),
            "x1_manifests_sha256": {p: hashlib.sha256((REPO / p).read_bytes()).hexdigest() for p in
                                    ("experiments/x1/FROZEN_SHA256.json", "experiments/x1/AMENDMENT_A1_SHA256.json")}}


def check(path: Path = MANIFEST) -> list[str]:
    if not path.exists():
        return [f"{path.name} missing: X2 Freeze Commit 1 has not been made"]
    m = json.loads(path.read_text())
    p = [f"{r} changed since freeze" for r, h in m["files"].items() if not (REPO / r).exists() or sha(r) != h]
    return p + v5_dependency_problems() + x1_problems()


def _sha_path(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def phase_pin_record(plat: str, phase: str, root: Path = X2) -> dict:
    sys.path.insert(0, str(REPO / "scripts"))
    import freeze_x2_traces as fx

    d = root / plat
    rec = {"created_utc": datetime.now(UTC).isoformat(),
           "files": {str(f.relative_to(d)): _sha_path(f) for f in fx.phase_files(plat, phase, root)},
           "schedule": _sha_path(d / fx.SCHED_FILE[phase]), "traces": _sha_path(d / fx.TRACE_FILE[phase]),
           "qualification": _sha_path(d / "QUALIFICATION.json")}
    if phase == "main":
        rec["rates"] = _sha_path(d / "RATES.json")
    return rec


def pin_phase_problems(plat: str, phase: str, *, root: Path = X2, reports_root: Path = REPORTS,
                       results_root: Path = REPO / "results") -> list[str]:
    sys.path.insert(0, str(REPO / "scripts"))
    import freeze_x2_traces as fx

    p = [x for x in check() if root == X2]
    p += fx.ordering_problems(plat, phase, root=root, reports_root=reports_root, results_root=results_root)
    for name in (fx.SCHED_FILE[phase], fx.TRACE_FILE[phase]):
        if not (root / plat / name).exists():
            p.append(f"{name} missing (run scripts/freeze_x2_traces.py first)")
    pins = root / plat / "PHASE_PINS.json"
    if pins.exists() and phase in json.loads(pins.read_text()):
        p.append(f"{plat}/{phase} already pinned (pins are never overwritten)")
    return p


def phase_pin_problems(plat: str, phase: str, *, root: Path = X2, reports_root: Path = REPORTS) -> list[str]:
    """Stage-driver check before ANY live block: pinned, unchanged since, and pinned before the phase's first run."""
    pins = root / plat / "PHASE_PINS.json"
    if not pins.exists() or phase not in json.loads(pins.read_text()):
        return [f"{plat}/{phase} is not pinned (traces must be frozen and pinned before any {phase} run)"]
    rec = json.loads(pins.read_text())[phase]
    d = root / plat
    p = [f"{rel} changed since the {phase} pin" for rel, h in rec["files"].items()
         if not (d / rel).exists() or _sha_path(d / rel) != h]
    sys.path.insert(0, str(REPO / "scripts"))
    import freeze_x2_traces as fx

    for key, name in (("schedule", fx.SCHED_FILE[phase]), ("traces", fx.TRACE_FILE[phase]), ("rates", "RATES.json"),
                      ("qualification", "QUALIFICATION.json")):
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
        if os.environ.get("QUOTASHIFT_APPROVED") != f"x2_freeze_{phase}_{plat}":
            print(f"REFUSED: needs QUOTASHIFT_APPROVED=x2_freeze_{phase}_{plat} (owner approval)", file=sys.stderr)
            return 3
        probs = pin_phase_problems(plat, phase)
        if probs:
            print("REFUSED:\n  " + "\n  ".join(probs), file=sys.stderr)
            return 3
        pins = X2 / plat / "PHASE_PINS.json"
        allp = json.loads(pins.read_text()) if pins.exists() else {}
        allp[phase] = phase_pin_record(plat, phase)
        pins.write_text(json.dumps(allp, indent=1) + "\n")
        print(f"pinned {plat}/{phase}")
        return 0
    if a.check:
        p = check()
        print("X2 frozen artifacts match their pins" if not p else "MISMATCH:\n  " + "\n  ".join(p))
        return 0 if not p else 1
    dep = v5_dependency_problems() + x1_problems()
    if dep:
        print("REFUSED:\n  " + "\n  ".join(dep), file=sys.stderr)
        return 3
    if a.write:
        if os.environ.get("QUOTASHIFT_APPROVED") != "x2_freeze1":
            print("REFUSED: X2 Freeze Commit 1 needs QUOTASHIFT_APPROVED=x2_freeze1 (owner approval)", file=sys.stderr)
            return 3
        if MANIFEST.exists():
            print(f"REFUSED: {MANIFEST.relative_to(REPO)} exists (freezes are never overwritten)", file=sys.stderr)
            return 3
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(manifest("X2 Freeze Commit 1"), indent=1) + "\n")
        print(f"wrote {MANIFEST.relative_to(REPO)}")
        return 0
    missing = [r for r in FILES if not (REPO / r).exists()]
    if missing:
        print(f"REFUSED: candidate files missing: {missing}", file=sys.stderr)
        return 3
    CANDIDATE.parent.mkdir(parents=True, exist_ok=True)
    m = manifest("X2 freeze CANDIDATE (not a freeze; X2 Freeze Commit 1 not executed)")
    CANDIDATE.write_text(json.dumps(m, indent=1) + "\n")
    print(f"wrote {CANDIDATE.relative_to(REPO)} ({len(m['files'])} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
