"""scripts/aws_ops.sh X1 guards with fake `aws` / `terraform` binaries (nothing reaches AWS):
deploy refuses a plan without the budget alarm; stop-gpu stops runner tasks first, then services, then the ASG;
run-stage refuses without a runner task definition or a single running vLLM task."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROLE = "arn:aws:sts::111122223333:assumed-role/quotashift-x1-operator/s"


def _bins(tmp: Path, *, plan: dict | None = None, running: str = "1", runner_family: str = "quotashift-research-runner",
          tasks: str = "arn:task/a arn:task/b") -> dict:
    b = tmp / "bin"
    b.mkdir()
    log = tmp / "calls.log"
    (tmp / "plan.json").write_text(json.dumps(plan or {"resource_changes": []}))
    files = {
        "aws": f'''echo "aws $*" >> {log}
case "$1 $2" in
  "sts get-caller-identity") echo "{ROLE}";;
  "ecs list-tasks") echo "{tasks}";;
  "ecs describe-services") echo "{running}";;
  "ecs run-task") echo "arn:task/new";;
esac''',
        "terraform": f'''echo "terraform $*" >> {log}
if [[ "$*" == *"show -json"* ]]; then cat {tmp / "plan.json"}; exit 0; fi
if [[ "$*" == *"output -raw runner_task_definition_family"* ]]; then echo "{runner_family}"; exit 0; fi
if [[ "$*" == *"output -raw"* ]]; then echo fake-output; exit 0; fi''',
    }
    for name, body in files.items():
        p = b / name
        p.write_text("#!/usr/bin/env bash\n" + body + "\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return {**os.environ, "PATH": f"{b}:{os.environ['PATH']}", "CALLS": str(log)}


def _run(env: dict, *args: str, approved: str | None = None) -> tuple[subprocess.CompletedProcess, list[str]]:
    e = dict(env)
    if approved:
        e["QUOTASHIFT_APPROVED"] = approved
    # gate() needs an interactive "yes": feed it on stdin
    r = subprocess.run(["bash", str(REPO / "scripts" / "aws_ops.sh"), *args], cwd=REPO, env=e, capture_output=True,
                       text=True, input="yes\n")
    p = Path(env["CALLS"])
    return r, (p.read_text().splitlines() if p.exists() else [])


def test_deploy_refuses_a_plan_without_the_budget_alarm(tmp_path):
    r, log = _run(_bins(tmp_path), "deploy", "research", approved="deploy")
    assert r.returncode == 3 and "no budget alarm" in r.stderr and not any(" apply " in x for x in log)
    t2 = tmp_path / "ok"
    t2.mkdir()
    plan = {"resource_changes": [{"type": "aws_budgets_budget", "change": {"actions": ["create"]}}]}
    r, log = _run(_bins(t2, plan=plan), "deploy", "research", approved="deploy")
    assert r.returncode == 0 and any(x.endswith("apply research.tfplan") for x in log)


def test_stop_gpu_stops_runner_tasks_then_services_then_asg(tmp_path):
    r, log = _run(_bins(tmp_path), "stop-gpu", "research")
    assert r.returncode == 0
    aws = [x for x in log if x.startswith("aws ")]
    i_stop = [i for i, x in enumerate(aws) if "ecs stop-task" in x]
    i_svc = [i for i, x in enumerate(aws) if "ecs update-service" in x and "--desired-count 0" in x]
    i_asg = [i for i, x in enumerate(aws) if "set-desired-capacity" in x and "--desired-capacity 0" in x]
    assert len(i_stop) == 2 and i_svc and i_asg and max(i_stop) < min(i_svc) < i_asg[0]


def test_run_stage_dependencies(tmp_path):
    r, log = _run(_bins(tmp_path, runner_family="null"), "run-stage", "research", "--platform", "g1m0",
                  approved="run-stage")
    assert r.returncode == 3 and "no runner task definition" in r.stderr
    t2 = tmp_path / "b"
    t2.mkdir()
    r, log = _run(_bins(t2, running="0"), "run-stage", "research", "--platform", "g1m0", approved="run-stage")
    assert r.returncode == 3 and "runningCount=0" in r.stderr and not any("run-task" in x for x in log)
    t3 = tmp_path / "c"
    t3.mkdir()
    env = _bins(t3)
    r, log = _run(env, "run-stage", "research", "--platform", "g1m0", "--phase", "calA", "--live", approved="run-stage")
    assert r.returncode == 3 and "QUOTASHIFT_STAGE_APPROVAL" in r.stderr             # stage token required
    r, log = _run({**env, "QUOTASHIFT_STAGE_APPROVAL": "x1_calA_g0m0"}, "run-stage", "research", "--platform", "g0m0",
                  approved="run-stage")
    assert r.returncode == 3                                                          # G0 platforms never run on AWS
    r, log = _run({**env, "QUOTASHIFT_STAGE_APPROVAL": "x1_calA_g1m0"}, "run-stage", "research", "--platform", "g1m0",
                  "--phase", "calA", "--live", approved="run-stage")
    rt = next(x for x in log if "ecs run-task" in x)
    assert r.returncode == 0 and "assignPublicIp=DISABLED" in rt and "scripts/x1_stage.py" in rt
    assert '"QUOTASHIFT_APPROVED", "value": "x1_calA_g1m0"' in rt
