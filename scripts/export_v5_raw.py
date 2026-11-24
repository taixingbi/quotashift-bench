"""Sanitized raw-data export with SHA-256 verification (PROTOCOL_V5_DRAFT §9 item 11; docs/RAW_DATA_AUDIT.md §2–§3).

    uv run python scripts/export_v5_raw.py export --stage A --salt-file ~/.config/quotashift/export_salt
    uv run python scripts/export_v5_raw.py verify --manifest reports/v5/RAW_DATA_MANIFEST_A.json \
        --tar reports/v5/export/quotashift-v5-A.tar.gz

Read-only on reports/ and results/. For one stage it collects every file under the stage's report dir and every run
dir those reports reference, sanitizes them into a staging tree, refuses to package if any forbidden pattern survives
(the regex gate), then writes a deterministic tarball and a manifest listing each file's path, size and SHA-256 plus
the tarball's SHA-256. The manifest is small and meant for git; the tarball is a release asset (git-ignored).

Sanitization (rules version 1):
  1. paths:   every source report / run dir -> its export-relative path; the repo root -> relative; any other
              /Users/<u> or /home/<u> prefix -> ~
  2. hosts:   each target profile's backend/exporter host -> the profile name (e.g. `selfhost`); any other RFC1918
              IPv4 address -> <rfc1918>
  3. GPU ids: values of `uuid` and `pci_bus_id` in any `gpu` block -> gpu-<12 hex> (HMAC-SHA256 with a per-project
              salt kept outside the repo), replaced everywhere they occur, so "same device" stays comparable
  4. dropped: vllm_env keys containing CACHE; system_env.{pip_packages, conda_packages, env_vars}
Parquet string columns get rules 1–3. PNG files are copied unchanged (and byte-scanned by the gate). Every other file
is treated as UTF-8 text whatever its extension; a file that is neither refuses the export. Nothing else is altered.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import tarfile
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import yaml

REPO = Path(__file__).resolve().parents[1]
RULES_VERSION = 1
TEXT_EXT = {".json", ".jsonl", ".csv", ".md", ".yaml", ".yml", ".txt", ".log", ".prom"}
BINARY_EXT = {".png"}   # copied unchanged; checked as bytes. Any other type must decode as UTF-8 text, or the export
                        # refuses (fail closed: an unknown file type is never copied unsanitized or skipped by the gate)
STAGE_DIRS = {"smoke": "smoke", "A": "stage_a", "B": "stage_b"}
RFC1918 = re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b")
HOME = re.compile(r"/(?:Users|home)/[^/\s\"',]+")
FORBIDDEN = {
    "home_path": re.compile(r"/(?:Users|home)/"),
    "rfc1918": RFC1918,
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "aws_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "hf_token": re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    "sk_key": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
}
DROP_SYSTEM_ENV = ("pip_packages", "conda_packages", "env_vars")


# ---------------------------------------------------------------- collection
def _resolve(d: str) -> Path:
    p = Path(d)
    if p.exists():
        return p
    i = p.parts.index("results") if "results" in p.parts else None
    return REPO.joinpath(*p.parts[i:]) if i is not None else p


def collect(reports: Path) -> dict[Path, str]:
    """source file -> export-relative path. Reports under reports/<cell>/..., runs under results/<exp>/<run>/..."""
    out: dict[Path, str] = {}
    for f in sorted(p for p in reports.rglob("*") if p.is_file()):
        out[f] = f"reports/{f.relative_to(reports).as_posix()}"
    for man in sorted(reports.glob("*/manifest.json")):
        for by_seed in (json.loads(man.read_text()).get("run_dirs") or {}).values():
            for d in by_seed.values():
                run = _resolve(d)
                for f in sorted(p for p in run.rglob("*") if p.is_file()):
                    out[f] = f"results/{run.parent.name}/{run.name}/{f.relative_to(run).as_posix()}"
    return out


def path_map(reports: Path, files: dict[Path, str]) -> list[tuple[str, str]]:
    """Literal absolute-path replacements, longest first (rule 1)."""
    m: dict[str, str] = {str(reports.resolve()): "reports", str(reports): "reports"}
    for man in reports.glob("*/manifest.json"):
        for by_seed in (json.loads(man.read_text()).get("run_dirs") or {}).values():
            for d in by_seed.values():
                run = _resolve(d)
                rel = f"results/{run.parent.name}/{run.name}"
                m[d], m[str(run)], m[str(run.resolve())] = rel, rel, rel
    m[str(REPO) + "/"] = ""
    return sorted(m.items(), key=lambda kv: -len(kv[0]))


def target_hosts() -> dict[str, str]:
    """Rule 2: host -> profile name, from configs/targets/*.yaml (every URL field)."""
    out: dict[str, str] = {}
    for f in sorted((REPO / "configs" / "targets").glob("*.yaml")):
        d = yaml.safe_load(f.read_text()) or {}
        name = d.get("name") or f.stem
        for k, v in d.items():
            if isinstance(v, str) and k.endswith("url") and v.startswith("http"):
                h = urlparse(v).hostname
                if h and h not in ("localhost", "127.0.0.1"):
                    out[h] = name
    return out


def gpu_ids(files: dict[Path, str]) -> set[str]:
    """Rule 3 inputs: `uuid` / `pci_bus_id` values found in any `gpu` block of any JSON file."""
    ids: set[str] = set()

    def walk(o: object, in_gpu: bool = False) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if in_gpu and k in ("uuid", "pci_bus_id") and isinstance(v, str) and v:
                    ids.add(v)
                walk(v, in_gpu or k == "gpu")
        elif isinstance(o, list):
            for v in o:
                walk(v, in_gpu)
    for f in files:
        if f.suffix == ".json":
            try:
                walk(json.loads(f.read_text()))
            except (ValueError, UnicodeDecodeError):
                continue
    return ids


# ---------------------------------------------------------------- sanitization
class Sanitizer:
    def __init__(self, paths: list[tuple[str, str]], hosts: dict[str, str], gpu: set[str], salt: bytes) -> None:
        self.paths, self.hosts = paths, sorted(hosts.items(), key=lambda kv: -len(kv[0]))
        self.gpu = {g: "gpu-" + hmac.new(salt, g.encode(), hashlib.sha256).hexdigest()[:12] for g in sorted(gpu, key=len, reverse=True)}
        self.counts: dict[str, int] = {"paths": 0, "home": 0, "hosts": 0, "rfc1918": 0, "gpu_ids": 0, "dropped_keys": 0}

    def text(self, s: str) -> str:
        for a, b in self.paths:
            if a and a in s:
                self.counts["paths"] += s.count(a)
                s = s.replace(a, b)
        s, n = HOME.subn("~", s)
        self.counts["home"] += n
        for h, name in self.hosts:
            if h in s:
                self.counts["hosts"] += s.count(h)
                s = s.replace(h, name)
        s, n = RFC1918.subn("<rfc1918>", s)
        self.counts["rfc1918"] += n
        for g, r in self.gpu.items():
            if g in s:
                self.counts["gpu_ids"] += s.count(g)
                s = s.replace(g, r)
        return s

    def drop(self, o: object, parent: str = "") -> object:
        if isinstance(o, dict):
            out = {}
            for k, v in o.items():
                if (parent == "vllm_env" and "CACHE" in k) or (parent == "system_env" and k in DROP_SYSTEM_ENV):
                    self.counts["dropped_keys"] += 1
                    continue
                out[k] = self.drop(v, k)
            return out
        if isinstance(o, list):
            return [self.drop(v, parent) for v in o]
        return o

    def file(self, src: Path) -> bytes:
        raw = src.read_bytes()
        if src.suffix == ".parquet":
            df = pd.read_parquet(io.BytesIO(raw))
            changed = False
            for c in df.columns:
                if df[c].dtype == object:
                    new = df[c].map(lambda v: self.text(v) if isinstance(v, str) else v)
                    if not new.equals(df[c]):
                        df[c], changed = new, True
            if not changed:
                return raw
            buf = io.BytesIO()
            df.to_parquet(buf, index=False)
            return buf.getvalue()
        if src.suffix in BINARY_EXT:
            return raw
        try:
            s = raw.decode()
        except UnicodeDecodeError as e:
            raise SystemExit(f"REFUSED: {src} is neither a known binary type nor UTF-8 text; extend the rules") from e
        if src.suffix == ".json":
            try:
                obj = json.loads(s)
            except ValueError:
                return self.text(s).encode()
            dropped = self.drop(obj)
            if dropped != obj:
                s = json.dumps(dropped, indent=1)
        return self.text(s).encode()


def gate(data: bytes, suffix: str, extra: set[str]) -> list[str]:
    """Regex gate on an exported file: names of every forbidden pattern still present (empty = clean)."""
    if suffix == ".parquet":
        df = pd.read_parquet(io.BytesIO(data))
        text = "\n".join(str(v) for c in df.columns if df[c].dtype == object for v in df[c].dropna())
    elif suffix in BINARY_EXT:
        text = data.decode("latin-1")   # byte-level scan: an embedded path, IP or id is still caught
    else:
        text = data.decode(errors="replace")
    hits = [k for k, rx in FORBIDDEN.items() if rx.search(text)]
    hits += ["gpu_id"] if any(g in text for g in extra) else []
    return hits


# ---------------------------------------------------------------- package / verify
def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def deterministic_tar(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz, tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name in sorted(entries):
            ti = tarfile.TarInfo(name)
            ti.size, ti.mtime, ti.mode, ti.uid, ti.gid, ti.uname, ti.gname = len(entries[name]), 0, 0o644, 0, 0, "", ""
            tar.addfile(ti, io.BytesIO(entries[name]))
    return buf.getvalue()


def load_salt(path: Path) -> bytes:
    path = path.expanduser().resolve()
    if path == REPO or REPO in path.parents:
        raise SystemExit("the export salt must live outside the repository")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32))
        os.chmod(path, 0o600)
    return path.read_text().strip().encode()


def export(stage: str, reports: Path, out: Path, manifest_path: Path, salt: bytes) -> dict:
    files = collect(reports)
    if not files:
        raise SystemExit(f"nothing to export under {reports}")
    ids = gpu_ids(files)
    san = Sanitizer(path_map(reports, files), target_hosts(), ids, salt)
    entries: dict[str, bytes] = {}
    for src, rel in files.items():
        entries[f"quotashift-v5-{stage}/{rel}"] = san.file(src)
    bad = {n: h for n, b in entries.items() if (h := gate(b, Path(n).suffix, ids))}
    if bad:
        raise SystemExit(f"REFUSED: regex gate failed on {len(bad)} file(s), e.g. {next(iter(bad.items()))}; nothing written")
    tar = deterministic_tar(entries)
    out.mkdir(parents=True, exist_ok=True)
    tar_path = out / f"quotashift-v5-{stage}.tar.gz"
    tar_path.write_bytes(tar)
    man = {"stage": stage, "rules_version": RULES_VERSION, "tarball": tar_path.name, "tarball_sha256": sha256(tar),
           "tarball_bytes": len(tar), "n_files": len(entries), "sanitization_counts": san.counts,
           "release_asset_url": None,
           "files": [{"path": n, "bytes": len(b), "sha256": sha256(b)} for n, b in sorted(entries.items())]}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(man, indent=1) + "\n")
    return man


def verify(manifest_path: Path, tar_path: Path) -> list[str]:
    """Mismatches between the manifest and the tarball (empty = verified)."""
    man = json.loads(manifest_path.read_text())
    raw = tar_path.read_bytes()
    problems = [] if sha256(raw) == man["tarball_sha256"] else [f"tarball sha256 {sha256(raw)[:12]} != manifest"]
    want = {f["path"]: f for f in man["files"]}
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tar:
        for m in tar.getmembers():
            fh = tar.extractfile(m)
            b = fh.read() if fh else b""
            seen.add(m.name)
            w = want.get(m.name)
            if w is None:
                problems.append(f"unexpected member {m.name}")
            elif w["sha256"] != sha256(b) or w["bytes"] != len(b):
                problems.append(f"content mismatch {m.name}")
    problems += [f"missing member {p}" for p in sorted(set(want) - seen)]
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--stage", choices=tuple(STAGE_DIRS), required=True)
    e.add_argument("--reports", default=None, help="stage report dir (default reports/v5/<stage dir>)")
    e.add_argument("--out", default=str(REPO / "reports" / "v5" / "export"))
    e.add_argument("--manifest", default=None, help="default reports/v5/RAW_DATA_MANIFEST_<stage>.json")
    e.add_argument("--salt-file", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--manifest", required=True)
    v.add_argument("--tar", required=True)
    a = ap.parse_args()
    if a.cmd == "verify":
        p = verify(Path(a.manifest), Path(a.tar))
        print("verified: every file matches the manifest" if not p else "MISMATCH:\n  " + "\n  ".join(p))
        return 0 if not p else 1
    reports = Path(a.reports) if a.reports else REPO / "reports" / "v5" / STAGE_DIRS[a.stage]
    mp = Path(a.manifest) if a.manifest else REPO / "reports" / "v5" / f"RAW_DATA_MANIFEST_{a.stage}.json"
    man = export(a.stage, reports, Path(a.out), mp, load_salt(Path(a.salt_file)))
    print(f"exported {man['n_files']} files -> {Path(a.out) / man['tarball']} (sha256 {man['tarball_sha256'][:16]}…); "
          f"manifest {mp}; sanitized {man['sanitization_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
