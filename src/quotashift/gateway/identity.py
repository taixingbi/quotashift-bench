"""Synthetic tenant identity for the gateway.

A bearer key maps to an experiment-owned synthetic tenant. Keys are fixtures for
an isolated, owned testbed; they are NOT real secrets and must never be reused as
such. Unknown keys are rejected (401). No real tenant data is used.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Identity(BaseModel):
    model_config = ConfigDict(frozen=True)
    tenant_id: str = Field(pattern=r"^[A-Za-z0-9_\-]+$")
    experiment_id: str
    run_id: str
    role: str = "unknown"  # victim | competitor | unknown (reporting only)


class TenantRegistry(BaseModel):
    """api_key -> Identity. `extra=forbid` so a malformed entry fails closed."""

    model_config = ConfigDict(frozen=True)
    keys: dict[str, Identity]

    def resolve(self, bearer: str | None) -> Identity | None:
        if not bearer:
            return None
        token = bearer[7:].strip() if bearer.lower().startswith("bearer ") else bearer.strip()
        return self.keys.get(token)

    @property
    def tenants(self) -> list[str]:
        return sorted({i.tenant_id for i in self.keys.values()})

    @classmethod
    def from_yaml(cls, path: str | Path) -> TenantRegistry:
        return cls.model_validate(yaml.safe_load(Path(path).read_text()))
