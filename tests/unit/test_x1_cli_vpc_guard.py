"""`experiment --live` accepts an AWS target ONLY inside the VPC runner task (QUOTASHIFT_IN_VPC_RUNNER=1, set by the
Terraform runner task definition). Nothing is contacted: the guard is checked before any network access."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _run(extra_env: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "QUOTASHIFT_IN_VPC_RUNNER"} | extra_env
    return subprocess.run([sys.executable, "-m", "quotashift.cli", "experiment", "does-not-exist.yaml", "--live",
                           "--target", "x1-g1-qwen", "--out", "/nonexistent/out"], cwd=REPO, env=env,
                          capture_output=True, text=True)


def test_workstation_cannot_drive_an_aws_target():
    r = _run({})
    assert r.returncode == 3 and "inside the VPC runner" in r.stderr


def test_in_vpc_runner_passes_the_guard():
    r = _run({"QUOTASHIFT_IN_VPC_RUNNER": "1"})
    assert "inside the VPC runner" not in r.stderr and r.returncode != 3      # next failure: the missing scenario file
