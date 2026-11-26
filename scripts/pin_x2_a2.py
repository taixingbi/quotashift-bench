"""X2 Amendment A2 pinning (DRAFT). The A2 freeze is NOT made by this commit.

    uv run python scripts/pin_x2_a2.py --candidate     # non-binding list -> reports/x2_a2/A2_CANDIDATE_SHA256.json
    QUOTASHIFT_APPROVED=x2_amend_a2 uv run python scripts/pin_x2_a2.py --write    # A2 freeze (owner approval only)
    uv run python scripts/pin_x2_a2.py --check         # A2 manifest + X2 Freeze 1 (+ v5, X1, A1) all verify
    QUOTASHIFT_APPROVED=x2a2_freeze_main_<p> uv run python scripts/pin_x2_a2.py --pin-phase <p> main

The A2 manifest pins the amendment document, the A2 arrival law, its generator/freeze/pin/stage/validation drivers and
the CLI loader dispatch. It never rewrites X2 Freeze 1: --write and --check require pin_x2.check() to pass (which also
re-verifies v5 and X1/A1). Phase pins use the frozen X2 record format (pin_x2.phase_pin_record) under
experiments/x2_a2/<p>/PHASE_PINS.json, so the frozen stage driver's pin check works on the A2 root unchanged.
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
sys.path.insert(0, str(REPO / "scripts"))
import pin_x2  # noqa: E402  (frozen)

A2 = REPO / "experiments" / "x2_a2"
MANIFEST = A2 / "AMENDMENT_A2_SHA256.json"
CANDIDATE = REPO / "reports" / "x2_a2" / "A2_CANDIDATE_SHA256.json"
FILES = (
    "docs/PROTOCOL_X2_AMENDMENT_A2.md",
    "src/quotashift/x2/arrivals_a2.py", "src/quotashift/cli.py",
    "scripts/build_x2_a2.py", "scripts/freeze_x2_a2_traces.py", "scripts/pin_x2_a2.py", "scripts/x2_a2_stage.py",
    "scripts/x2_a2_validate.py",
)


def manifest(kind: str) -> dict:
    return {"kind": kind, "created_utc": datetime.now(UTC).isoformat(), "files": {r: pin_x2.sha(r) for r in FILES},
            "x2_freeze1_manifest_sha256": hashlib.sha256(pin_x2.MANIFEST.read_bytes()).hexdigest(),
            "supersedes": "X2 rev 2 fixed-count competitor arrival law (iid Uniform, stream 101) for files that "
                          "declare protocol_amendment: X2-A2 only",
            "unchanged": "X2 Freeze 1 files, rates, seeds, repetitions, caps, budgets, thresholds (1.25), gates "
                         "(incl. arrival coverage 0.25/0.75), hypotheses, analysis"}


def check(path: Path = MANIFEST) -> list[str]:
    p = [f"X2 Freeze 1: {x}" for x in pin_x2.check()]
    if not path.exists():
        return p + [f"{path.name} missing: the A2 freeze has not been made"]
    m = json.loads(path.read_text())
    p += [f"{r} changed since the A2 freeze" for r, h in m["files"].items()
          if not (REPO / r).exists() or pin_x2.sha(r) != h]
    if m.get("x2_freeze1_manifest_sha256") != hashlib.sha256(pin_x2.MANIFEST.read_bytes()).hexdigest():
        p.append("X2 Freeze 1 manifest changed since the A2 freeze")
    return p


def pin_phase_problems(plat: str, phase: str) -> list[str]:
    import build_x2_a2
    import freeze_x2_a2_traces as fa
    import freeze_x2_traces as fx

    if phase != "main":
        return ["A2 covers the main phase only"]
    p = check()
    p += fa.ordering_problems(plat)
    p += build_x2_a2.check(plat)
    for name in (fx.SCHED_FILE[phase], fx.TRACE_FILE[phase]):
        f = A2 / plat / name
        if not f.exists():
            p.append(f"{name} missing (run scripts/freeze_x2_a2_traces.py first)")
        elif json.loads(f.read_text()).get("amendment", {}).get("protocol") != "X2-A2":
            p.append(f"{name} has no X2-A2 provenance")
    pins = A2 / plat / "PHASE_PINS.json"
    if pins.exists() and phase in json.loads(pins.read_text()):
        p.append(f"A2 {plat}/{phase} already pinned (pins are never overwritten)")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--candidate", action="store_true")
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--pin-phase", nargs=2, metavar=("PLATFORM", "PHASE"))
    a = ap.parse_args()
    if a.candidate:
        CANDIDATE.parent.mkdir(parents=True, exist_ok=True)
        CANDIDATE.write_text(json.dumps(manifest("X2 Amendment A2 CANDIDATE (not binding)"), indent=1) + "\n")
        print(f"wrote {CANDIDATE.relative_to(REPO)} ({len(FILES)} files)")
        return 0
    if a.write:
        if os.environ.get("QUOTASHIFT_APPROVED") != "x2_amend_a2":
            print("REFUSED: needs QUOTASHIFT_APPROVED=x2_amend_a2 (owner approval of the reviewed amendment)",
                  file=sys.stderr)
            return 3
        if MANIFEST.exists():
            print("REFUSED: the A2 manifest exists (written once)", file=sys.stderr)
            return 3
        if pin_x2.check():
            print("REFUSED: X2 Freeze 1 does not verify", file=sys.stderr)
            return 3
        MANIFEST.write_text(json.dumps(manifest("X2 Amendment A2 (stratified competitor arrivals)"), indent=1) + "\n")
        print(f"wrote {MANIFEST.relative_to(REPO)}")
        return 0
    if a.check:
        p = check()
        print("X2 Amendment A2 artifacts match their pins" if not p else "MISMATCH:\n  " + "\n  ".join(p))
        return 0 if not p else 1
    plat, phase = a.pin_phase
    if os.environ.get("QUOTASHIFT_APPROVED") != f"x2a2_freeze_{phase}_{plat}":
        print(f"REFUSED: needs QUOTASHIFT_APPROVED=x2a2_freeze_{phase}_{plat} (owner approval)", file=sys.stderr)
        return 3
    probs = pin_phase_problems(plat, phase)
    if probs:
        print("REFUSED:\n  " + "\n  ".join(probs), file=sys.stderr)
        return 3
    pins = A2 / plat / "PHASE_PINS.json"
    allp = json.loads(pins.read_text()) if pins.exists() else {}
    allp[phase] = pin_x2.phase_pin_record(plat, phase, root=A2) | {"amendment": "X2-A2"}
    pins.write_text(json.dumps(allp, indent=1) + "\n")
    print(f"pinned A2 {plat}/{phase}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
