"""X1 Amendment A1 pinning: a SEPARATE manifest; Freeze Commit 1 (experiments/x1/FROZEN_SHA256.json) is never touched.

    QUOTASHIFT_APPROVED=x1_amend_a1 uv run python scripts/pin_x1_amendment.py --write   # owner-approved only, once
    uv run python scripts/pin_x1_amendment.py --check

--write refuses unless Freeze Commit 1 and the v5 pins still verify (pin_x1.check) and the manifest does not exist.
It pins the amendment text, the reviewed proposal (02eafae), the candidate rule, the sizing simulation and its output,
the Phase 1 driver that implements A1, this script, and both failed g0m0 Phase 1 records (immutable history).
--check verifies every pinned file AND Freeze Commit 1 + v5. The Phase 1 driver refuses to run unless --check passes.
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
import pin_x1  # noqa: E402  (frozen; imported unchanged)

MANIFEST = REPO / "experiments" / "x1" / "AMENDMENT_A1_SHA256.json"
TOKEN = "x1_amend_a1"
REVIEWED_PROPOSAL_COMMIT = "02eafae"
FILES = (
    "docs/PROTOCOL_X1_AMENDMENT_A1.md",
    "docs/X1_AMENDMENT_A1_SAMPLER_EQUIVALENCE.md",
    "src/quotashift/x1/sampler_equivalence_a1.py",
    "scripts/x1_amendment_a1_power.py",
    "reports/x1/AMENDMENT_A1_POWER.json",
    "scripts/x1_preflight.py",
    "scripts/pin_x1_amendment.py",
    "experiments/x1/g0m0/HOST_VERIFICATION.attempt1.json",
    "experiments/x1/g0m0/HOST_VERIFICATION.attempt2.json",
)


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def manifest_sha(path: Path = MANIFEST) -> str | None:
    return sha_file(path) if path.exists() else None


def check(path: Path = MANIFEST, repo: Path = REPO) -> list[str]:
    if not path.exists():
        return [f"{path.name} missing: Amendment A1 has not been pinned"]
    m = json.loads(path.read_text())
    p = [f"{r} changed since the A1 pin" for r, h in m["files"].items()
         if not (repo / r).exists() or sha_file(repo / r) != h]
    if m.get("freeze1_manifest_sha256") != sha_file(pin_x1.MANIFEST):
        p.append("experiments/x1/FROZEN_SHA256.json differs from the one verified at the A1 pin")
    return p + pin_x1.check()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        probs = check()
        print("\n".join(probs) if probs else "Amendment A1 pins, X1 Freeze Commit 1 and v5 pins all match")
        return 1 if probs else 0
    if os.environ.get("QUOTASHIFT_APPROVED") != TOKEN:
        print(f"REFUSED: pinning Amendment A1 needs QUOTASHIFT_APPROVED={TOKEN} (owner approval)", file=sys.stderr)
        return 3
    if MANIFEST.exists():
        print(f"REFUSED: {MANIFEST.relative_to(REPO)} exists (pins are never overwritten)", file=sys.stderr)
        return 3
    base = pin_x1.check()
    if base:
        print("REFUSED: X1 Freeze Commit 1 / v5 pins do not verify:\n  " + "\n  ".join(base), file=sys.stderr)
        return 3
    missing = [r for r in FILES if not (REPO / r).exists()]
    if missing:
        print(f"REFUSED: missing {missing}", file=sys.stderr)
        return 3
    m = {"kind": "X1 Amendment A1 (post hoc, 2026-11-25): sampler on/off equivalence", "approval": TOKEN,
         "reviewed_proposal_commit": REVIEWED_PROPOSAL_COMMIT, "created_utc": datetime.now(UTC).isoformat(),
         "files": {r: sha_file(REPO / r) for r in FILES},
         "freeze1_manifest_sha256": sha_file(pin_x1.MANIFEST),
         "v5_manifest_sha256": sha_file(pin_x1.V5_PINS),
         "supersedes": "rev 4 section 9.1 row 'Sampler on/off equivalence', for Phase 1 runs started after this pin only",
         "unchanged": "frozen protocol file, preflight.py thresholds incl. sampler_overhead < 1% core, seeds, hypotheses, "
                      "families, predictions, analysis; attempts 1 and 2 remain FAIL"}
    MANIFEST.write_text(json.dumps(m, indent=1) + "\n")
    print(f"wrote {MANIFEST.relative_to(REPO)} ({len(FILES)} files); sha256 {sha_file(MANIFEST)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
