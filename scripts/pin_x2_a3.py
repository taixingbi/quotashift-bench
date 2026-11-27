"""X2 Amendment A3 pinning (DRAFT). The A3 freeze is NOT made by the draft commit.

    uv run python scripts/pin_x2_a3.py --candidate     # non-binding list -> reports/x2_a3/A3_CANDIDATE_SHA256.json
    QUOTASHIFT_APPROVED=x2_amend_a3 uv run python scripts/pin_x2_a3.py --write    # A3 freeze (owner approval only)
    uv run python scripts/pin_x2_a3.py --check         # A3 manifest + A2 + X2 Freeze 1 + v5 (+ X1, A1) all verify

The A3 manifest pins the amendment document, the sequential counter, its env-gated activation hook, the A3 driver,
this script and the offline validation. It never rewrites an earlier manifest: --write and --check require the A2
check (which re-verifies X2 Freeze 1, the v5 dependencies and X1/A1) and the full v5 check (the frozen counter
src/quotashift/workload/tokenize.py is a v5 pin) to pass, and record each earlier manifest's SHA-256.
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
import pin_v5  # noqa: E402  (frozen)
import pin_x2  # noqa: E402  (frozen)
import pin_x2_a2  # noqa: E402  (frozen by A2)

A3 = REPO / "experiments" / "x2_a3"
MANIFEST = A3 / "AMENDMENT_A3_SHA256.json"
CANDIDATE = REPO / "reports" / "x2_a3" / "A3_CANDIDATE_SHA256.json"
FILES = (
    "docs/PROTOCOL_X2_AMENDMENT_A3.md",
    "src/quotashift/workload/tokenize_a3.py", "src/quotashift/workload/__init__.py",
    "scripts/x2_a3.py", "scripts/pin_x2_a3.py", "scripts/x2_a3_validate.py",
)
EARLIER = ("experiments/v5/FROZEN_SHA256.json", "experiments/x2/FROZEN_SHA256.json",
           "experiments/x2_a2/AMENDMENT_A2_SHA256.json", "experiments/x1/FROZEN_SHA256.json",
           "experiments/x1/AMENDMENT_A1_SHA256.json")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def earlier_problems() -> list[str]:
    p = [f"v5: {x}" for x in pin_v5.check()]
    p += [f"A2: {x}" for x in pin_x2_a2.check()]     # includes X2 Freeze 1, v5 dependencies, X1 + A1
    return p


def manifest(kind: str) -> dict:
    return {"kind": kind, "created_utc": datetime.now(UTC).isoformat(), "files": {r: pin_x2.sha(r) for r in FILES},
            "earlier_manifests_sha256": {r: _sha(REPO / r) for r in EARLIER},
            "scope": "Mistral models only (quotashift.workload.tokenize_a3.A3_MODELS); process-local, activated by "
                     "QUOTASHIFT_TOKEN_COUNTER=X2-A3 set by scripts/x2_a3.py",
            "supersedes": "the 16-worker concurrent /tokenize fan-out of the frozen VllmTokenizer, for A3 models in "
                          "A3-activated processes only",
            "unchanged": "every byte of the v5, X2 Freeze 1, X2-A2, X1, A1 artifacts; Mistral revision and vLLM "
                         "flags; prompts, request shapes, seeds, arrival laws, rates, SLOs, thresholds (1.25), "
                         "gates, hypotheses, Holm family, analysis; exact-token equality; Qwen counting"}


def check(path: Path = MANIFEST) -> list[str]:
    p = earlier_problems()
    if not path.exists():
        return p + [f"{path.name} missing: the A3 freeze has not been made"]
    m = json.loads(path.read_text())
    p += [f"{r} changed since the A3 freeze" for r, h in m["files"].items()
          if not (REPO / r).exists() or pin_x2.sha(r) != h]
    p += [f"earlier manifest {r} changed since the A3 freeze" for r, h in m["earlier_manifests_sha256"].items()
          if _sha(REPO / r) != h]
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--candidate", action="store_true")
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        p = check()
        print("X2 Amendment A3 artifacts match their pins" if not p else "MISMATCH:\n  " + "\n  ".join(p))
        return 0 if not p else 1
    p = earlier_problems()
    if p:
        print("REFUSED (an earlier freeze does not verify):\n  " + "\n  ".join(p), file=sys.stderr)
        return 3
    if a.candidate:
        CANDIDATE.parent.mkdir(parents=True, exist_ok=True)
        CANDIDATE.write_text(json.dumps(manifest("X2 Amendment A3 CANDIDATE (non-binding)"), indent=1) + "\n")
        print(f"wrote {CANDIDATE.relative_to(REPO)}")
        return 0
    if os.environ.get("QUOTASHIFT_APPROVED") != "x2_amend_a3":
        print("REFUSED: needs QUOTASHIFT_APPROVED=x2_amend_a3 (owner approval)", file=sys.stderr)
        return 3
    if MANIFEST.exists():
        print(f"refusing to overwrite {MANIFEST.relative_to(REPO)} (frozen)", file=sys.stderr)
        return 3
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest("X2 Amendment A3 (sequential Mistral token counting)"), indent=1) + "\n")
    print(f"pinned {len(FILES)} files -> {MANIFEST.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
