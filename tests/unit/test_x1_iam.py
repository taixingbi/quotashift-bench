"""X1-B least-privilege preparation: aws_ops.sh refuses ROOT credentials (fake `aws`/`terraform` on PATH; nothing
reaches AWS) and the drafted IAM policies keep their guard rails."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _fake_bin(tmp: Path, arn: str) -> dict:
    b = tmp / "bin"
    b.mkdir()
    log = tmp / "calls.log"
    for name, body in {
        "aws": f'echo "aws $*" >> {log}\nif [[ "$1 $2" == "sts get-caller-identity" ]]; then echo "{arn}"; fi\n',
        "terraform": f'echo "terraform $*" >> {log}\necho fake-output\n',
    }.items():
        p = b / name
        p.write_text("#!/usr/bin/env bash\n" + body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return {**os.environ, "PATH": f"{b}:{os.environ['PATH']}", "CALLS": str(log)}


def _run(tmp: Path, arn: str, *args: str) -> tuple[subprocess.CompletedProcess, str]:
    env = _fake_bin(tmp, arn)
    r = subprocess.run(["bash", str(REPO / "scripts" / "aws_ops.sh"), *args], cwd=REPO, env=env,
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    log = Path(env["CALLS"]).read_text() if Path(env["CALLS"]).exists() else ""
    return r, log


@pytest.mark.parametrize("action", ["plan", "deploy", "start-gpu", "destroy", "healthcheck", "cost-report"])
def test_root_credentials_are_refused(tmp_path, action):
    r, log = _run(tmp_path, "arn:aws:iam::111122223333:root", action, "research")
    assert r.returncode == 3 and "ROOT" in r.stderr
    assert "terraform" not in log and log.count("aws ") == 1           # only the identity lookup happened
    assert "111122223333" not in r.stderr                               # the ARN/account is not printed


def test_stop_gpu_stays_allowed_with_any_identity(tmp_path):
    r, log = _run(tmp_path, "arn:aws:iam::111122223333:root", "stop-gpu", "research")
    assert r.returncode == 0 and "set-desired-capacity" in log and "sts get-caller-identity" not in log


def test_role_session_passes_identity_check_but_gates_still_apply(tmp_path):
    arn = "arn:aws:sts::111122223333:assumed-role/quotashift-x1-operator/session"
    r, _ = _run(tmp_path, arn, "deploy", "research")
    assert r.returncode == 3 and "approval-gated" in r.stderr           # no QUOTASHIFT_APPROVED -> still refused


def test_policies_parse_and_keep_guard_rails():
    op = json.loads((REPO / "infra" / "iam" / "x1-operator-policy.json").read_text())
    ro = json.loads((REPO / "infra" / "iam" / "x1-readonly-policy.json").read_text())
    sids = {s["Sid"]: s for s in op["Statement"]}
    deny_types = sids["DenyOtherInstanceTypesAndSpot"]
    assert deny_types["Effect"] == "Deny" and deny_types["Condition"]["StringNotEquals"]["ec2:InstanceType"] == "g6.xlarge"
    deny = sids["DenyCostExplorerQuotaAndCredentialChanges"]["Action"]
    for a in ("ce:*", "servicequotas:RequestServiceQuotaIncrease", "iam:CreateAccessKey", "iam:CreateUser"):
        assert a in deny
    for pol in (op, ro):
        for s in pol["Statement"]:
            acts = s.get("Action", [])
            acts = [acts] if isinstance(acts, str) else acts
            assert not (s["Effect"] == "Allow" and ("*" in acts or any(a.endswith(":*") for a in acts))), s["Sid"]
    pr = sids["PassProjectRolesToEcsAndEc2"]
    assert pr["Resource"] == "arn:aws:iam::*:role/quotashift-*"


def test_no_real_account_ids_in_iam_files():
    for p in (REPO / "infra" / "iam").glob("*.json"):
        assert not re.search(r"\b\d{12}\b", p.read_text()), p
