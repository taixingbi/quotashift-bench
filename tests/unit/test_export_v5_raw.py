"""Sanitized raw-data export (scripts/export_v5_raw.py; PROTOCOL_V5 §9 item 11): sanitization rules, the fail-closed
regex gate, deterministic packaging and SHA-256 verification. Synthetic fixture files only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import export_v5_raw as ex  # noqa: E402

HOST = next(h for h, n in ex.target_hosts().items() if n == "selfhost")   # the LAN address, from configs/targets
UUID, PCI = "a837190a-d9c2-ed45-994b-55319c6e258e", "00000000:01:00.0"


@pytest.fixture
def tree(tmp_path) -> Path:
    run = tmp_path / "results" / "v5_x__attack" / "20261124T000000Z_fcfs_5000"
    run.mkdir(parents=True)
    (run / "manifest.json").write_text(json.dumps({
        "gpu": {"exporter_url": f"http://{HOST}:9835/metrics", "gpu": {"uuid": UUID, "pci_bus_id": PCI, "name": "RTX"}},
        "run_context": {"backend_url": f"http://{HOST}:8000", "cwd": "/Users/someone/work"}}))
    pd.DataFrame({"run_dir": [str(run)], "x": [1.0]}).to_parquet(run / "requests.parquet")
    (run / "fig.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x01")
    rep = tmp_path / "reports" / "v5_x"
    (rep / "target_snapshot").mkdir(parents=True)
    (rep / "manifest.json").write_text(json.dumps({"run_dirs": {"attack": {"5000": str(run)}}}))
    (rep / "summary.csv").write_text(f"run_dir,seed\n{run},5000\n")
    (rep / "target_snapshot" / "gpu_info.prom").write_text(f'gpu_info{{uuid="{UUID}",pci_bus_id="{PCI}"}} 1\n')
    (rep / "target_snapshot" / "server_info.json").write_text(json.dumps({
        "vllm_env": {"VLLM_CACHE_ROOT": "/home/tb/.cache/vllm", "VLLM_USE_V1": "1"},
        "system_env": {"pip_packages": "torch==2.9", "env_vars": "HOME=/home/tb", "os": "Ubuntu"}}))
    return tmp_path / "reports"


def _export(tree: Path, tmp: Path, salt: bytes = b"s" * 32) -> tuple[dict, Path, Path]:
    out, man = tmp / "out", tmp / "out" / "M.json"
    m = ex.export("A", tree, out, man, salt)
    return m, out / m["tarball"], man


def _members(tar: Path) -> dict[str, bytes]:
    import io
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(tar.read_bytes()), mode="r:gz") as t:
        return {m.name: t.extractfile(m).read() for m in t.getmembers()}  # type: ignore[union-attr]


def test_sanitizes_paths_hosts_gpu_ids_and_drops_keys(tree, tmp_path):
    m, tar, man = _export(tree, tmp_path)
    files = _members(tar)
    assert m["n_files"] == len(files) == 7  # 4 report files + 3 run files
    blob = b"\n".join(b for n, b in files.items() if not n.endswith(".parquet"))
    for leaked in (b"/Users/", b"/home/", HOST.encode(), UUID.encode(), PCI.encode(), str(tree.parent).encode()):
        assert leaked not in blob, leaked
    assert b"selfhost" in blob and b"gpu-" in blob
    srv = json.loads(next(b for n, b in files.items() if n.endswith("server_info.json")))
    assert srv["vllm_env"] == {"VLLM_USE_V1": "1"} and srv["system_env"] == {"os": "Ubuntu"}
    pq = next(b for n, b in files.items() if n.endswith(".parquet"))
    import io
    assert pd.read_parquet(io.BytesIO(pq)).run_dir[0] == "results/v5_x__attack/20261124T000000Z_fcfs_5000"
    csv = next(b for n, b in files.items() if n.endswith("summary.csv")).decode()
    assert "results/v5_x__attack/20261124T000000Z_fcfs_5000,5000" in csv
    # same device -> same pseudonym in every file (uuid in JSON and in the .prom text)
    prom = next(b for n, b in files.items() if n.endswith(".prom")).decode()
    gid = ex.Sanitizer([], {}, {UUID}, b"s" * 32).gpu[UUID]
    assert gid in prom
    assert ex.verify(man, tar) == []


def test_export_is_deterministic_and_salt_dependent(tree, tmp_path):
    a, _, _ = _export(tree, tmp_path / "1")
    b, _, _ = _export(tree, tmp_path / "2")
    c, _, _ = _export(tree, tmp_path / "3", salt=b"t" * 32)
    assert a["tarball_sha256"] == b["tarball_sha256"] != c["tarball_sha256"]


def test_verify_detects_tampering(tree, tmp_path):
    _, tar, man = _export(tree, tmp_path)
    m = json.loads(man.read_text())
    m["files"][0]["sha256"] = "0" * 64
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(m))
    assert any("content mismatch" in p for p in ex.verify(bad, tar))
    tar.write_bytes(tar.read_bytes()[:-10])
    assert ex.verify(man, tar)


def test_gate_refuses_secrets_and_unknown_binaries(tree, tmp_path):
    (tree / "v5_x" / "notes.txt").write_text("token ghp_" + "a" * 36)
    with pytest.raises(SystemExit, match="regex gate"):
        _export(tree, tmp_path / "1")
    (tree / "v5_x" / "notes.txt").unlink()
    (tree / "v5_x" / "blob.bin").write_bytes(b"\xff\xfe\x00\x81")
    with pytest.raises(SystemExit, match="neither a known binary type"):
        _export(tree, tmp_path / "2")
    assert not (tmp_path / "1" / "out").exists()   # nothing written on refusal


def test_salt_must_live_outside_the_repository(tmp_path):
    with pytest.raises(SystemExit, match="outside the repository"):
        ex.load_salt(REPO / ".export_salt")
    p = tmp_path / "salt"
    s = ex.load_salt(p)
    assert len(s) == 64 and ex.load_salt(p) == s and (p.stat().st_mode & 0o777) == 0o600
