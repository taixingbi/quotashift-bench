"""X1 host-telemetry sampler (draft rev 4, section 9.2). READ-ONLY, standard library only, Linux /proc.

Runs ON the GPU host (piped over ssh, nothing installed):

    ssh <host> python3 - --duration 60 --interval 1.0 < scripts/x1_host_sampler.py > samples.jsonl

Each line on stdout is one JSON sample:
  t                monotonic seconds since start
  host_busy        fraction of all CPUs busy since the previous sample (from /proc/stat)
  ncpu             number of CPUs counted
  api_cpu, engine_cpu   CPU seconds used by the vLLM API server / EngineCore since the previous sample,
                   divided by the interval (1.0 = one full core). null if the process was not found.
  mem_available    /proc/meminfo MemAvailable in bytes
  oom_kill, pswpin cumulative /proc/vmstat counters (deltas are taken by the evaluator)
The last line is {"summary": ...} with the sampler's OWN CPU seconds, wall seconds and overhead fraction
(of one core), so its cost is measured, not assumed.

Distortion budget (draft rev 4 section 9.2): the sampler opens a handful of small /proc files per tick, holds no locks,
writes one ~200-byte line per tick to stdout, never touches the GPU, the network or the vLLM process, and runs
under `nice 19`. It must stay below 1% of one core; the summary line proves it per run.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time


def _read(root: str, rel: str) -> str | None:
    try:
        with open(os.path.join(root, rel)) as f:
            return f.read()
    except OSError:
        return None


def parse_proc_stat(text: str) -> tuple[int, int, int]:
    """(total jiffies, idle jiffies incl. iowait, cpu count) from /proc/stat."""
    total = idle = ncpu = 0
    for line in text.splitlines():
        if line.startswith("cpu ") or not line.startswith("cpu"):
            continue
        ncpu += 1
    for line in text.splitlines():
        if line.startswith("cpu "):
            v = [int(x) for x in line.split()[1:]]
            total = sum(v[:8])            # user nice system idle iowait irq softirq steal (guest is inside user)
            idle = v[3] + (v[4] if len(v) > 4 else 0)
            break
    return total, idle, ncpu


def parse_proc_pid_cpu(text: str) -> int:
    """utime + stime jiffies from /proc/<pid>/stat (comm may contain spaces; split after the last ')')."""
    rest = text[text.rindex(")") + 2:].split()
    return int(rest[11]) + int(rest[12])


def parse_meminfo_available(text: str) -> int | None:
    for line in text.splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    return None


def parse_vmstat(text: str) -> dict[str, int]:
    out = {}
    for line in text.splitlines():
        k, _, v = line.partition(" ")
        if k in ("oom_kill", "pswpin"):
            out[k] = int(v)
    return out


def find_vllm_pids(root: str) -> dict[str, int | None]:
    """API server: a python executable whose argv contains `vllm` and `serve` (never a shell wrapper).
    EngineCore: process named `VLLM::EngineCore` (argv[0] or comm)."""
    api = eng = None
    for pid in sorted((p for p in os.listdir(os.path.join(root, "proc")) if p.isdigit()), key=int):
        raw = _read(root, f"proc/{pid}/cmdline")
        if not raw:
            continue
        argv = [a for a in raw.split("\0") if a]
        comm = (_read(root, f"proc/{pid}/comm") or "").strip()
        if argv and (argv[0].startswith("VLLM::EngineCore") or comm.startswith("VLLM::Engine")):
            eng = eng or int(pid)
        elif argv and os.path.basename(argv[0]).startswith("python") and any(a.endswith("vllm") for a in argv) \
                and "serve" in argv:
            api = api or int(pid)
    return {"api": api, "engine": eng}


def sample(root: str, pids: dict[str, int | None]) -> dict:
    stat = parse_proc_stat(_read(root, "proc/stat") or "")
    procs = {}
    for k, pid in pids.items():
        t = _read(root, f"proc/{pid}/stat") if pid else None
        procs[k] = parse_proc_pid_cpu(t) if t else None
    return {"stat": stat, "procs": procs,
            "mem_available": parse_meminfo_available(_read(root, "proc/meminfo") or ""),
            **parse_vmstat(_read(root, "proc/vmstat") or "")}


def derive(prev: dict, cur: dict, dt: float, tck: int) -> dict:
    (t0, i0, n), (t1, i1, _) = prev["stat"], cur["stat"]
    busy = 1.0 - (i1 - i0) / (t1 - t0) if t1 > t0 else None
    cpu = {}
    for k in ("api", "engine"):
        a, b = prev["procs"].get(k), cur["procs"].get(k)
        cpu[k] = (b - a) / tck / dt if a is not None and b is not None and dt > 0 else None
    return {"host_busy": busy, "ncpu": n, "api_cpu": cpu["api"], "engine_cpu": cpu["engine"],
            "mem_available": cur["mem_available"], "oom_kill": cur.get("oom_kill"), "pswpin": cur.get("pswpin")}


def run(root: str, duration: float, interval: float, out=sys.stdout) -> dict:  # noqa: ANN001
    tck = os.sysconf("SC_CLK_TCK")
    pids = find_vllm_pids(root)
    r0, w0 = resource.getrusage(resource.RUSAGE_SELF), time.monotonic()
    prev, tp = sample(root, pids), time.monotonic()
    n = 0
    nxt = tp + interval
    while time.monotonic() - w0 < duration:
        time.sleep(max(0.0, nxt - time.monotonic()))
        nxt += interval
        cur, tc = sample(root, pids), time.monotonic()
        out.write(json.dumps({"t": round(tc - w0, 3), **derive(prev, cur, tc - tp, tck)}) + "\n")
        prev, tp, n = cur, tc, n + 1
    r1, w1 = resource.getrusage(resource.RUSAGE_SELF), time.monotonic()
    own = (r1.ru_utime - r0.ru_utime) + (r1.ru_stime - r0.ru_stime)
    summ = {"samples": n, "wall_s": round(w1 - w0, 3), "own_cpu_s": round(own, 4),
            "overhead_core_frac": round(own / (w1 - w0), 6) if w1 > w0 else None, "pids": pids,
            "max_rss_kib": r1.ru_maxrss}
    out.write(json.dumps({"summary": summ}) + "\n")
    out.flush()
    return summ


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=60.0)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--proc-root", default="/", help="root containing proc/ (tests use a fake tree)")
    ap.add_argument("--no-nice", action="store_true")
    a = ap.parse_args()
    if not a.no_nice:
        try:
            os.nice(19)
        except OSError:
            pass
    run(a.proc_root, a.duration, a.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
