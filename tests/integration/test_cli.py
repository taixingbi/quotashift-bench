import json
import subprocess
import sys


def run(*args, cwd):
    return subprocess.run([sys.executable, "-m", "quotashift.cli", *args], cwd=cwd, capture_output=True, text=True, timeout=300)


def test_doctor(repo):
    d = run("doctor", cwd=repo)
    assert d.returncode == 0 and "packages" in json.loads(d.stdout)


def test_validate_ok(repo):
    r = run("validate", "experiments/smoke.yaml", cwd=repo)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["valid"] and out["scenario_id"] == "smoke" and len(out["schedule_sha256"]) == 64


def test_validate_rejects_bad_scenario(repo, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "schema_version: 1\nscenario_id: bad\nseed: 1\nmodel: m\nruntime_seconds: 10\n"
        "endpoint: http://evil.example.com:8080\n"
        "victim_tenants: [v]\ncompeting_tenants: []\nphases: []\n"
        "safety: {max_total_requests: 10, max_global_inflight: 1, max_requests_per_tenant: 10,"
        " max_input_tokens_per_request: 8, max_output_tokens_per_request: 8, max_runtime_seconds: 60}\n"
        "comparison: {primary_control: benign_only}\n"
        "benign: {rate_rps: 0.1}\n"
    )
    r = run("validate", str(bad), cwd=repo)
    assert r.returncode == 2 and "endpoint" in r.stderr.lower()


def test_dry_run_is_deterministic(repo):
    a = run("dry-run", "experiments/stateful_sequences.yaml", cwd=repo)
    b = run("dry-run", "experiments/stateful_sequences.yaml", cwd=repo)
    assert a.returncode == 0 and b.returncode == 0
    assert json.loads(a.stdout)["schedule_sha256"] == json.loads(b.stdout)["schedule_sha256"]


def test_dry_run_control_differs(repo):
    base = run("dry-run", "experiments/stateful_sequences.yaml", cwd=repo)
    ctrl = run("dry-run", "experiments/stateful_sequences.yaml", "--control", cwd=repo)
    assert json.loads(base.stdout)["schedule_sha256"] != json.loads(ctrl.stdout)["schedule_sha256"]


def test_run_local_requires_mock(repo, tmp_path):
    r = run("run-local", "experiments/smoke.yaml", "--results-root", str(tmp_path), cwd=repo)
    assert r.returncode == 3 and "mock" in r.stderr.lower()


def test_run_local_and_summarize(repo, tmp_path):
    r = run("run-local", "experiments/smoke.yaml", "--mock", "--results-root", str(tmp_path), cwd=repo)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out["accounting_conserved"] and out["event_validation_ok"] and out["synthetic_backend"]
    s = run("summarize", "--input", str(tmp_path), "--output", str(tmp_path / "rep"), cwd=repo)
    assert s.returncode == 0 and (tmp_path / "rep" / "summary.csv").exists()
