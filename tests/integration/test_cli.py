import json
import subprocess
import sys

import pytest


def run(*args, cwd):
    return subprocess.run([sys.executable, "-m", "risksched.cli", *args], cwd=cwd, capture_output=True, text=True, timeout=300)


def test_generate_workload_deterministic(repo, tmp_path):
    a = run("generate-workload", "--config", "configs/tenants/three_tenants.yaml", "--seed", "11",
            "--out", str(tmp_path / "a.jsonl"), cwd=repo)
    b = run("generate-workload", "--config", "configs/tenants/three_tenants.yaml", "--seed", "11",
            "--out", str(tmp_path / "b.jsonl"), cwd=repo)
    assert a.returncode == 0, a.stderr
    assert json.loads(a.stdout)["sha256"] == json.loads(b.stdout)["sha256"]


def test_validate_env_and_doctor(repo):
    v = run("validate-env", cwd=repo)
    assert v.returncode == 0, v.stdout + v.stderr
    d = run("doctor", cwd=repo)
    assert d.returncode == 0 and "packages" in json.loads(d.stdout)


@pytest.mark.slow
def test_run_report_compare(repo, tmp_path):
    for sched in ("fcfs", "static_quota"):
        r = run("run", "--config", "configs/experiments/smoke.yaml", "--scheduler", sched, "--seed", "11",
                "--results-root", str(tmp_path), cwd=repo)
        assert r.returncode == 0, r.stdout + r.stderr
        out = json.loads(r.stdout)
        assert out["accounting_conserved"] and out["event_validation_ok"] and out["synthetic_backend"]
        rep = run("report", "--run-dir", out["run_dir"], cwd=repo)
        assert rep.returncode == 0 and json.loads(rep.stdout)["revalidated_event_errors"] == 0
    c = run("compare", "--experiment", "smoke", "--results-root", str(tmp_path), cwd=repo)
    assert c.returncode == 0 and "static_quota" in c.stdout


def test_profile_vllm_requires_explicit_cost_ack(repo, tmp_path):
    r = run("profile", "--config", "configs/experiments/e0.yaml", "--backend", "vllm", "--results-root", str(tmp_path),
            cwd=repo)
    assert r.returncode == 3 and "i-understand-gpu-costs" in r.stderr
