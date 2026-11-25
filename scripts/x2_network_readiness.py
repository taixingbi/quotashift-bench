"""X2 G0 network + host readiness check (READ-ONLY; docs/X2_DEPLOYMENT_READINESS.md B-X2-1/B-X2-2; Phase B).

    uv run python scripts/x2_network_readiness.py --host gpu-node-2 [--pings 200] [--label after-ethernet]

Changes nothing on either machine. Measures and reports (no addresses or user names in the output):
  * runner side: the interface that routes to the GPU host and its hardware type (macOS networksetup / Linux sysfs)
  * host side (ssh, read-only): the interface that routes back to the runner, wireless or not, link speed, operstate
  * ICMP RTT to the host: median, p95, sd, min, max, loss (N pings at 0.2 s), vs the X1/X2-audit Wi-Fi baseline
  * HTTP RTT to the vLLM /health endpoint (the measured path), 50 sequential GETs, if the server answers
  * host readiness: k3s agent, unattended-upgrades / apt timers, sysstat timer, desktop session, NVIDIA driver,
    GPU processes, vLLM process start, MemAvailable, load, and one x2_host_snapshot inventory hash
Readiness rule (B-X2-1, unchanged): BOTH ends wired. The RTT numbers are reported, never used to relax that rule.
Writes reports/x2/readiness/<UTC>_<label>.json.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import re
import statistics as st
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "reports" / "x2" / "readiness"
WIFI_BASELINE_SD_MS = 22.5          # docs/X2_HOST_AUDIT.md (2026-11-25, 100 echoes over Wi-Fi at both ends)
IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


def sh(cmd: list[str], timeout: int = 60) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.stdout


def ssh(host: str, cmd: str, timeout: int = 60) -> str:
    return sh(["ssh", "-o", "BatchMode=yes", host, cmd], timeout)


def host_addr(host: str) -> str:
    out = sh(["ssh", "-G", host])
    return next((ln.split()[1] for ln in out.splitlines() if ln.startswith("hostname ")), host)


def runner_interface(addr: str) -> dict:
    if platform.system() == "Darwin":
        dev = next((ln.split()[-1] for ln in sh(["route", "-n", "get", addr]).splitlines() if "interface:" in ln), None)
        ports = sh(["networksetup", "-listallhardwareports"]).split("\n\n")
        port = next((b.split("\n")[0].split(": ", 1)[1] for b in ports if f"Device: {dev}" in b), None) if dev else None
        wired = port is not None and not re.search(r"wi-?fi|airport|wireless", port, re.I)
        return {"device": dev, "hardware_port": port, "wired": wired}
    dev = re.search(r" dev (\S+)", sh(["ip", "route", "get", addr]))
    d = dev.group(1) if dev else None
    wireless = bool(d) and Path(f"/sys/class/net/{d}/wireless").exists()
    return {"device": d, "hardware_port": "wireless" if wireless else "wired", "wired": bool(d) and not wireless}


def host_interface(host: str) -> dict:
    out = ssh(host, "RIP=${SSH_CLIENT%% *}; DEV=$(ip route get \"$RIP\" | sed -n 's/.* dev \\([^ ]*\\).*/\\1/p' | head -1); "
                    "echo dev=$DEV; [ -d /sys/class/net/$DEV/wireless ] && echo wireless=1 || echo wireless=0; "
                    "echo speed=$(cat /sys/class/net/$DEV/speed 2>/dev/null); echo state=$(cat /sys/class/net/$DEV/operstate)")
    kv = dict(ln.split("=", 1) for ln in out.split() if "=" in ln)
    return {"device": kv.get("dev"), "wireless": kv.get("wireless") == "1", "wired": kv.get("wireless") == "0",
            "speed_mbps": int(kv["speed"]) if kv.get("speed", "").lstrip("-").isdigit() and int(kv["speed"]) > 0 else None,
            "operstate": kv.get("state")}


def rtt_stats(xs: list[float], sent: int) -> dict:
    if not xs:
        return {"n": 0, "loss": 1.0}
    s = sorted(xs)
    return {"n": len(xs), "sent": sent, "loss": 1 - len(xs) / sent, "median_ms": st.median(s),
            "p95_ms": s[max(0, math.ceil(0.95 * len(s)) - 1)], "sd_ms": st.stdev(s) if len(s) > 1 else 0.0,
            "min_ms": s[0], "max_ms": s[-1]}


def icmp(addr: str, n: int) -> dict:
    out = sh(["ping", "-c", str(n), "-i", "0.2", addr], timeout=n + 30)
    return rtt_stats([float(m) for m in re.findall(r"time=([\d.]+) ms", out)], n)


def http(base: str, n: int = 50) -> dict:
    import httpx
    xs = []
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            httpx.get(base + "/health", timeout=5)
            xs.append((time.perf_counter() - t0) * 1000)
        except httpx.HTTPError:
            pass
    return rtt_stats(xs, n)


def host_state(host: str) -> dict:
    q = ("for u in k3s-agent unattended-upgrades apt-daily.timer apt-daily-upgrade.timer sysstat-collect.timer gdm; do "
         "printf '%s=%s/%s\\n' $u $(systemctl is-active $u 2>/dev/null) $(systemctl is-enabled $u 2>/dev/null); done; "
         "echo driver=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1); "
         "echo gpu_util=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -1); "
         "echo gpu_procs=$(nvidia-smi --query-compute-apps=process_name --format=csv,noheader 2>/dev/null | tr '\\n' ','); "
         "echo vllm_etimes=$(ps -o etimes= -p $(pgrep -u $USER -f 'vllm serv[e]' | head -1) 2>/dev/null | tr -d ' '); "
         "echo memavail_kb=$(awk '/MemAvailable/{print $2}' /proc/meminfo); echo load=$(cut -d' ' -f1-3 /proc/loadavg); "
         "echo samplers=$(pgrep -fc '[x][12]_host_s' || true)")
    out = ssh(host, q)
    kv = dict(ln.split("=", 1) for ln in out.splitlines() if "=" in ln)
    return dict(kv)


def inventory(host: str) -> dict:
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", host, "python3", "-", "--no-timers"],
                       input=(REPO / "scripts" / "x2_host_snapshot.py").read_text(), capture_output=True, text=True,
                       timeout=60)
    s = json.loads(r.stdout)
    return {"inventory_sha256": s["inventory_sha256"], "n_processes": sum(s["inventory"].values()),
            "names": sorted(s["inventory"]), "vllm_pids_found": all(s["pids"].values())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True, help="ssh alias of the G0 host")
    ap.add_argument("--pings", type=int, default=200)
    ap.add_argument("--label", default="check")
    ap.add_argument("--target", default="x2-g0-qwen")
    a = ap.parse_args()
    import yaml
    addr = host_addr(a.host)
    base = yaml.safe_load((REPO / "configs" / "targets" / f"{a.target}.yaml").read_text())["backend_url"].rstrip("/")
    rec: dict = {"utc": datetime.now(UTC).isoformat(), "label": a.label, "rule": "B-X2-1: both ends wired (unchanged)",
                 "runner": runner_interface(addr), "host": host_interface(a.host), "icmp": icmp(addr, a.pings),
                 "http_health": http(base), "host_state": host_state(a.host), "inventory": inventory(a.host),
                 "wifi_baseline_icmp_sd_ms": WIFI_BASELINE_SD_MS}
    rec["network_ready"] = bool(rec["runner"]["wired"] and rec["host"]["wired"])
    text = json.dumps(rec, indent=1)
    assert not IPV4.search(text), "an address leaked into the readiness record"
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{rec['utc'][:19].replace(':', '')}_{a.label}.json"
    f.write_text(text + "\n")
    i, h = rec["icmp"], rec["http_health"]
    print(f"runner {rec['runner']['hardware_port']} ({'wired' if rec['runner']['wired'] else 'NOT wired'}); "
          f"host {'wireless' if rec['host']['wireless'] else 'wired'} {rec['host']['speed_mbps']} Mb/s {rec['host']['operstate']}")
    print(f"ICMP n={i.get('n')} loss={i.get('loss', 1):.1%} median {i.get('median_ms', float('nan')):.2f} p95 "
          f"{i.get('p95_ms', float('nan')):.2f} sd {i.get('sd_ms', float('nan')):.2f} ms (Wi-Fi baseline sd {WIFI_BASELINE_SD_MS})")
    print(f"HTTP /health n={h.get('n')} median {h.get('median_ms', float('nan')):.2f} p95 {h.get('p95_ms', float('nan')):.2f} "
          f"sd {h.get('sd_ms', float('nan')):.2f} ms")
    print(f"network_ready (both wired): {rec['network_ready']}  -> {f.relative_to(REPO)}")
    return 0 if rec["network_ready"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
