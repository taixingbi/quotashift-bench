"""X2 instrumentation: host snapshot script (fake /proc), per-arm metrics/flags, the guarded boundary procedure, the
harness hook (inert unless QUOTASHIFT_X2_BOUNDARY is set), and the X2 target / terraform policy."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import x2_host_snapshot as hs  # noqa: E402

from quotashift.x2 import snapshot as sn  # noqa: E402


def fake_root(tmp: Path, *, total=(100, 0, 50, 1000, 10, 0, 0, 0), api_ticks=(30, 20), eng_ticks=(400, 100),
              mem_kb=20_000_000, oom=0, pswpin=0, extra=()) -> Path:
    r = tmp / "root"
    p = r / "proc"
    p.mkdir(parents=True, exist_ok=True)
    (p / "stat").write_text("cpu  " + " ".join(map(str, total)) + "\ncpu0 1 2 3 4\ncpu1 1 2 3 4\n")
    (p / "meminfo").write_text(f"MemTotal: 32000000 kB\nMemAvailable: {mem_kb} kB\n")
    (p / "vmstat").write_text(f"pgfault 1\noom_kill {oom}\npswpin {pswpin}\n")

    def proc(pid: int, argv: list[str], comm: str, ticks: tuple[int, int] = (0, 0)) -> None:
        d = p / str(pid)
        d.mkdir(exist_ok=True)
        (d / "cmdline").write_text("\0".join(argv) + "\0")
        (d / "comm").write_text(comm + "\n")
        fields = ["S"] + ["0"] * 10 + [str(ticks[0]), str(ticks[1])] + ["0"] * 30
        (d / "stat").write_text(f"{pid} ({comm}) " + " ".join(fields))
    proc(100, ["/env/bin/python", "/env/bin/vllm", "serve", "m"], "python", api_ticks)
    proc(101, ["VLLM::EngineCore"], "VLLM::EngineCor", eng_ticks)
    proc(102, ["/usr/sbin/sshd", "-D"], "sshd")
    (p / "7").mkdir(exist_ok=True)                                   # kernel thread: empty cmdline -> excluded
    (p / "7" / "cmdline").write_text("")
    for i, name in enumerate(extra):
        proc(200 + i, [f"/usr/bin/{name}"], name)
    return r


def test_host_snapshot_reads_proc_and_finds_vllm(tmp_path):
    s = hs.snapshot(str(fake_root(tmp_path)), with_timers=False)
    assert s["schema"] == "x2-host-snapshot/1" and s["ncpu"] == 2
    assert s["pids"] == {"api": 100, "engine": 101} and s["ticks"] == {"api": 50, "engine": 500}
    assert s["cpu_total"] == 1160 and s["cpu_idle"] == 1010 and s["mem_available"] == 20_000_000 * 1024
    assert s["inventory"] == {"VLLM::EngineCor": 1, "python": 1, "sshd": 1} and len(s["inventory_sha256"]) == 64


def test_host_snapshot_cli_is_read_only_json(tmp_path):
    root = fake_root(tmp_path)
    before = sorted((p, p.stat().st_mtime_ns) for p in root.rglob("*"))
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "x2_host_snapshot.py"), "--proc-root", str(root),
                        "--no-timers"], capture_output=True, text=True)
    assert r.returncode == 0 and json.loads(r.stdout)["pids"]["engine"] == 101
    assert sorted((p, p.stat().st_mtime_ns) for p in root.rglob("*")) == before


def _snap(tmp: Path, name: str, **kw) -> dict:  # noqa: ANN003
    return hs.snapshot(str(fake_root(tmp / name, **kw)), with_timers=False)


def test_arm_metrics_and_flags(tmp_path):
    a = _snap(tmp_path, "a") | {"wall": 1000.0}
    b = _snap(tmp_path, "b", total=(200, 0, 100, 1100, 10, 0, 0, 0), api_ticks=(130, 20), eng_ticks=(900, 100)) | {"wall": 1010.0}
    m = sn.arm_metrics(a, b)
    assert m["host_busy_mean"] == pytest.approx(1 - 100 / 250) and m["api_cpu_mean_cores"] == pytest.approx(0.1)
    assert m["engine_cpu_mean_cores"] == pytest.approx(0.5) and m["vllm_pids_unchanged"] and m["inventory_unchanged"]
    assert sn.arm_flags(m) == {"status": "pass", "fails": [], "flags": []}
    oom = sn.arm_metrics(a, _snap(tmp_path, "c", oom=1) | {"wall": 1010.0})
    assert sn.arm_flags(oom)["status"] == "fail" and "oom_kill" in sn.arm_flags(oom)["fails"]
    inv = sn.arm_metrics(a, _snap(tmp_path, "d", extra=("apt",)) | {"wall": 1010.0})
    assert sn.arm_flags(inv)["status"] == "flag" and "resident_inventory_changed" in sn.arm_flags(inv)["flags"]
    low = sn.arm_metrics(a, _snap(tmp_path, "e", mem_kb=500_000) | {"wall": 1010.0})
    assert "mem_available_below_1GiB" in sn.arm_flags(low)["fails"]


def test_boundary_guard_counts_from_snapshot_return_and_writes_record(tmp_path):
    t = {"now": 0.0}
    calls: list[str] = []

    def take() -> dict:
        calls.append("snap")
        t["now"] += 1.0                                   # the snapshot itself takes 1 s
        return sn.take_mock()

    slept: list[float] = []
    b = sn.Boundary(take=take, guard_s=15.0, transport="mock", sleep=lambda s: (slept.append(s), t.__setitem__("now", t["now"] + s)),
                    clock=lambda: t["now"])
    pre = b.before("x/1/attack")
    assert slept == [15.0] and calls == ["snap"] and pre["guard_s"] == 15.0
    rec = b.after(pre, tmp_path)
    assert calls == ["snap", "snap"] and rec["flags"]["status"] in ("pass", "flag")
    assert json.loads((tmp_path / "x2_host_snapshots.json").read_text())["metrics"]["synthetic"] is True


def test_from_env_is_inert_unless_set():
    assert sn.from_env({}) is None
    b = sn.from_env({sn.ENV: json.dumps({"transport": "mock", "guard_s": 0})})
    assert b is not None and b.guard_s == 0 and b.transport == "mock"
    with pytest.raises(ValueError):
        sn.from_env({sn.ENV: json.dumps({"transport": "telnet"})})


def test_http_transport_refuses_public_endpoints():
    with pytest.raises(sn.SnapshotError):
        sn.take_http("http://example.com:9500/")


def test_x2_targets_disable_gpu_polling_and_exporters():
    from quotashift.local import backend_for
    from quotashift.scenario import load_scenario
    from quotashift.targets import TargetProfile

    sc = load_scenario(REPO / "experiments" / "smoke.yaml")
    for n in ("x2-g0-qwen", "x2-g0-mistral", "x2-g1-qwen", "x2-g1-mistral"):
        t = TargetProfile(**yaml.safe_load((REPO / "configs" / "targets" / f"{n}.yaml").read_text()))
        assert t.gpu_telemetry == "none" and t.gpu_exporter_url is None
        b = backend_for(sc, t.model_copy(update={"max_model_len": 1 << 20}))
        assert b.gpu_source == "none" and b.gpu_exporter_url is None
    x1 = TargetProfile(**yaml.safe_load((REPO / "configs" / "targets" / "x1-g1-qwen.yaml").read_text()))
    assert x1.gpu_telemetry == "auto" and backend_for(sc, x1.model_copy(update={"max_model_len": 1 << 20})).gpu_source == "exporter"


def test_x2_tfvars_disable_sampler_and_dcgm_and_enable_snapshotd():
    txt = (REPO / "infra" / "terraform" / "envs" / "research.x2.tfvars").read_text()
    kv = dict(ln.split("=", 1) for ln in (x.split("#")[0].strip() for x in txt.splitlines()) if "=" in ln)
    kv = {k.strip(): v.strip() for k, v in kv.items()}
    assert kv["enable_host_sampler"] == "false" and kv["enable_dcgm_exporter"] == "false"
    assert kv["enable_x2_snapshotd"] == "true"
