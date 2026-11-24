"""Protocol v5 freeze pins (Freeze Commit 1): SHA-256 of every frozen artifact.

    uv run python scripts/pin_v5.py --write    # once, at Freeze Commit 1 (refuses if the manifest exists)
    uv run python scripts/pin_v5.py --check    # exit 1 on any mismatch, missing or unexpected frozen file

Pinned: the protocol text, every generated YAML (blocks + pre-generated reruns), the frozen schedule, the FCFS
predictions, the P1 host record, the generation/freeze/prediction/analysis/driver/export/P1 scripts (and the frozen v4
helpers they import), the v5 schema/metric/gate/instrumentation sources, and the v5 protocol tests. NOT pinned (by
design): runtime harness code (gateway, runner, simulator, HTTP client), which the protocol's stage-S rule requires to
stay fixable; every run records its git SHA. FROZEN_TRACES.json is added by Freeze Commit 2 and pinned there separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "experiments" / "v5" / "FROZEN_SHA256.json"
FIXED = [
    "docs/PROTOCOL_V5.md",
    "experiments/v5/FROZEN_SCHEDULE.json", "experiments/v5/FCFS_PREDICTIONS.json", "experiments/v5/HOST_VERIFICATION.json",
    "scripts/build_v5.py", "scripts/freeze_v5.py", "scripts/v5_fcfs_predictions.py", "scripts/v5_analysis.py",
    "scripts/v5_stage.py", "scripts/run_v5.sh", "scripts/export_v5_raw.py", "scripts/p1_host_evidence.py",
    "scripts/p1_verify_host.py", "scripts/pin_v5.py",
    "scripts/freeze_v4.py", "scripts/v4_posthoc_slot_time.py",          # frozen v4 helpers imported by v5 code
    "src/quotashift/scenario.py", "src/quotashift/evaluation/attack_effect.py", "src/quotashift/evaluation/validity.py",
    "src/quotashift/evaluation/occupancy.py", "src/quotashift/evaluation/metrics.py",
    "src/quotashift/instrumentation/engine_counters.py", "src/quotashift/workload/tokenize.py",
    "tests/unit/test_v5_protocol.py", "tests/unit/test_v5_rev3_consistency.py", "tests/unit/test_export_v5_raw.py",
    "tests/unit/test_p1_host.py",
]


def frozen_files() -> list[str]:
    yamls = sorted(str(p.relative_to(REPO)) for p in (REPO / "experiments" / "v5").rglob("*.yaml"))
    return sorted(set(FIXED) | set(yamls))


def sha(path: str) -> str:
    return hashlib.sha256((REPO / path).read_bytes()).hexdigest()


def check() -> list[str]:
    man = json.loads(MANIFEST.read_text())
    pins = man["files"]
    probs = [f"changed: {p}" for p, h in pins.items() if not (REPO / p).exists() or sha(p) != h]
    probs += [f"unpinned frozen file: {p}" for p in frozen_files() if p not in pins]
    return probs


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        p = check()
        print("all frozen artifacts match their pins" if not p else "PIN MISMATCH:\n  " + "\n  ".join(p))
        return 0 if not p else 1
    if MANIFEST.exists():
        print(f"refusing to overwrite {MANIFEST.relative_to(REPO)} (frozen)", file=sys.stderr)
        return 3
    parent = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    files = {p: sha(p) for p in frozen_files()}
    MANIFEST.write_text(json.dumps({"freeze": "Protocol v5 Freeze Commit 1", "created_utc": datetime.now(UTC).isoformat(),
                                    "parent_commit": parent, "n_files": len(files), "files": files,
                                    "not_pinned": "runtime harness code (see module docstring); FROZEN_TRACES.json is "
                                                  "pinned by Freeze Commit 2"}, indent=1) + "\n")
    print(f"pinned {len(files)} files -> {MANIFEST.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
