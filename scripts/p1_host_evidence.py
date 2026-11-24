"""Protocol v5 pre-stage P1: READ-ONLY host evidence collector. Runs ON the GPU host, standard library only.

    ssh <gpu-host> python3 - --expect-start 1795268683.89 < scripts/p1_host_evidence.py > p1_evidence.json
    # optional, reads the loaded weight files once (~15 GB of disk reads, no GPU use):
    ssh <gpu-host> python3 - --expect-start 1795268683.89 --hash < scripts/p1_host_evidence.py > p1_evidence.json

It never writes, signals, restarts or allocates anything, and it touches no GPU. Every read is a plain file read under
/proc, the Hugging Face cache, or the server's own log; `journalctl` / `docker logs` are run read-only when the
process lives in a systemd unit or a container. Permission errors are recorded, not worked around.

What it records (consumed by scripts/p1_verify_host.py on the runner):
  - every process whose argv mentions vllm: pid, ppid, start time (btime + starttime/CLK_TCK, the same formula as
    Prometheus' process_start_time_seconds), argv; the one matching --expect-start and its descendants
  - the vllm package version of that process's own interpreter (importlib.metadata; vllm itself is not imported)
  - weight files (*.safetensors / *.bin) currently mapped (/proc/<pid>/maps) or open (/proc/<pid>/fd), incl. deleted
  - environment of the matched process, ALLOWLIST ONLY (HF_*/VLLM_* cache and offline settings; never tokens)
  - the HF cache of the served model: refs (commit + mtime), every snapshot (mtime, each file's blob + size + mtime)
  - startup-log lines mentioning scheduler limits, args, revision or snapshot paths
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time

WEIGHT_RE = re.compile(r"\.(safetensors|bin|pt)(\s+\(deleted\))?$")
ENV_ALLOW = re.compile(r"^(HF_HOME|HF_HUB_CACHE|HUGGINGFACE_HUB_CACHE|HF_HUB_OFFLINE|TRANSFORMERS_OFFLINE|"
                       r"VLLM_[A-Z0-9_]*(CACHE|OFFLINE|CONFIG|USE_V1|ROOT)[A-Z0-9_]*|CUDA_VISIBLE_DEVICES)$")
ENV_DENY = re.compile(r"TOKEN|SECRET|PASSWORD|KEY", re.I)
LOG_RE = re.compile(r"max_num_seqs|max_num_batched_tokens|non-default args|snapshots/|revision|Loading weights|"
                    r"Starting vLLM|vLLM API server version|Chunked prefill", re.I)


def _read(path: str, binary: bool = False):  # noqa: ANN202
    try:
        with open(path, "rb" if binary else "r") as f:
            return f.read()
    except OSError as e:
        return e


def boot_time() -> float:
    for ln in str(_read("/proc/stat")).splitlines():
        if ln.startswith("btime "):
            return float(ln.split()[1])
    raise SystemExit("no btime in /proc/stat")


def proc_info(pid: int, btime: float, tck: int) -> dict | None:
    stat = _read(f"/proc/{pid}/stat")
    raw = _read(f"/proc/{pid}/cmdline", binary=True)
    if isinstance(stat, Exception) or isinstance(raw, Exception):
        return None
    rest = stat.rsplit(")", 1)[1].split()
    argv = [a.decode(errors="replace") for a in raw.split(b"\0") if a]
    try:
        uid = os.stat(f"/proc/{pid}").st_uid
    except OSError:      # the process exited during the scan
        return None
    return {"pid": pid, "ppid": int(rest[1]), "start_epoch": round(btime + int(rest[19]) / tck, 2), "argv": argv,
            "exe": _link(f"/proc/{pid}/exe"), "uid": uid}


def _link(p: str) -> str | None:
    try:
        return os.readlink(p)
    except OSError as e:
        return f"<unreadable: {e.strerror}>"


def weight_files(pid: int) -> dict:
    out: dict = {"maps": [], "fds": [], "errors": []}
    maps = _read(f"/proc/{pid}/maps")
    if isinstance(maps, Exception):
        out["errors"].append(f"maps: {maps}")
    else:
        out["maps"] = sorted({ln.split(None, 5)[5] for ln in maps.splitlines()
                              if len(ln.split(None, 5)) == 6 and WEIGHT_RE.search(ln.split(None, 5)[5])})
    try:
        for fd in os.listdir(f"/proc/{pid}/fd"):
            t = _link(f"/proc/{pid}/fd/{fd}")
            if t and WEIGHT_RE.search(t):
                out["fds"].append(t)
    except OSError as e:
        out["errors"].append(f"fd: {e.strerror}")
    out["fds"] = sorted(set(out["fds"]))
    return out


def environ(pid: int) -> dict:
    raw = _read(f"/proc/{pid}/environ", binary=True)
    if isinstance(raw, Exception):
        return {"<error>": str(raw)}
    env = {}
    for kv in raw.split(b"\0"):
        k, _, v = kv.decode(errors="replace").partition("=")
        if ENV_ALLOW.match(k) and not ENV_DENY.search(k):
            env[k] = v
    return env


def vllm_version(exe: str | None) -> str:
    if not exe or exe.startswith("<"):
        return "<unknown interpreter>"
    try:
        r = subprocess.run([exe, "-c", "import importlib.metadata as m; print(m.version('vllm'))"],
                           capture_output=True, text=True, timeout=60)
        return r.stdout.strip() or f"<error: {r.stderr.strip()[-200:]}>"
    except (OSError, subprocess.SubprocessError) as e:
        return f"<error: {e}>"


def hf_cache(model: str, env: dict, home: str) -> dict:
    roots = [env.get("HF_HUB_CACHE"), env.get("HUGGINGFACE_HUB_CACHE"),
             os.path.join(env["HF_HOME"], "hub") if env.get("HF_HOME") else None,
             os.path.join(home, ".cache", "huggingface", "hub")]
    for root in [r for r in roots if r]:
        repo = os.path.join(root, "models--" + model.replace("/", "--"))
        if os.path.isdir(repo):
            break
    else:
        return {"found": False, "searched": [r for r in roots if r]}
    out: dict = {"found": True, "root": root, "repo_dir": repo, "refs": {}, "snapshots": {}}
    for ref in sorted(os.listdir(os.path.join(repo, "refs"))) if os.path.isdir(os.path.join(repo, "refs")) else []:
        p = os.path.join(repo, "refs", ref)
        out["refs"][ref] = {"commit": str(_read(p)).strip(), "mtime": os.stat(p).st_mtime}
    sdir = os.path.join(repo, "snapshots")
    for commit in sorted(os.listdir(sdir)) if os.path.isdir(sdir) else []:
        d = os.path.join(sdir, commit)
        files = {}
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            real = os.path.realpath(p)
            try:
                st = os.stat(real)
                files[name] = {"blob": os.path.basename(real), "realpath": real, "bytes": st.st_size, "mtime": st.st_mtime}
            except OSError as e:
                files[name] = {"error": e.strerror}
        out["snapshots"][commit] = {"mtime": os.lstat(d).st_mtime, "files": files}
    return out


def startup_log(pid: int, start: float) -> dict:
    cg = str(_read(f"/proc/{pid}/cgroup"))
    since = f"@{int(start) - 120}"
    lines: list[str] = []
    src = None
    unit = re.search(r"/([^/\s]+\.service)", cg)
    dock = re.search(r"docker[-/]([0-9a-f]{12,64})", cg)
    try:
        if dock:
            src = f"docker:{dock.group(1)[:12]}"
            r = subprocess.run(["docker", "logs", "--since", str(int(start) - 120), dock.group(1)],
                               capture_output=True, text=True, timeout=60)
            text = r.stdout + r.stderr
        elif unit:
            src = f"journal:{unit.group(1)}"
            r = subprocess.run(["journalctl", "-u", unit.group(1), "--since", since, "--no-pager", "-o", "cat"],
                               capture_output=True, text=True, timeout=60)
            text = r.stdout + r.stderr
        else:
            text, seen = "", set()
            for fd in ("1", "2"):
                t = _link(f"/proc/{pid}/fd/{fd}")
                if t and t.startswith("/") and os.path.isfile(t) and t not in seen:   # stdout and stderr may share a file
                    seen.add(t)
                    src = f"file:{t}"
                    content = _read(t)
                    text += content if isinstance(content, str) else ""
            if src is None:
                src = f"none (stdout -> {_link(f'/proc/{pid}/fd/1')})"
    except (OSError, subprocess.SubprocessError) as e:
        return {"source": src, "error": str(e), "lines": []}
    for ln in text.splitlines():
        if LOG_RE.search(ln):
            lines.append(ln[:20000])
    return {"source": src, "lines": lines[:300], "log_total_lines": len(text.splitlines())}


VLLM_SOURCES = ("engine/arg_utils.py", "config/vllm.py", "entrypoints/cli/serve.py")


def vllm_source(exe: str | None) -> dict:
    """sha256 of the installed vllm files that resolve the scheduler defaults (located without importing vllm)."""
    if not exe or exe.startswith("<"):
        return {"error": "unknown interpreter"}
    try:
        r = subprocess.run([exe, "-c", "import importlib.util as u; print(u.find_spec('vllm').submodule_search_locations[0])"],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return {"error": str(e)}
    root = r.stdout.strip()
    out: dict = {"package_dir": root, "sha256": {}}
    for rel in VLLM_SOURCES:
        try:
            out["sha256"][rel] = sha256_file(os.path.join(root, rel))
        except OSError as e:
            out["sha256"][rel] = f"<error: {e.strerror}>"
    return out


def gpu_models() -> list[str]:
    """Model names from the NVIDIA driver's read-only /proc interface (no GPU tool or context)."""
    base = "/proc/driver/nvidia/gpus"
    names = []
    try:
        for d in sorted(os.listdir(base)):
            for ln in str(_read(os.path.join(base, d, "information"))).splitlines():
                if ln.startswith("Model:"):
                    names.append(ln.split(":", 1)[1].strip())
    except OSError as e:
        names.append(f"<error: {e.strerror}>")
    return names


