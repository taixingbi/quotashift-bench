"""Synthetic tenant identity for the gateway.

A bearer key maps to an experiment-owned synthetic tenant. Unknown keys are rejected
(401). No real tenant data is used. Two registry formats are accepted:

- **Legacy** (`keys:` mapping plaintext key -> identity): test fixtures for an isolated
  testbed; NOT real secrets. Kept so historical configs and tests keep working.
- **Hashed** (`tenants:` list with `key_sha256` or `key_env`): only the SHA-256 digest is
  stored; `key_env` names an environment variable holding the key, so secrets never live
  in YAML or source control.

Resolution hashes the presented token and compares against every registered digest with
`hmac.compare_digest`, so timing does not depend on which tenant matched. Keys are never
logged or echoed; `Identity` carries no key material.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator


class Identity(BaseModel):
    model_config = ConfigDict(frozen=True)
    tenant_id: str = Field(pattern=r"^[A-Za-z0-9_\-]+$")
    experiment_id: str
    run_id: str
    role: str = "unknown"  # victim | competitor | unknown (reporting only)


class HashedTenant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    tenant_id: str = Field(pattern=r"^[A-Za-z0-9_\-]+$")
    experiment_id: str
    run_id: str
    role: str = "unknown"
    key_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    key_env: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> HashedTenant:
        if (self.key_sha256 is None) == (self.key_env is None):
            raise ValueError(f"tenant {self.tenant_id}: set exactly one of key_sha256 / key_env")
        return self

    def digest(self) -> str:
        if self.key_sha256:
            return self.key_sha256
        key = os.environ.get(self.key_env or "")
        if not key:
            raise ValueError(f"tenant {self.tenant_id}: env var {self.key_env} is unset or empty (fail closed)")
        return sha256_hex(key)

    def identity(self) -> Identity:
        return Identity(tenant_id=self.tenant_id, experiment_id=self.experiment_id, run_id=self.run_id, role=self.role)


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


class TenantRegistry(BaseModel):
    """bearer key -> Identity. `extra=forbid` so a malformed entry fails closed."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    keys: dict[str, Identity] = Field(default_factory=dict)  # legacy plaintext fixtures
    tenants_hashed: list[HashedTenant] = Field(default_factory=list, alias="tenants")
    _digests: list[tuple[str, Identity]] = PrivateAttr(default_factory=list)

    @model_validator(mode="after")
    def _build(self) -> TenantRegistry:
        if not self.keys and not self.tenants_hashed:
            raise ValueError("tenant registry is empty (fail closed)")
        digests = [(sha256_hex(k), ident) for k, ident in self.keys.items()]
        digests += [(t.digest(), t.identity()) for t in self.tenants_hashed]
        seen = [d for d, _ in digests]
        if len(seen) != len(set(seen)):
            raise ValueError("two tenant entries share the same API key")
        self._digests = digests
        return self

    def resolve(self, bearer: str | None) -> Identity | None:
        if not bearer:
            return None
        token = bearer[7:].strip() if bearer.lower().startswith("bearer ") else bearer.strip()
        if not token:
            return None
        d = sha256_hex(token)
        found: Identity | None = None
        for digest, ident in self._digests:
            if hmac.compare_digest(digest, d):
                found = ident
        return found

    @property
    def tenants(self) -> list[str]:
        return sorted({i.tenant_id for _, i in self._digests})

    @classmethod
    def from_yaml(cls, path: str | Path) -> TenantRegistry:
        return cls.model_validate(yaml.safe_load(Path(path).read_text()))
