"""GPU telemetry. Scope: ENGINE-GLOBAL (whole GPU, all clients). Never fabricated.

Sources (`source=`):
- `nvidia-smi` (default; historical behaviour): run `nvidia-smi` locally, or through a command
  prefix such as `["ssh", "user@gpu-host"]` when the runner is not on the GPU host.
- `exporter`: scrape a Prometheus endpoint on the GPU host — DCGM Exporter (`DCGM_FI_DEV_*`),
  utkuozdemir/nvidia_gpu_exporter (`nvidia_smi_*`, port 9835, labelled by GPU uuid; index taken from
  `nvidia_smi_gpu_info`), or QuotaShift's own exporter (`quotashift gpu-exporter`, run ON the GPU host).
- `none`: no telemetry.

Fields: GPU util %, VRAM used/total (MiB), power (W), temperature (C), SM and memory clocks
(MHz) when available. A failed or unavailable sample is reported (`sample_error` /
`available=False`); missing fields are None — values are never interpolated.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
from typing import Any

import httpx

from quotashift.instrumentation.prom import parse_prometheus_text

_FIELDS = {
    "utilization.gpu": "gpu_util_perc",
    "memory.used": "mem_used_mib",
    "memory.total": "mem_total_mib",
    "temperature.gpu": "temp_c",
    "clocks.sm": "sm_clock_mhz",
    "clocks.mem": "mem_clock_mhz",
    "power.draw": "power_w",
}
DCGM = {
    "DCGM_FI_DEV_GPU_UTIL": "gpu_util_perc",
    "DCGM_FI_DEV_FB_USED": "mem_used_mib",
    "DCGM_FI_DEV_FB_FREE": "mem_free_mib",
    "DCGM_FI_DEV_POWER_USAGE": "power_w",
    "DCGM_FI_DEV_GPU_TEMP": "temp_c",
    "DCGM_FI_DEV_SM_CLOCK": "sm_clock_mhz",
    "DCGM_FI_DEV_MEM_CLOCK": "mem_clock_mhz",
}
OWN_PREFIX = "quotashift_gpu_"
# nvidia_gpu_exporter (v2.x) metric -> (field, multiplier to our unit)
NVSMI = {
    "nvidia_smi_utilization_gpu_ratio": ("gpu_util_perc", 100.0),
    "nvidia_smi_memory_used_bytes": ("mem_used_mib", 1 / 2**20),
    "nvidia_smi_memory_total_bytes": ("mem_total_mib", 1 / 2**20),
    "nvidia_smi_power_draw_watts": ("power_w", 1.0),
    "nvidia_smi_temperature_gpu": ("temp_c", 1.0),
    "nvidia_smi_clocks_current_sm_clock_hz": ("sm_clock_mhz", 1e-6),
    "nvidia_smi_clocks_current_memory_clock_hz": ("mem_clock_mhz", 1e-6),
}


def parse_smi_csv(text: str) -> dict[str, float | None]:
    """First GPU line of `--format=csv,noheader,nounits`; `[N/A]` -> None."""
    line = text.strip().splitlines()[0] if text.strip() else ""
    vals = [v.strip() for v in line.split(",")]
    res: dict[str, float | None] = {}
    for (_, key), v in zip(_FIELDS.items(), vals, strict=False):
        try:
            res[key] = float(v)
        except ValueError:
            res[key] = None
    return res


def parse_exporter_text(text: str, gpu_index: int = 0) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    samples = parse_prometheus_text(text)
    uuid_index = {s.labels["uuid"]: s.labels.get("index") for s in samples
                  if s.name == "nvidia_smi_gpu_info" and "uuid" in s.labels}
    for s in samples:
        if s.name in NVSMI:
            # uuid-labelled; an unknown uuid is never assumed to be the requested GPU
            if str(uuid_index.get(s.labels.get("uuid", ""))) != str(gpu_index):
                continue
            field, mult = NVSMI[s.name]
            out[field] = s.value * mult
            continue
        g = s.labels.get("gpu", s.labels.get("gpu_index", "0"))
        if str(g) != str(gpu_index):
            continue
        if s.name in DCGM:
            out[DCGM[s.name]] = s.value
        elif s.name.startswith(OWN_PREFIX) and s.name != OWN_PREFIX + "sample_ok":
            out[s.name[len(OWN_PREFIX):]] = s.value
    if "mem_total_mib" not in out and out.get("mem_used_mib") is not None and out.get("mem_free_mib") is not None:
        out["mem_total_mib"] = out["mem_used_mib"] + out["mem_free_mib"]  # type: ignore[operator]
    return out


class GpuSampler:
    def __init__(self, index: int = 0, *, source: str = "nvidia-smi", smi_prefix: list[str] | None = None,
                 exporter_url: str | None = None) -> None:
        if source not in ("nvidia-smi", "exporter", "none"):
            raise ValueError(f"unknown GPU telemetry source {source!r}")
        if source == "exporter" and not exporter_url:
            raise ValueError("GPU source 'exporter' needs exporter_url")
        if exporter_url:
            from quotashift.scenario import endpoint_is_private

            ok, reason = endpoint_is_private(exporter_url)
            if not ok:
                raise ValueError(f"GPU exporter URL rejected: {reason}")
        self.index = index
        self.source = source
        self.smi_prefix = list(smi_prefix or [])
        self.exporter_url = exporter_url
        self.binary = shutil.which("nvidia-smi") if source == "nvidia-smi" and not self.smi_prefix else None
        if source == "nvidia-smi":
            self.available = bool(self.smi_prefix) or self.binary is not None
        else:
            self.available = source == "exporter"

    def _smi(self, args: list[str]) -> list[str]:
        return [*self.smi_prefix, self.binary or "nvidia-smi", *args]

    def sample(self) -> dict:
        """Synchronous sample (nvidia-smi sources; exporter via a short blocking GET)."""
        if not self.available:
            return {}
        if self.source == "exporter":
            try:
                r = httpx.get(self.exporter_url, timeout=2.0)  # type: ignore[arg-type]
                r.raise_for_status()
                vals = parse_exporter_text(r.text, self.index)
                return vals if vals else {"sample_error": 1}
            except httpx.HTTPError:
                return {"sample_error": 1}
        try:
            out = subprocess.run(
                self._smi([f"--id={self.index}", f"--query-gpu={','.join(_FIELDS)}", "--format=csv,noheader,nounits"]),
                capture_output=True, text=True, timeout=5, check=True,
            ).stdout
        except (subprocess.SubprocessError, OSError):
            return {"sample_error": 1}
        return parse_smi_csv(out)

    async def asample(self) -> dict:
        if not self.available:
            return {}
        if self.source == "exporter":
            try:
                async with httpx.AsyncClient(timeout=2.0) as c:
                    r = await c.get(self.exporter_url)  # type: ignore[arg-type]
                    r.raise_for_status()
                vals = parse_exporter_text(r.text, self.index)
                return vals if vals else {"sample_error": 1}
            except httpx.HTTPError:
                return {"sample_error": 1}
        return await asyncio.to_thread(self.sample)

    def static_info(self) -> dict:
        if not self.available:
            return {"available": False, "source": self.source, "reason": "no GPU telemetry source on this host"}
        if self.source == "exporter":
            info: dict[str, Any] = {"available": True, "source": "exporter", "exporter_url": self.exporter_url}
            try:
                r = httpx.get(self.exporter_url, timeout=2.0)  # type: ignore[arg-type]
                r.raise_for_status()
                gi = [x.labels for x in parse_prometheus_text(r.text)
                      if x.name == "nvidia_smi_gpu_info" and str(x.labels.get("index")) == str(self.index)]
            except httpx.HTTPError as e:
                return info | {"reachable": False, "reason": str(e)}
            if gi:  # reported by the exporter, i.e. measured on the host (not owner-stated)
                keys = ("name", "uuid", "driver_version", "cuda_version", "vbios_version", "pci_bus_id", "compute_cap")
                info["gpu"] = {k: gi[0].get(k) for k in keys}
            else:
                info["note"] = "GPU model/driver not exposed by this exporter; record from the GPU host"
            return info
        try:
            out = subprocess.run(
                self._smi(["--query-gpu=name,driver_version,memory.total,pci.bus_id", "--format=csv,noheader"]),
                capture_output=True, text=True, timeout=5, check=True,
            ).stdout.strip()
            cuda = subprocess.run(self._smi([]), capture_output=True, text=True, timeout=5).stdout
            cuda_line = next((ln for ln in cuda.splitlines() if "CUDA Version" in ln), "")
            return {"available": True, "source": "nvidia-smi", "gpus": out.splitlines(), "header": cuda_line.strip()}
        except (subprocess.SubprocessError, OSError) as e:
            return {"available": False, "source": self.source, "reason": str(e)}


IDLE_MAX_SM_CLOCK_MHZ = 500.0  # idle P-state SM clock is ~210 MHz on the RTX 3090; under load > 1000 MHz


def idle_settled(samples: list[dict], *, window: int = 6, max_spread_w: float = 15.0,
                 max_sm_clock_mhz: float = IDLE_MAX_SM_CLOCK_MHZ) -> bool:
    """True when the last `window` samples are in the idle state: GPU util 0, SM clock in the idle P-state
    (when the source reports clocks), and power spread <= `max_spread_w` (excludes the P-state transition).

    Measured on the RTX 3090 (2026-11-21): after work the GPU holds load clocks (SM 1725 / mem 9501 MHz) at
    ~130 W with 0% util for ~16 s before dropping to idle (SM 210 / mem 405 MHz, ~31 W, ~40 W blips every
    ~7 s). Util + power stability alone accepted that 130 W plateau as "idle", so clocks are required."""
    last = samples[-window:]
    if len(last) < window or any(x.get("power_w") is None for x in last):
        return False
    if any((x.get("gpu_util_perc") or 0) > 0 for x in last):
        return False
    if any(x.get("sm_clock_mhz") is not None and x["sm_clock_mhz"] > max_sm_clock_mhz for x in last):
        return False
    pw = [x["power_w"] for x in last]
    return max(pw) - min(pw) <= max_spread_w


def _median(v: list[float]) -> float:
    v = sorted(v)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


async def settle_idle_power(gpu: GpuSampler, *, timeout_s: float = 90.0, interval_s: float = 0.5,
                            window: int = 6, max_spread_w: float = 15.0,
                            t_origin: float | None = None) -> dict[str, Any]:
    """Bounded wait for the GPU to reach the idle state; idle power = median of the settled window (robust
    to periodic blips). Not settled within `timeout_s` -> idle_power_w None (dynamic energy unavailable,
    never guessed). `samples` holds (t, power_w) relative to `t_origin` (monotonic) for tail integration."""
    t0 = time.monotonic()
    origin = t0 if t_origin is None else t_origin
    samples: list[dict] = []
    series: list[tuple[float, float]] = []
    while time.monotonic() - t0 < timeout_s:
        v = await gpu.asample()
        samples.append(v)
        if v.get("power_w") is not None:
            series.append((time.monotonic() - origin, v["power_w"]))
        if idle_settled(samples, window=window, max_spread_w=max_spread_w):
            last = samples[-window:]
            clocks = all(x.get("sm_clock_mhz") is not None for x in last)
            return {"settled": True, "idle_power_w": _median([x["power_w"] for x in last]),
                    "settle_s": time.monotonic() - t0, "n_samples": len(samples),
                    "first_power_w": samples[0].get("power_w"), "series": series,
                    "criterion": (f"last {window} samples: util=0, power spread <= {max_spread_w} W"
                                  + (f", SM clock <= {IDLE_MAX_SM_CLOCK_MHZ:.0f} MHz" if clocks
                                     else " (no clock data: power-only criterion, weaker)"))}
        await asyncio.sleep(interval_s)
    return {"settled": False, "idle_power_w": None, "settle_s": time.monotonic() - t0, "n_samples": len(samples),
            "first_power_w": samples[0].get("power_w") if samples else None,
            "last_power_w": samples[-1].get("power_w") if samples else None, "series": series}


def trapezoid_j(series: list[tuple[float, float]]) -> float | None:
    if len(series) < 2:
        return None
    return sum((t2 - t1) * (p1 + p2) / 2 for (t1, p1), (t2, p2) in zip(series, series[1:], strict=False))


def exporter_metrics_text(sampler: GpuSampler | None = None) -> str:
    """Prometheus text for `quotashift gpu-exporter` (run on the GPU host)."""
    s = sampler or GpuSampler()
    vals: dict[str, Any] = s.sample()
    ok = bool(vals) and "sample_error" not in vals
    lines = [f"# QuotaShift GPU exporter (nvidia-smi). scope=engine_global source={s.source}"]
    for k, v in vals.items():
        if k != "sample_error" and v is not None:
            lines.append(f'{OWN_PREFIX}{k}{{gpu="{s.index}"}} {v}')
    lines.append(f"{OWN_PREFIX}sample_ok {1 if ok else 0}")
    return "\n".join(lines) + "\n"
