"""Protocol v5 pre-stage P1: turn host evidence (scripts/p1_host_evidence.py output) into HOST_VERIFICATION.json.

    uv run python scripts/p1_verify_host.py --evidence p1_evidence.json --check            # report only
    uv run python scripts/p1_verify_host.py --evidence p1_evidence.json --verified-by "<owner>" \
        [--model-revision-waiver "<signed text>"]                                           # write the record

Read-only towards the server (GET /version and /metrics only). Resolution rules (PROTOCOL_V5_DRAFT §10.3):
  process      exactly one vllm process whose start time equals the LIVE process_start_time_seconds (±1 s) — the same
               server every v5 stage must run on (and that v4 ran on)
  vllm_version the process interpreter's installed vllm == GET /version == 0.17.1
  launch flags --max-num-seqs / --max-num-batched-tokens from the process argv; else from the startup log
               (`max_num_seqs=N`, `max_num_batched_tokens=N`); else UNRESOLVED (never assumed from defaults)
  snapshot     DIRECT: the weight files mapped or open in the server's processes resolve to blobs that one HF snapshot
               links (`process_files`), or the startup log names one `snapshots/<commit>` (`startup_log`);
               EXCLUSION (needs explicit owner acceptance): exactly one snapshot holds a complete weight set, it and its
               weight blobs predate the process start, and no mapped/open weight file is deleted or elsewhere;
               refs/main alone is NEVER accepted. --hash evidence additionally checks blob sha256 == blob name.
The record is sanitized with the export rules (scripts/export_v5_raw.py) and gate-checked before it is written; the
canonical path is written only when `v5_stage.host_record_problems` is empty.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import export_v5_raw as ex  # noqa: E402
import v5_stage  # noqa: E402

TARGET_VERSION = "0.17.1"
WEIGHT = re.compile(r"\.(safetensors|bin|pt)$")
FLAGS = {"max_num_seqs": "--max-num-seqs", "max_num_batched_tokens": "--max-num-batched-tokens"}


def flag_from_argv(argv: list[str], flag: str) -> int | None:
    for i, a in enumerate(argv):
        if a == flag and i + 1 < len(argv):
            return int(argv[i + 1])
        if a.startswith(flag + "="):
            return int(a.split("=", 1)[1])
    return None


def flag_from_log(lines: list[str], key: str) -> tuple[int | None, list[int]]:
    vals = [int(m.group(1)) for ln in lines for m in re.finditer(rf"['\"]?{key}['\"]?\s*[=:]\s*(\d+)", ln)]
    return (vals[0] if vals and len(set(vals)) == 1 else None), sorted(set(vals))


def resolve_snapshot(ev: dict) -> dict:
    cache = ev.get("hf_cache") or {}
    snaps = cache.get("snapshots") or {}
    weights = {c: {n: f for n, f in s["files"].items() if WEIGHT.search(n) and "blob" in f} for c, s in snaps.items()}
    opened = sorted({p for w in (ev.get("weight_files") or {}).values() for p in (*w.get("maps", []), *w.get("fds", []))})
    out: dict = {"status": "unresolved", "commit": None, "method": None, "opened_weight_files": opened,
                 "refs": cache.get("refs"), "snapshots_with_weights": sorted(c for c, w in weights.items() if w)}
    blobs = {Path(p.replace(" (deleted)", "")).name for p in opened}
    if any("(deleted)" in p for p in opened):
        out["note"] = "a mapped/open weight file is deleted: the loaded snapshot may no longer be on disk"
    if blobs:
        hit = [c for c, w in weights.items() if blobs <= {f["blob"] for f in w.values()}]
        if len(hit) == 1:
            return out | {"status": "verified_direct", "commit": hit[0], "method": "process_files"}
        out["process_files_match"] = hit
    logged = sorted({m.group(1) for ln in (ev.get("startup_log") or {}).get("lines", [])
                     for m in re.finditer(r"snapshots/([0-9a-f]{40})", ln)})
    if len(logged) == 1:
        return out | {"status": "verified_direct", "commit": logged[0], "method": "startup_log"}
    out["startup_log_commits"] = logged
    start = (next((p for p in ev.get("vllm_processes", []) if p["pid"] == ev.get("matched_pid")), {}) or {}).get("start_epoch")
    full = [c for c, w in weights.items() if w and all("error" not in f for f in w.values())]
    if len(full) == 1 and start is not None and not out.get("note") and not blobs - {f["blob"] for f in weights[full[0]].values()}:
        c = full[0]
        old = snaps[c]["mtime"] <= start and all(f["mtime"] <= start for f in weights[c].values())
        if old:
            return out | {"status": "verified_by_exclusion", "commit": c, "method": "single_complete_snapshot_predating_start",
                          "requires_owner_acceptance": True}
    out["method"] = "none (refs/main alone is not evidence)"
    return out


def build_record(ev: dict, live_version: str | None, live_start: float | None, *, verified_by: str | None,
                 waiver: str | None, accept_exclusion: bool) -> tuple[dict, list[str]]:
    issues: list[str] = []
    pid = ev.get("matched_pid")
    proc = next((p for p in ev.get("vllm_processes", []) if p["pid"] == pid), None)
    if proc is None:
        issues.append(f"no unique vllm process matched start {ev.get('expect_start')} ({ev.get('match_count')} matches)")
    if live_start is None or abs((ev.get("expect_start") or 0) - live_start) > 1.0:
        issues.append(f"evidence start {ev.get('expect_start')} != live process_start_time_seconds {live_start}")
    argv = proc["argv"] if proc else []
    ver = ev.get("python_vllm_version")
    if not (ver == live_version == TARGET_VERSION):
        issues.append(f"vllm version: interpreter {ver}, GET /version {live_version}, target {TARGET_VERSION}")
    rec: dict = {"vllm_version": ver if ver == live_version else None, "launch_command": shlex.join(argv) if argv else None,
                 "process_start_time_seconds": live_start}
    log = (ev.get("startup_log") or {}).get("lines", [])
    for key, flag in FLAGS.items():
        v, src = flag_from_argv(argv, flag), "argv"
        if v is None:
            v, seen = flag_from_log(log, key)
            src = "startup_log" if v is not None else f"unresolved (log values {seen})"
        rec[key], rec[f"{key}_source"] = v, src
        if v is None:
            issues.append(f"{key} unresolved: not in argv and not uniquely in the startup log ({src})")
    rev_flag = next((a.split("=", 1)[1] if "=" in a else argv[i + 1] for i, a in enumerate(argv)
                     if a.startswith("--revision") and (i + 1 < len(argv) or "=" in a)), None)
    snap = resolve_snapshot(ev)
    rec["model_revision_flag"] = rev_flag
    rec["model_snapshot_evidence"] = snap
    ok_snap = snap["status"] == "verified_direct" or (snap["status"] == "verified_by_exclusion" and accept_exclusion)
    rec["model_snapshot_sha"] = snap["commit"] if ok_snap else None
    if snap["status"] == "verified_by_exclusion" and not accept_exclusion:
        issues.append(f"snapshot {snap['commit']} only by exclusion: needs --accept-exclusion (owner decision)")
    elif not ok_snap:
        issues.append("loaded model snapshot not identified from process files or the startup log")
    if rev_flag and snap["commit"] and rev_flag != snap["commit"]:
        issues.append(f"--revision {rev_flag} != loaded snapshot {snap['commit']}")
    hashes = ev.get("weight_sha256") or {}
    if hashes:
        bad = [b for b, h in hashes.items() if len(b) == 64 and b != h]
        rec["weight_blob_sha256_checked"] = len(hashes)
        if bad:
            issues.append(f"{len(bad)} weight blob(s) whose sha256 differs from the blob name")
    if waiver:
        rec["model_revision_waiver"] = waiver
    rec |= {"verified_by": verified_by, "verified_utc": datetime.now(UTC).isoformat() if verified_by else None,
            "evidence_collected_epoch": ev.get("collected_epoch"), "collector_version": ev.get("collector_version"),
            "startup_log_source": (ev.get("startup_log") or {}).get("source"),
            "environ_allowlisted": ev.get("environ_allowlisted")}
    issues += [f"record: {p}" for p in v5_stage.host_record_problems(rec)]
    return rec, sorted(set(issues))


def sanitize(rec: dict) -> dict:
    san = ex.Sanitizer([(str(REPO) + "/", "")], ex.target_hosts(), set(), b"p1")
    text = san.text(json.dumps(rec, indent=1))
    hits = [k for k, rx in ex.FORBIDDEN.items() if rx.search(text)]
    if hits:
        raise SystemExit(f"REFUSED: sanitized record still matches {hits}")
    return json.loads(text)


def live() -> tuple[str | None, float | None]:
    import httpx

    from quotashift.local import current_server_start
    from quotashift.targets import active_target
    t = active_target()
    try:
        ver = httpx.get(t.backend_url.rstrip("/") + "/version", timeout=10).json().get("version")
    except (httpx.HTTPError, ValueError):
        ver = None
    return ver, current_server_start(t)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--check", action="store_true", help="report only; write nothing")
    ap.add_argument("--verified-by", default=None)
    ap.add_argument("--model-revision-waiver", default=None)
    ap.add_argument("--accept-exclusion", action="store_true", help="owner accepts snapshot identification by exclusion")
    ap.add_argument("--out", default=str(v5_stage.HOST_RECORD))
    a = ap.parse_args()
    ev = json.loads(Path(a.evidence).read_text())
    ver, start = live()
    rec, issues = build_record(ev, ver, start, verified_by=a.verified_by, waiver=a.model_revision_waiver,
                               accept_exclusion=a.accept_exclusion)
    rec = sanitize(rec)
    print(json.dumps({k: rec.get(k) for k in ("vllm_version", "max_num_seqs", "max_num_seqs_source", "max_num_batched_tokens",
                                              "max_num_batched_tokens_source", "model_revision_flag", "model_snapshot_sha",
                                              "process_start_time_seconds")}, indent=1))
    print(f"snapshot evidence: {rec['model_snapshot_evidence']['status']} via {rec['model_snapshot_evidence']['method']}")
    print("UNRESOLVED:\n  - " + "\n  - ".join(issues) if issues else "all P1 fields resolved")
    if a.check:
        return 0 if not issues else 1
    out = Path(a.out)
    if out.resolve() == v5_stage.HOST_RECORD.resolve() and issues:
        print(f"refusing to write {out} with unresolved issues (use --out <draft path> to inspect)", file=sys.stderr)
        return 1
    out.write_text(json.dumps(rec, indent=1) + "\n")
    print(f"wrote {out}")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
