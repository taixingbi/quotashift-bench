"""Optional GPU sampler via `nvidia-smi` (absent on non-NVIDIA hosts).

On hosts without NVIDIA tooling the sampler reports `available=False`; no
values are fabricated. DCGM-exporter scraping is the planned ECS path.
"""

from __future__ import annotations

import shutil
import subprocess

_FIELDS = {
    "utilization.gpu": "gpu_util_perc",
    "memory.used": "mem_used_mib",
    "memory.total": "mem_total_mib",
    "temperature.gpu": "temp_c",
    "clocks.sm": "sm_clock_mhz",
    "power.draw": "power_w",
}


class GpuSampler:
    def __init__(self, index: int = 0) -> None:
        self.index = index
        self.binary = shutil.which("nvidia-smi")
        self.available = self.binary is not None

    def sample(self) -> dict:
        if not self.available:
            return {}
        try:
            out = subprocess.run(
                [self.binary, f"--id={self.index}", f"--query-gpu={','.join(_FIELDS)}", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5, check=True,
            ).stdout.strip()
        except (subprocess.SubprocessError, OSError):
            return {"sample_error": 1}
        vals = [v.strip() for v in out.split(",")]
        res = {}
        for (_, key), v in zip(_FIELDS.items(), vals, strict=False):
            try:
                res[key] = float(v)
            except ValueError:
                res[key] = None
        return res

    def static_info(self) -> dict:
        if not self.available:
            return {"available": False, "reason": "nvidia-smi not found"}
        try:
            out = subprocess.run(
                [self.binary, "--query-gpu=name,driver_version,memory.total,pci.bus_id", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5, check=True,
            ).stdout.strip()
            cuda = subprocess.run([self.binary], capture_output=True, text=True, timeout=5).stdout
            cuda_line = next((ln for ln in cuda.splitlines() if "CUDA Version" in ln), "")
            return {"available": True, "gpus": out.splitlines(), "header": cuda_line.strip()}
        except (subprocess.SubprocessError, OSError) as e:
            return {"available": False, "reason": str(e)}
