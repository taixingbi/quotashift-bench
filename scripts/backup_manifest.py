"""Off-machine backup MANIFEST (names, sizes, SHA-256 only; never contents) for git-ignored evidence and archives.

    uv run python scripts/backup_manifest.py            # -> reports/backup/BACKUP_MANIFEST.json (+ printed totals)
    uv run python scripts/backup_manifest.py --verify <manifest> --root <restored copy>   # after the owner's copy

Covers (docs/BACKUP_PLAN.md): X1 raw evidence (reports/x1/g0m0/**, results/x1_*), v5 raw results referenced by the
v5 archives, and the archives already under ~/QuotaShift-backups/. Committed records are in git and are not listed.
The manifest holds relative paths only (archives as "~/QuotaShift-backups/<name>"); no file content is read beyond
hashing, and nothing is uploaded anywhere: the off-machine copy is an owner action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "reports" / "backup" / "BACKUP_MANIFEST.json"
BACKUPS = Path.home() / "QuotaShift-backups"
SETS = {
    "x1_raw_evidence": [REPO / "reports" / "x1" / "g0m0"],
    "x2_raw_evidence": sorted((REPO / "reports" / "x2").glob("g[01]m[01]")) + [REPO / "results" / "aws"],
    "x1_results": sorted((REPO / "results").glob("x1_*")) if (REPO / "results").exists() else [],
    "archives": [BACKUPS],
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(REPO))
    except ValueError:
        return "~/" + str(p.relative_to(Path.home()))


def build() -> dict:
    out: dict = {"created_utc": datetime.now(UTC).isoformat(), "note": "names, sizes and SHA-256 only; no contents",
                 "sets": {}}
    for name, roots in SETS.items():
        files = []
        for r in roots:
            if not r.exists():
                continue
            for p in sorted(x for x in (r.rglob("*") if r.is_dir() else [r]) if x.is_file()):
                files.append({"path": rel(p), "bytes": p.stat().st_size, "sha256": sha256(p)})
        out["sets"][name] = {"files": files, "n": len(files), "bytes": sum(f["bytes"] for f in files)}
    return out


def verify(manifest: Path, root: Path) -> list[str]:
    m = json.loads(manifest.read_text())
    bad = []
    for s in m["sets"].values():
        for f in s["files"]:
            p = root / f["path"].removeprefix("~/")
            if not p.exists() or sha256(p) != f["sha256"]:
                bad.append(f["path"])
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify")
    ap.add_argument("--root")
    a = ap.parse_args()
    if a.verify:
        bad = verify(Path(a.verify), Path(a.root))
        print("all files verified" if not bad else f"{len(bad)} missing or changed, e.g. {bad[:5]}")
        return 0 if not bad else 1
    m = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(m, indent=1) + "\n")
    for k, v in m["sets"].items():
        print(f"{k}: {v['n']} files, {v['bytes'] / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
