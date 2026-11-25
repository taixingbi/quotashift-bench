"""X1 host sampler (scripts/x1_host_sampler.py) on a fake /proc tree; no real host is touched."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import x1_host_sampler as hs  # noqa: E402

STAT = "cpu  {u} 0 {s} {i} 0 0 0 0 0 0\ncpu0 1 0 1 1 0 0 0 0 0 0\ncpu1 1 0 1 1 0 0 0 0 0 0\nintr 1\n"


def _pid(root: Path, pid: int, argv: list[str], comm: str, jiffies: int) -> None:
    d = root / "proc" / str(pid)
    d.mkdir(parents=True)
    (d / "cmdline").write_text("\0".join(argv) + "\0")
    (d / "comm").write_text(comm + "\n")
    fields = ["S"] + ["0"] * 10 + [str(jiffies), "0"] + ["0"] * 30     # utime at index 11 after ")", stime 12
    (d / "stat").write_text(f"{pid} ({comm}) " + " ".join(fields))


@pytest.fixture
def proc(tmp_path: Path) -> Path:
    root = tmp_path
    (root / "proc").mkdir()
    (root / "proc" / "stat").write_text(STAT.format(u=100, s=50, i=850))
    (root / "proc" / "meminfo").write_text("MemTotal: 16000000 kB\nMemAvailable: 4194304 kB\n")
    (root / "proc" / "vmstat").write_text("pswpin 7\noom_kill 0\npgfault 1\n")
    _pid(root, 100, ["bash", "-c", "conda activate vllm && vllm serve x"], "bash", 1)     # wrapper: never matched
    _pid(root, 101, ["/env/bin/python", "/env/bin/vllm", "serve", "m"], "python", 500)
    _pid(root, 102, ["VLLM::EngineCore"], "VLLM::EngineCor", 900)
    return root


def test_parsers(proc: Path):
    assert hs.parse_proc_stat((proc / "proc" / "stat").read_text()) == (1000, 850, 2)
    assert hs.parse_meminfo_available((proc / "proc" / "meminfo").read_text()) == 4 * 1024 ** 3
    assert hs.parse_vmstat((proc / "proc" / "vmstat").read_text()) == {"pswpin": 7, "oom_kill": 0}
    assert hs.parse_proc_pid_cpu("5 (VLLM::Engine Core) " + " ".join(["S"] + ["0"] * 10 + ["3", "4"] + ["0"] * 5)) == 7


def test_pid_discovery_skips_shell_wrapper(proc: Path):
    assert hs.find_vllm_pids(str(proc)) == {"api": 101, "engine": 102}


def test_derive_rates(proc: Path):
    a = hs.sample(str(proc), {"api": 101, "engine": 102})
    (proc / "proc" / "stat").write_text(STAT.format(u=160, s=70, i=870))          # +100 total, +20 idle
    (proc / "proc" / "101" / "stat").write_text("101 (python) " + " ".join(["S"] + ["0"] * 10 + ["550", "0"] + ["0"] * 30))
    b = hs.sample(str(proc), {"api": 101, "engine": 102})
    d = hs.derive(a, b, dt=1.0, tck=100)
    assert d["host_busy"] == pytest.approx(0.8) and d["api_cpu"] == pytest.approx(0.5) and d["engine_cpu"] == 0.0


def test_run_emits_samples_and_measured_overhead(proc: Path):
    buf = io.StringIO()
    summ = hs.run(str(proc), duration=0.35, interval=0.1, out=buf)
    lines = [json.loads(x) for x in buf.getvalue().splitlines()]
    assert lines[-1]["summary"] == summ and summ["samples"] >= 2
    assert all({"host_busy", "api_cpu", "mem_available", "oom_kill"} <= set(x) for x in lines[:-1])
    assert summ["pids"] == {"api": 101, "engine": 102} and summ["overhead_core_frac"] is not None