def sha256_file(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect-start", type=float, required=True, help="process_start_time_seconds from /metrics")
    ap.add_argument("--model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument("--hash", action="store_true", help="sha256 the matched snapshot's weight blobs (disk reads only)")
    a = ap.parse_args()
    btime, tck = boot_time(), os.sysconf("SC_CLK_TCK")
    allp = [p for pid in os.listdir("/proc") if pid.isdigit() for p in [proc_info(int(pid), btime, tck)] if p]
    procs = [p for p in allp if any("vllm" in x.lower() for x in p["argv"])]   # incl. `VLLM::EngineCore`
    match = [p for p in procs if abs(p["start_epoch"] - a.expect_start) <= 1.0]
    out: dict = {"collector": "p1_host_evidence.py", "collector_version": 2, "collected_epoch": time.time(),
                 "expect_start": a.expect_start, "boot_time": btime, "clk_tck": tck, "vllm_processes": procs,
                 "matched_pid": match[0]["pid"] if len(match) == 1 else None, "match_count": len(match)}
    if len(match) == 1:
        root = match[0]
        kids, frontier = [], [root["pid"]]
        while frontier:
            nxt = [p["pid"] for p in allp if p["ppid"] in frontier]   # every descendant, whatever its argv
            kids += nxt
            frontier = nxt
        out["descendants"] = kids
        out["descendant_processes"] = [p for p in allp if p["pid"] in kids]
        out["weight_files"] = {str(pid): weight_files(pid) for pid in [root["pid"], *kids]}
        env = environ(root["pid"])
        out["environ_allowlisted"] = env
        out["python_vllm_version"] = vllm_version(root["exe"])
        out["vllm_source"] = vllm_source(root["exe"])
        out["gpu_models"] = gpu_models()
        home = next((ln.split(":")[5] for ln in str(_read("/etc/passwd")).splitlines()
                     if ln.split(":")[2:3] == [str(root["uid"])]), os.path.expanduser("~"))
        out["hf_cache"] = hf_cache(a.model, env, home)
        out["startup_log"] = startup_log(root["pid"], root["start_epoch"])
        if a.hash and out["hf_cache"].get("found"):
            out["weight_sha256"] = {}
            for snap in out["hf_cache"]["snapshots"].values():
                for name, f in snap["files"].items():
                    if WEIGHT_RE.search(name) and "realpath" in f and f["blob"] not in out["weight_sha256"]:
                        out["weight_sha256"][f["blob"]] = sha256_file(f["realpath"])
    json.dump(out, sys.stdout, indent=1)
    print()
    return 0 if len(match) == 1 else 2


if __name__ == "__main__":
    raise SystemExit(main())
