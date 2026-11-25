"""Backend target profiles: switch between the AWS GPU and a self-hosted vLLM.

A target names *where* the fixed serving config runs (endpoint, model, context
length). It is not an experimental variable: a scenario and its control always run
on the same target. Profiles live in `configs/targets/<name>.yaml`; the active one
is `configs/targets/active.yaml` (`active: <name>`), overridable with
`QUOTASHIFT_TARGET`. Selecting a target never starts cloud resources.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from quotashift.scenario import endpoint_is_private

REPO = Path(__file__).resolve().parents[2]
TARGETS_DIR = REPO / "configs" / "targets"
ACTIVE_FILE = "active.yaml"
ENV_VAR = "QUOTASHIFT_TARGET"
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class TargetProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    kind: Literal["aws", "selfhost"]
    backend_url: str
    model: str
    model_revision: str | None = None
    max_model_len: int = Field(gt=0)
    # Hardware provenance. `gpu_type_source` says whether it was measured on the host or stated by
    # the owner; telemetry needs an exporter running ON the GPU host (quotashift gpu-exporter / DCGM).
    gpu_type: str | None = None
    gpu_type_source: Literal["owner_stated", "measured"] | None = None
    gpu_exporter_url: str | None = None
    # "none": no GPU telemetry polling at all during arms (X2 measured-window policy; docs/X2_INSTRUMENTATION_SPEC.md).
    # Default "auto" keeps the historical behaviour (exporter if configured, else local nvidia-smi).
    gpu_telemetry: Literal["auto", "none"] = "auto"

    @model_validator(mode="after")
    def _check(self) -> TargetProfile:
        if not _NAME.match(self.name):
            raise ValueError(f"invalid target name {self.name!r}")
        ok, reason = endpoint_is_private(self.backend_url)
        if not ok:
            raise ValueError(f"target {self.name}: backend_url rejected: {reason}")
        if self.gpu_exporter_url:
            ok, reason = endpoint_is_private(self.gpu_exporter_url)
            if not ok:
                raise ValueError(f"target {self.name}: gpu_exporter_url rejected: {reason}")
        return self


def _dir(targets_dir: Path | None) -> Path:
    return targets_dir or TARGETS_DIR


def list_targets(targets_dir: Path | None = None) -> list[str]:
    return sorted(p.stem for p in _dir(targets_dir).glob("*.yaml") if p.name != ACTIVE_FILE)


def load_target(name: str, targets_dir: Path | None = None) -> TargetProfile:
    if not _NAME.match(name):
        raise ValueError(f"invalid target name {name!r}")
    path = _dir(targets_dir) / f"{name}.yaml"
    if not path.exists():
        raise ValueError(f"unknown target {name!r}; have {list_targets(targets_dir)}")
    prof = TargetProfile.model_validate(yaml.safe_load(path.read_text()))
    if prof.name != name:
        raise ValueError(f"{path}: name {prof.name!r} does not match file name {name!r}")
    return prof


def active_target_name(targets_dir: Path | None = None) -> str:
    env = os.environ.get(ENV_VAR)
    if env:
        return env
    path = _dir(targets_dir) / ACTIVE_FILE
    if not path.exists():
        raise ValueError(f"no active target: create {path} or set {ENV_VAR}")
    return str((yaml.safe_load(path.read_text()) or {}).get("active", ""))


def active_target(targets_dir: Path | None = None) -> TargetProfile:
    return load_target(active_target_name(targets_dir), targets_dir)


def set_active(name: str, targets_dir: Path | None = None) -> TargetProfile:
    prof = load_target(name, targets_dir)  # validate before switching
    (_dir(targets_dir) / ACTIVE_FILE).write_text(
        "# Active backend target. Switch with `uv run quotashift target use <name>`;\n"
        f"# override per-process with {ENV_VAR}=<name>.\n"
        f"active: {name}\n"
    )
    return prof


def check_target(prof: TargetProfile, timeout_s: float = 10.0) -> dict:
    """Read-only probe: GET /v1/models and compare against the profile."""
    url = prof.backend_url.rstrip("/") + "/v1/models"
    try:
        r = httpx.get(url, timeout=timeout_s)
        r.raise_for_status()
        data = r.json().get("data", [])
    except (httpx.HTTPError, ValueError) as e:
        return {"reachable": False, "url": url, "error": f"{type(e).__name__}: {e}"}
    served = {m.get("id"): m for m in data}
    m = served.get(prof.model)
    problems = []
    if m is None:
        problems.append(f"model {prof.model!r} not served (have {sorted(served)})")
    elif m.get("max_model_len") is not None and m["max_model_len"] != prof.max_model_len:
        problems.append(f"server max_model_len={m['max_model_len']} != profile {prof.max_model_len}")
    caps = probe_capabilities(prof, timeout_s=timeout_s)
    if prof.gpu_exporter_url and not (caps.get("gpu_exporter") or {}).get("power_w_ok"):
        problems.append(f"gpu_exporter_url set but no power reading from {prof.gpu_exporter_url}")
    return {"reachable": True, "url": url, "served_models": sorted(served), "ok": not problems,
            "problems": problems, "capabilities": caps}


def parse_capabilities(openapi_paths: list[str] | None, metrics_text: str | None,
                       exporter_text: str | None) -> dict:
    """Pure parser behind `probe_capabilities` (unit-tested). None input -> that part unknown."""
    from quotashift.instrumentation.gpu import parse_exporter_text
    from quotashift.instrumentation.prom import parse_prometheus_text

    out: dict = {}
    if openapi_paths is not None:
        # listed only when vLLM runs with VLLM_SERVER_DEV_MODE=1 (needed for A7's verified reset)
        out["reset_prefix_cache_listed"] = "/reset_prefix_cache" in openapi_paths
    if metrics_text is not None:
        ms = parse_prometheus_text(metrics_text)
        cc = next((m.labels for m in ms if m.name == "vllm:cache_config_info"), {})
        val = {m.name: m.value for m in ms}
        out["prefix_caching"] = {"True": True, "False": False}.get(cc.get("enable_prefix_caching", ""))
        out["gpu_memory_utilization"] = float(cc["gpu_memory_utilization"]) if "gpu_memory_utilization" in cc else None
        out["num_gpu_blocks"] = int(cc["num_gpu_blocks"]) if cc.get("num_gpu_blocks", "None") != "None" else None
        out["process_start_time_seconds"] = val.get("process_start_time_seconds")
        out["engine_idle"] = (val.get("vllm:num_requests_running") == 0 and val.get("vllm:num_requests_waiting") == 0)
    if exporter_text is not None:
        g = parse_exporter_text(exporter_text, 0)
        out["gpu_exporter"] = {"power_w_ok": g.get("power_w") is not None, "power_w": g.get("power_w"),
                               "sm_clock_mhz": g.get("sm_clock_mhz"), "gpu_util_perc": g.get("gpu_util_perc")}
    return out


def probe_capabilities(prof: TargetProfile, timeout_s: float = 10.0) -> dict:
    """Read-only (GET only): dev-mode reset endpoint listed, prefix caching, serving config, GPU exporter.
    `prompt_tokens_details` can't be checked without sending a request, so it isn't checked here."""
    base = prof.backend_url.rstrip("/")

    def get(u: str) -> httpx.Response | None:
        try:
            r = httpx.get(u, timeout=timeout_s)
            r.raise_for_status()
            return r
        except httpx.HTTPError:
            return None

    oa = get(base + "/openapi.json")
    paths: list[str] | None = None
    if oa is not None:
        try:
            paths = sorted(oa.json().get("paths", {}))
        except ValueError:
            paths = None
    met = get(base + "/metrics")
    exp = get(prof.gpu_exporter_url) if prof.gpu_exporter_url else None
    caps = parse_capabilities(paths, met.text if met is not None else None, exp.text if exp is not None else None)
    if prof.gpu_exporter_url and exp is None:
        caps["gpu_exporter"] = {"power_w_ok": False, "error": f"unreachable: {prof.gpu_exporter_url}"}
    return caps


def write_target_snapshot(prof: TargetProfile, out: Path, *, timeout_s: float = 10.0) -> dict:
    """Read-only (GET only) record of the server state a suite ran against: target check + capabilities,
    `/version`, `/v1/models`, the `vllm:*` and `process_*` lines of `/metrics`, and the GPU exporter's
    `nvidia_smi_gpu_info`. Written under `<report>/target_snapshot/`; never contains credentials."""
    import datetime
    import json

    out.mkdir(parents=True, exist_ok=True)
    base = prof.backend_url.rstrip("/")

    def get(u: str) -> str | None:
        try:
            r = httpx.get(u, timeout=timeout_s)
            r.raise_for_status()
            return r.text
        except httpx.HTTPError:
            return None

    chk = check_target(prof, timeout_s=timeout_s)
    files = {"version.json": get(base + "/version"), "models.json": get(base + "/v1/models")}
    met = get(base + "/metrics")
    files["metrics_vllm.prom"] = None if met is None else "\n".join(
        ln for ln in met.splitlines() if ln.startswith(("vllm:", "process_start_time_seconds"))) + "\n"
    if prof.gpu_exporter_url:
        exp = get(prof.gpu_exporter_url)
        files["gpu_info.prom"] = None if exp is None else "\n".join(
            ln for ln in exp.splitlines() if ln.startswith("nvidia_smi_gpu_info")) + "\n"
    rev = model_revision_provenance(prof, timeout_s=timeout_s)
    files["model_revision.json"] = json.dumps(rev, indent=2)
    for name, text in files.items():
        if text is not None:
            (out / name).write_text(text)
    rec = {"captured_utc": datetime.datetime.now(datetime.UTC).isoformat(), "target": prof.name,
           "check": chk, "files": {k: v is not None for k, v in files.items()}}
    (out / "target_check.json").write_text(json.dumps(rec, indent=2, default=str))
    return rec


def model_revision_provenance(prof: TargetProfile, *, timeout_s: float = 10.0) -> dict:
    """Model revision as the server states it (`/server_info` -> vllm_config `revision=` / `tokenizer_revision=`),
    beside the profile's documented value. Never invents a revision: when the server reports None, the status says
    so explicitly. Only the vllm_config string is read (environment sections are not stored)."""
    import re

    base = prof.backend_url.rstrip("/")
    reported: dict[str, str | None] = {"revision": None, "tokenizer_revision": None}
    err = None
    try:
        r = httpx.get(base + "/server_info", timeout=timeout_s)
        r.raise_for_status()
        cfg = str(r.json().get("vllm_config", ""))
        for k in reported:
            m = re.search(rf"(?<![a-z_]){k}=([^,\s)]+)", cfg)
            reported[k] = None if m is None or m.group(1) == "None" else m.group(1)
    except (httpx.HTTPError, ValueError) as e:
        err = f"{type(e).__name__}"
    documented = prof.model_revision
    if reported["revision"]:
        status = f"server-reported revision {reported['revision']}"
    elif err:
        status = f"server_info unavailable ({err}); documented revision {documented or 'none'} (unverified)"
    else:
        status = ("server reports revision=None (resolved from the hub default at load time); documented revision "
                  f"{documented or 'none'} is not server-verified")
    return {"model_revision_server_reported": reported["revision"],
            "tokenizer_revision_server_reported": reported["tokenizer_revision"],
            "model_revision_documented": documented, "model_revision_status": status}


def current_server_identity(prof: TargetProfile, *, timeout_s: float = 10.0) -> dict:
    """vLLM version, process start and model-revision status right now (GET only) — recorded with frozen traces."""
    base = prof.backend_url.rstrip("/")
    ver = None
    try:
        ver = httpx.get(base + "/version", timeout=timeout_s).json().get("version")
    except (httpx.HTTPError, ValueError):
        pass
    from quotashift.local import current_server_start

    return {"vllm_version": ver, "process_start_time_seconds": current_server_start(prof),
            **model_revision_provenance(prof, timeout_s=timeout_s)}
