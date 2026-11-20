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

    @model_validator(mode="after")
    def _check(self) -> TargetProfile:
        if not _NAME.match(self.name):
            raise ValueError(f"invalid target name {self.name!r}")
        ok, reason = endpoint_is_private(self.backend_url)
        if not ok:
            raise ValueError(f"target {self.name}: backend_url rejected: {reason}")
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
    return {"reachable": True, "url": url, "served_models": sorted(served), "ok": not problems,
            "problems": problems}
