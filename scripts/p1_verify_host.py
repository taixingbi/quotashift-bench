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

# ---- Owner-approved inference rule (2026-11-23, P1 review decision 2). NARROW BY CONSTRUCTION: it applies only to
# vLLM 0.17.1 with exactly these installed source files (read on gpu-node-1 and reviewed: engine/arg_utils.py
# get_batch_defaults / _set_default_max_num_seqs_and_batched_tokens_args; config/vllm.py performance_mode default
# "balanced"; entrypoints/cli/serve.py usage context OPENAI_API_SERVER), a `vllm serve` launch, an RTX 3090, no
# max_num_seqs / performance_mode override in argv or in the logged non-default args, and the logged
# max_num_batched_tokens = 2048 (the same non-H100, non-doubled default branch). Result: min(256, 2048) = 256.
SOURCE_DEFAULT_RULE = {
    "id": "vllm-0.17.1-openai-server-default-max-num-seqs",
    "approved_by_owner_utc": "2026-11-23",
    "vllm_version": "0.17.1",
    "source_sha256": {
        "engine/arg_utils.py": "846fe5ade00f9651e7cee487092c6cb69eb02f19b15906a8c68a3683678a179f",
        "config/vllm.py": "405074725a88d63cf1221caf84261485f97d3f1d4eadb2837df78753fc8d5490",
        "entrypoints/cli/serve.py": "64b4427d989d6e35b353d1d718075a1c6560e1c65026de8592a57c1567e7b0ec",
    },
    "gpu_models": ["NVIDIA GeForce RTX 3090"],
    "default_max_num_seqs": 256,
    "expected_logged_max_num_batched_tokens": 2048,
}
INFERENCE_UNCERTAINTY = (
    "max_num_seqs is not logged by vLLM 0.17.1 at INFO level. The value is inferred from the installed source defaults "
    "(pinned by sha256) and the absence of any override in argv or in the logged non-default args. It is not a direct "
    "observation; an override invisible to both (e.g. a runtime patch outside the pinned files) cannot be excluded.")
CAPTURE_NOTE = ("engine-config max_cudagraph_capture_size = 512 is CONSISTENT with max_num_seqs >= 256 "
                "(min(2 * max_num_seqs, 512) when unset); it is a consistency check only and does not by itself prove "
                "the value.")


def infer_max_num_seqs(ev: dict, argv: list[str], log: list[str], batched: int | None) -> dict:
    """Evaluate SOURCE_DEFAULT_RULE; every condition is recorded, value only if all hold."""
    r = SOURCE_DEFAULT_RULE
    src = (ev.get("vllm_source") or {}).get("sha256") or {}
    nondef = [ln for ln in log if "non-default args:" in ln and f"pid={ev.get('matched_pid')}" in ln]
    cond = {
        "vllm_version_is_0.17.1": ev.get("python_vllm_version") == r["vllm_version"],
        "installed_sources_match_pinned_sha256": all(src.get(k) == v for k, v in r["source_sha256"].items()),
        "launched_with_vllm_serve": len(argv) >= 2 and any(a.endswith("/vllm") or a == "vllm" for a in argv)
        and "serve" in argv,
        "no_max_num_seqs_or_performance_mode_in_argv": not any(
            a.startswith(("--max-num-seqs", "--performance-mode")) for a in argv),
        "nondefault_args_logged_once_without_override": len(nondef) == 1 and not any(
            k in nondef[0] for k in ("max_num_seqs", "performance_mode")),
        "gpu_is_rtx_3090": bool(ev.get("gpu_models")) and all(g in r["gpu_models"] for g in ev["gpu_models"]),
        "logged_max_num_batched_tokens_is_2048": batched == r["expected_logged_max_num_batched_tokens"],
    }
    cap = next((m.group(1) for ln in log for m in re.finditer(r"'max_cudagraph_capture_size': (\d+)", ln)), None)
    ok = all(cond.values())
    return {"rule": r["id"], "conditions": cond, "all_conditions_hold": ok,
            "value": min(r["default_max_num_seqs"], batched) if ok and batched else None,
            "pinned_sources": r["source_sha256"], "uncertainty": INFERENCE_UNCERTAINTY,
            "consistency_check": {"max_cudagraph_capture_size": int(cap) if cap else None, "note": CAPTURE_NOTE}}


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
                 waiver: str | None, accept_exclusion: bool,
                 accept_source_default: bool = False) -> tuple[dict, list[str]]:
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
    if rec["max_num_seqs"] is None:
        inf = infer_max_num_seqs(ev, argv, log, rec["max_num_batched_tokens"])
        rec["max_num_seqs_inference"] = inf
        if inf["all_conditions_hold"] and accept_source_default:
            rec["max_num_seqs"], rec["max_num_seqs_source"] = inf["value"], "inferred_from_source_default"
            inf["owner_approved_by"] = verified_by
        elif inf["all_conditions_hold"]:
            issues.append("max_num_seqs only inferable from source defaults: needs --accept-source-default-max-num-seqs")
        else:
            failed = [k for k, v in inf["conditions"].items() if not v]
            issues.append(f"max_num_seqs source-default rule does not apply (failed: {failed})")
    for key in FLAGS:
        if rec[key] is None and key != "max_num_seqs":
            issues.append(f"{key} unresolved: not in argv and not uniquely in the startup log ({rec[f'{key}_source']})")
    rev_flag = next((a.split("=", 1)[1] if "=" in a else argv[i + 1] for i, a in enumerate(argv)
                     if a.startswith("--revision") and (i + 1 < len(argv) or "=" in a)), None)
    snap = resolve_snapshot(ev)
    rec["model_revision_flag"] = rev_flag
    rec["model_snapshot_evidence"] = snap
    ok_snap = snap["status"] == "verified_direct" or (snap["status"] == "verified_by_exclusion" and accept_exclusion)
    rec["model_snapshot_sha"] = snap["commit"] if ok_snap else None
    rec["model_snapshot_evidence_level"] = snap["status"] if ok_snap else "unresolved"
    if ok_snap and snap["status"] == "verified_by_exclusion":
        snap["owner_accepted_by"] = verified_by
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
            "gpu_models": ev.get("gpu_models"),
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
    ap.add_argument("--accept-source-default-max-num-seqs", action="store_true",
                    help="owner accepts the pinned source-default inference rule for max_num_seqs (P1 decision 2)")
    ap.add_argument("--out", default=str(v5_stage.HOST_RECORD))
    a = ap.parse_args()
    ev = json.loads(Path(a.evidence).read_text())
    ver, start = live()
    rec, issues = build_record(ev, ver, start, verified_by=a.verified_by, waiver=a.model_revision_waiver,
                               accept_exclusion=a.accept_exclusion,
                               accept_source_default=a.accept_source_default_max_num_seqs)
    rec = sanitize(rec)
    print(json.dumps({k: rec.get(k) for k in ("vllm_version", "max_num_seqs", "max_num_seqs_source", "max_num_batched_tokens",
                                              "max_num_batched_tokens_source", "model_revision_flag", "model_snapshot_sha",
                                              "model_snapshot_evidence_level", "process_start_time_seconds")}, indent=1))
    if "max_num_seqs_inference" in rec:
        print("max_num_seqs rule conditions:", rec["max_num_seqs_inference"]["conditions"])
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
