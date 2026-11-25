"""X2 boundary-snapshot procedure (docs/X2_INSTRUMENTATION_SPEC.md sections 2-4). Runner side.

Measured-window policy: between (arm start - GUARD_S) and the end of the arm, the X2 harness performs NO host-side
action: no ssh session, no process start, no snapshot request. The only traffic is the workload and the frozen v5
harness's own `/metrics` scrape (identical in both arms; covered by qualification Q0/Q1).

Per arm:   before = snapshot()  ->  wait until GUARD_S has elapsed since the snapshot RETURNED  ->  arm  ->
           after = snapshot()   ->  per-arm metrics + flags (arm_metrics / arm_flags), written next to the arm's run.

Transports (one per platform; each platform's Q1 qualifies its own):
  ssh   G0: `ssh -o BatchMode=yes <host> python3 - < scripts/x2_host_snapshot.py` (no resident process on the host)
  http  G1: GET http://<host>:9500/ on the read-only snapshot daemon (ECS daemon task, VPC-only)
  mock  tests / mock stages: a synthetic snapshot, marked synthetic (never evidence)
Configured for a harness subprocess through the env var QUOTASHIFT_X2_BOUNDARY (JSON), set only by X2 drivers; when it is
unset the harness behaves exactly as before (v5 / X1 untouched).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HOST_SCRIPT = REPO / "scripts" / "x2_host_snapshot.py"
ENV = "QUOTASHIFT_X2_BOUNDARY"
GUARD_S = 15.0
# pre-registered per-arm flags (owner conditionally accepted: arm means only; intra-arm bursts not observable)
HOST_MEAN_FLAG = 0.80          # mean host CPU busy fraction over the arm (all cores)
API_MEAN_FLAG = 0.85           # mean API-server CPU, in cores
RAM_FLAG_BYTES = 2 * 2**30     # MemAvailable at either boundary below 2 GiB -> flag
RAM_FAIL_BYTES = 2**30         # below 1 GiB -> fail
SNAPSHOT_TIMEOUT_S = 30


class SnapshotError(RuntimeError):
    pass


def take_ssh(host: str) -> dict:
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", host, "python3", "-", "--no-timers"],
                       input=HOST_SCRIPT.read_text(), capture_output=True, text=True, timeout=SNAPSHOT_TIMEOUT_S)
    if r.returncode:
        raise SnapshotError(f"ssh snapshot failed: {r.stderr[-300:]}")
    return json.loads(r.stdout)


def take_http(url: str) -> dict:
    import httpx

    from quotashift.scenario import endpoint_is_private
    ok, why = endpoint_is_private(url)
    if not ok:
        raise SnapshotError(f"snapshot endpoint rejected: {why}")
    r = httpx.get(url, timeout=SNAPSHOT_TIMEOUT_S)
    r.raise_for_status()
    return r.json()


_MOCK_STATE: dict[str, float] = {"total": 1e6, "idle": 9e5, "api": 1e4, "engine": 5e4}


def take_mock() -> dict:
    s = _MOCK_STATE
    s["total"] += 1600.0
    s["idle"] += 1400.0
    s["api"] += 2.0
    s["engine"] += 100.0
    return {"schema": "x2-host-snapshot/1", "synthetic": True, "wall": time.time(), "clk_tck": 100,
            "cpu_total": int(s["total"]), "cpu_idle": int(s["idle"]), "ncpu": 16, "pids": {"api": 1, "engine": 2},
            "ticks": {"api": int(s["api"]), "engine": int(s["engine"])}, "mem_available": 28 * 2**30,
            "oom_kill": 0, "pswpin": 0, "inventory": {"mock": 1}, "inventory_sha256": "0" * 64, "timers": None,
            "read_s": 0.0}


def taker(cfg: dict) -> Callable[[], dict]:
    t = cfg.get("transport")
    if t == "ssh":
        return lambda: take_ssh(cfg["host"])
    if t == "http":
        return lambda: take_http(cfg["url"])
    if t == "mock":
        return take_mock
    raise ValueError(f"unknown snapshot transport {t!r}")


def arm_metrics(before: dict, after: dict) -> dict:
    """Per-arm host accounting from two snapshots (means over the whole interval between them)."""
    dt_total = after["cpu_total"] - before["cpu_total"]
    host_busy = 1.0 - (after["cpu_idle"] - before["cpu_idle"]) / dt_total if dt_total > 0 else None
    wall = after["wall"] - before["wall"]
    tck = before.get("clk_tck") or 100
    cpu = {}
    for k in ("api", "engine"):
        a, b = (before.get("ticks") or {}).get(k), (after.get("ticks") or {}).get(k)
        same = (before.get("pids") or {}).get(k) == (after.get("pids") or {}).get(k)
        cpu[k] = (b - a) / tck / wall if a is not None and b is not None and same and wall > 0 else None
    mems = [x for x in (before.get("mem_available"), after.get("mem_available")) if x is not None]
    return {"interval_s": wall, "host_busy_mean": host_busy, "api_cpu_mean_cores": cpu["api"],
            "engine_cpu_mean_cores": cpu["engine"], "mem_available_min": min(mems) if mems else None,
            "oom_kill_delta": (after.get("oom_kill") or 0) - (before.get("oom_kill") or 0),
            "pswpin_delta": (after.get("pswpin") or 0) - (before.get("pswpin") or 0),
            "vllm_pids_unchanged": before.get("pids") == after.get("pids"),
            "inventory_unchanged": before.get("inventory_sha256") == after.get("inventory_sha256"),
            "synthetic": bool(before.get("synthetic") or after.get("synthetic"))}


def arm_flags(m: dict) -> dict:
    """Pre-registered: fail on OOM, a vLLM restart or MemAvailable < 1 GiB; flag the rest. Missing data -> flag."""
    fails, flags = [], []
    if m["oom_kill_delta"] > 0:
        fails.append("oom_kill")
    if not m["vllm_pids_unchanged"]:
        fails.append("vllm_pids_changed")
    if m["mem_available_min"] is not None and m["mem_available_min"] < RAM_FAIL_BYTES:
        fails.append("mem_available_below_1GiB")
    if m["host_busy_mean"] is None or m["host_busy_mean"] >= HOST_MEAN_FLAG:
        flags.append("host_cpu_mean")
    if m["api_cpu_mean_cores"] is None or m["api_cpu_mean_cores"] >= API_MEAN_FLAG:
        flags.append("api_cpu_mean")
    if m["mem_available_min"] is None or m["mem_available_min"] < RAM_FLAG_BYTES:
        flags.append("mem_available_below_2GiB")
    if m["pswpin_delta"] > 0:
        flags.append("swap_in")
    if not m["inventory_unchanged"]:
        flags.append("resident_inventory_changed")
    return {"status": "fail" if fails else ("flag" if flags else "pass"), "fails": fails, "flags": flags}


@dataclass
class Boundary:
    """The production procedure. `before()` returns only after the guard; `after()` writes the per-arm record."""
    take: Callable[[], dict]
    guard_s: float = GUARD_S
    transport: str = "mock"
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    log: list[dict] = field(default_factory=list)

    def before(self, label: str) -> dict:
        snap = self.take()
        t_ret = self.clock()                                 # guard counts from the moment the snapshot RETURNED
        remaining = self.guard_s - (self.clock() - t_ret)
        if remaining > 0:
            self.sleep(remaining)
        return {"label": label, "snapshot": snap, "guard_s": self.guard_s, "guard_end_monotonic": self.clock(),
                "transport": self.transport}

    def after(self, pre: dict, run_dir: Path | None) -> dict:
        snap = self.take()
        m = arm_metrics(pre["snapshot"], snap)
        rec = {"label": pre["label"], "transport": self.transport, "guard_s": pre["guard_s"], "before": pre["snapshot"],
               "after": snap, "metrics": m, "flags": arm_flags(m)}
        if run_dir is not None:
            (Path(run_dir) / "x2_host_snapshots.json").write_text(json.dumps(rec, indent=1))
        self.log.append(rec)
        return rec


def from_env(env: dict | None = None) -> Boundary | None:
    raw = (os.environ if env is None else env).get(ENV)
    if not raw:
        return None
    cfg = json.loads(raw)
    return Boundary(take=taker(cfg), guard_s=float(cfg.get("guard_s", GUARD_S)), transport=cfg["transport"])
