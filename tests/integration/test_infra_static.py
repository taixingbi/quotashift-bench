"""Static infrastructure checks. No AWS credentials or API calls (terraform uses a mock provider)."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

TF = Path(__file__).resolve().parents[2] / "infra" / "terraform"
needs_tf = pytest.mark.skipif(shutil.which("terraform") is None, reason="terraform not installed")


def tf(*args):
    env = os.environ | {"AWS_ACCESS_KEY_ID": "", "AWS_SECRET_ACCESS_KEY": "", "AWS_PROFILE": "", "TF_IN_AUTOMATION": "1"}
    return subprocess.run(["terraform", f"-chdir={TF}", *args], capture_output=True, text=True, timeout=600, env=env)


@needs_tf
def test_terraform_fmt():
    r = tf("fmt", "-check", "-recursive")
    assert r.returncode == 0, r.stdout + r.stderr


@needs_tf
@pytest.mark.slow
def test_terraform_validate_and_mock_plan_tests():
    assert tf("init", "-backend=false", "-input=false").returncode == 0
    v = tf("validate")
    assert v.returncode == 0, v.stdout + v.stderr
    t = tf("test")
    assert t.returncode == 0 and "0 failed" in t.stdout, t.stdout + t.stderr


def test_all_images_digest_pinned(repo):
    files = [*TF.glob("*.tf"), repo / "docker" / "compose.yaml", repo / "docker" / "Dockerfile"]
    lines = [ln for p in files for ln in p.read_text().splitlines() if not ln.lstrip().startswith("#")]
    blob = "\n".join(lines)
    pat = r"(vllm/vllm-openai[^\s\"]*|nvidia/dcgm-exporter[^\s\"]*|python:3[^\s\"]*|astral-sh/uv[^\s\"]*)"
    found = re.findall(pat, blob)
    assert len(found) >= 4
    for img in found:
        assert "@sha256:" in img, f"unpinned image reference: {img}"


def test_no_state_or_secrets_tracked(repo):
    gi = (repo / ".gitignore").read_text()
    for pat in ("*.tfstate", "infra/terraform/backend.hcl", ".env"):
        assert pat in gi
    assert not list(TF.glob("*.tfstate*"))


def test_gated_actions_refuse_without_approval(repo):
    for action in ("deploy", "start-gpu", "destroy", "cost-report"):
        r = subprocess.run(["bash", "scripts/aws_ops.sh", action, "dev"], cwd=repo, capture_output=True, text=True,
                           env=os.environ | {"QUOTASHIFT_APPROVED": ""}, timeout=30)
        assert r.returncode == 3 and "REFUSED" in r.stderr, (action, r.stderr)


def test_cost_estimator_refuses_blank_prices(repo):
    r = subprocess.run(["python", "scripts/estimate_cost.py", "--prices", "configs/infrastructure/prices.example.yaml",
                        "--gpu-hours", "10"], cwd=repo, capture_output=True, text=True, timeout=60)
    assert r.returncode == 2 and "missing values" in r.stderr
