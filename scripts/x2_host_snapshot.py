"""X2 host snapshot: ONE read-only snapshot of the GPU host's counters (docs/X2_INSTRUMENTATION_SPEC.md section 3).

Runs ON the GPU host. Standard library only; reads /proc (and, if present, `systemctl list-timers`); writes JSON to
stdout; never signals, traces or modifies anything; starts no background process.

    ssh <gpu-host> python3 - < scripts/x2_host_snapshot.py                 # G0: one snapshot per ssh call, then exit
    python3 x2_host_snapshot.py --serve 9500                                 # G1: ECS daemon; one snapshot per GET
    python3 x2_host_snapshot.py --proc-root tests/fake_root                  # tests

Fields: wall time; /proc/stat total + idle(+iowait) jiffies and CPU count; vLLM API-server and EngineCore pids and
their utime+stime ticks (identified exactly as the X1 sampler did: API = python executable whose argv has `vllm` and
`serve`; EngineCore = `VLLM::EngineCore`); MemAvailable; oom_kill and pswpin counters; the resident user-space process
inventory (sorted comm names with counts; kernel threads excluded) and its sha256; systemd timers due (best effort).
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

SCHEMA = "x2-host-snapshot/1"


def _read(root: str, rel: str) -> str | None:
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def cpu_jiffies(text: str) -> tuple[int, int, int]:
    """(total, idle + iowait, ncpu) from /proc/stat."""
    total = idle = 0
    ncpu = 0
    for ln in text.splitlines():
        if ln.startswith("cpu "):
            v = [int(x) for x in ln.split()[1:]]
            total, idle = sum(v[:8]), v[3] + (v[4] if len(v) > 4 else 0)
        elif re.match(r"cpu\d+ ", ln):
            ncpu += 1
    return total, idle, ncpu


def proc_ticks(text: str) -> int:
    """utime + stime from /proc/<pid>/stat (fields after the parenthesised comm)."""
    rest = text[text.rindex(")") + 2:].split()
    return int(rest[11]) + int(rest[12])


def meminfo_available(text: str) -> int | None:
    m = re.search(r"^MemAvailable:\s+(\d+) kB", text, re.M)
    return int(m.group(1)) * 1024 if m else None


def vmstat(text: str) -> dict[str, int]:
    out = {}
    for ln in text.splitlines():
        k, _, v = ln.partition(" ")
        if k in ("oom_kill", "pswpin"):
            out[k] = int(v)
    return out


def processes(root: str) -> tuple[dict[str, int | None], dict[str, int]]:
    """(vLLM pids, inventory {comm: count}) over user-space processes (kernel threads have an empty cmdline)."""
    api = eng = None
    inv: dict[str, int] = {}
    for pid in sorted((p for p in os.listdir(os.path.join(root, "proc")) if p.isdigit()), key=int):
        raw = _read(root, f"proc/{pid}/cmdline")
        if not raw:
            continue
        argv = [a for a in raw.split("\0") if a]
        comm = (_read(root, f"proc/{pid}/comm") or "").strip()
        if not argv:
            continue
        if argv[0].startswith("VLLM::EngineCore") or comm.startswith("VLLM::Engine"):
            eng = eng or int(pid)
        elif os.path.basename(argv[0]).startswith("python") and any(a.endswith("vllm") for a in argv) and "serve" in argv:
            api = api or int(pid)
        name = comm or os.path.basename(argv[0])
        if name.startswith("python") and "x2_host_snapshot" in raw:
            continue                                   # never count the snapshot itself
        inv[name] = inv.get(name, 0) + 1
    return {"api": api, "engine": eng}, dict(sorted(inv.items()))


def timers() -> list[dict] | None:
    """Best effort: next elapse of systemd timers (`systemctl list-timers --all`); None where unavailable."""
    try:
        r = subprocess.run(["systemctl", "list-timers", "--all", "--no-legend", "--no-pager"], capture_output=True,
                           text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode:
        return None
    out = []
    for ln in r.stdout.splitlines():
        unit = re.search(r"(\S+\.timer)\s+(\S+\.service)?\s*$", ln)
        nxt = re.match(r"\w{3} (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\S+)", ln)
        if unit:
            out.append({"timer": unit.group(1), "next": f"{nxt.group(1)} {nxt.group(2)}" if nxt else None})
    return out


def snapshot(root: str = "/", *, with_timers: bool = True) -> dict:
    t0 = time.time()
    total, idle, ncpu = cpu_jiffies(_read(root, "proc/stat") or "")
    pids, inv = processes(root)
    ticks = {}
    for k, pid in pids.items():
        t = _read(root, f"proc/{pid}/stat") if pid else None
        ticks[k] = proc_ticks(t) if t else None
    snap = {"schema": SCHEMA, "wall": t0, "clk_tck": os.sysconf("SC_CLK_TCK"), "cpu_total": total, "cpu_idle": idle,
            "ncpu": ncpu, "pids": pids, "ticks": ticks,
            "mem_available": meminfo_available(_read(root, "proc/meminfo") or ""),
            **vmstat(_read(root, "proc/vmstat") or ""), "inventory": inv,
            "inventory_sha256": hashlib.sha256(json.dumps(inv, sort_keys=True).encode()).hexdigest(),
            "timers": timers() if with_timers and root == "/" else None}
    snap["read_s"] = time.time() - t0
    return snap


def serve(port: int, root: str) -> None:
    """G1 daemon: blocks in accept(); each GET returns one fresh snapshot. No periodic work of its own."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = json.dumps(snapshot(root)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a: object) -> None:          # no per-request logging on the host
            return

    HTTPServer(("0.0.0.0", port), H).serve_forever()       # noqa: S104 (VPC-only; SG allows the runner only)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proc-root", default="/")
    ap.add_argument("--serve", type=int, help="G1 daemon mode: HTTP port")
    ap.add_argument("--no-timers", action="store_true")
    a = ap.parse_args()
    if a.serve:
        serve(a.serve, a.proc_root)
        return 0
    json.dump(snapshot(a.proc_root, with_timers=not a.no_timers), sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
