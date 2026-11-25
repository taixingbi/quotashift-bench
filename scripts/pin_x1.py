"""X1 artifact pinning (rev 4 section 10, stage X1-G).

    uv run python scripts/pin_x1.py --candidate      # non-binding freeze CANDIDATE list -> reports/x1/FREEZE_CANDIDATE_SHA256.json
    QUOTASHIFT_APPROVED=x1_freeze1 uv run python scripts/pin_x1.py --write   # Freeze Commit 1 (owner-approved only)
    uv run python scripts/pin_x1.py --check          # verify experiments/x1/FROZEN_SHA256.json (live runs require it)

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
    "scripts/x1_host_sampler.py", "scripts/pin_x1.py",
    "src/quotashift/x1/__init__.py", "src/quotashift/x1/preflight.py", "src/quotashift/x1/tokenize_probe.py",
    "src/quotashift/x1/export_gate.py",
)
V5_DEPENDENCIES = ("scripts/v5_analysis.py", "scripts/v5_fcfs_predictions.py", "scripts/build_v5.py",
                   "scripts/v5_stage.py")


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--candidate", action="store_true")
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args()
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
