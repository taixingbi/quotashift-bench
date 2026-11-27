"""X2 G1 orchestration, offline: runner image contents vs every pinned file, aws_ops.sh X2 routing / refusals (fake
`aws` and `terraform`; nothing reaches AWS), and the in-VPC entry wrapper's integrity checks."""

from __future__ import annotations

import fnmatch
import io
import json
import os
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import pin_x1  # noqa: E402
import pin_x1_amendment  # noqa: E402
import pin_x2  # noqa: E402
import x2_runner_entry as ent  # noqa: E402

ROLE = "arn:aws:sts::111122223333:assumed-role/quotashift-x1-operator/s"
SHA = "a" * 64


# ------------------------------------------------------------------------------------------------ image contents
def _copy_sources() -> list[str]:
    srcs: list[str] = []
    for ln in (REPO / "docker" / "Dockerfile").read_text().splitlines():
        if ln.startswith("COPY ") and "--from=" not in ln:
            parts = ln.split()[1:]
            srcs += [p.rstrip("/") for p in parts[:-1]]
    return srcs


def _ignored(rel: str) -> bool:
    pats = [x.strip() for x in (REPO / ".dockerignore").read_text().splitlines() if x.strip() and not x.startswith("#")]
    return any(rel == p or rel.startswith(p.rstrip("/") + "/") or fnmatch.fnmatch(rel, p) for p in pats)


def _in_image(rel: str) -> bool:
    return any(rel == s or rel.startswith(s + "/") for s in _copy_sources()) and not _ignored(rel)


def test_image_contains_every_pinned_file_and_no_raw_evidence():
    pinned = {*pin_x2.FILES, *pin_x1.FILES, *pin_x1_amendment.FILES, *pin_x1.V5_DEPENDENCIES, *pin_x2.V5_DEPENDENCIES,
              "experiments/x2/FROZEN_SHA256.json", "experiments/x1/FROZEN_SHA256.json",
              "experiments/x1/AMENDMENT_A1_SHA256.json", "experiments/v5/FROZEN_SHA256.json"}
    import pin_v5
    import pin_x2_a2
    import pin_x2_a3
    pinned |= {*pin_x2_a2.FILES, *pin_x2_a3.FILES, *pin_x2_a3.EARLIER, "experiments/x2_a3/AMENDMENT_A3_SHA256.json",
               *json.loads(pin_v5.MANIFEST.read_text())["files"]}      # A3 --check runs the FULL v5 check in the runner
    missing = sorted(f for f in pinned if not _in_image(f))
    assert missing == [], missing
    for raw in ("reports/x1/g0m0/preflight/a1_requests.json", "reports/x2/g1m0/calA/STAGE_LOG.json",
                "results/x2_g1m0_X2a/requests.parquet", ".x2_inputs/g1m0.tar.gz", "reports/backup/BACKUP_MANIFEST.json"):
        assert not _in_image(raw), raw


def test_runner_task_entrypoint_and_image_user_dirs():
    tf = (REPO / "infra" / "terraform" / "compute.tf").read_text()
    assert 'entryPoint      = ["/usr/bin/env"]' in tf
    df = (REPO / "docker" / "Dockerfile").read_text()
    assert "chown -R quotashift /app/results /app/reports /app/experiments" in df and "install -y --no-install-recommends git" in df


# ------------------------------------------------------------------------------------------------ aws_ops.sh
def _bins(tmp: Path) -> dict:
    b = tmp / "bin"
    b.mkdir()
    log = tmp / "calls.log"
    files = {
        "aws": f'''printf '%s\\n' "aws $*" >> {log}
case "$1 $2" in
  "sts get-caller-identity") echo "{ROLE}";;
  "ecs describe-services") echo "1";;
  "ecs run-task") echo "arn:task/x2";;
esac''',
        "terraform": f'''echo "terraform $*" >> {log}
if [[ "$*" == *"output -raw runner_task_definition_family"* ]]; then echo "quotashift-research-runner"; exit 0; fi
if [[ "$*" == *"output -raw results_bucket"* ]]; then echo "qs-results"; exit 0; fi
if [[ "$*" == *"output -raw"* ]]; then echo fake-output; exit 0; fi''',
    }
    for name, body in files.items():
        p = b / name
        p.write_text("#!/usr/bin/env bash\n" + body + "\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return {**os.environ, "PATH": f"{b}:{os.environ['PATH']}", "CALLS": str(log)}


def _run(env: dict, *args: str, **extra: str) -> tuple[subprocess.CompletedProcess, list[str]]:
    e = {k: v for k, v in env.items() if not k.startswith(("QUOTASHIFT_STAGE", "QUOTASHIFT_X2", "QUOTASHIFT_APPROVED"))}
    e.update(extra)
    r = subprocess.run(["bash", str(REPO / "scripts" / "aws_ops.sh"), *args], cwd=REPO, env=e, capture_output=True,
                       text=True, input="yes\n")
    p = Path(env["CALLS"])
    return r, (p.read_text().splitlines() if p.exists() else [])


def _overrides(log: list[str]) -> dict:
    line = next(x for x in log if x.startswith("aws ecs run-task"))
    return json.loads(line[line.index("--overrides ") + len("--overrides "):].split(" --query")[0])


def test_run_stage_x2_cal_routes_to_the_frozen_stage_driver(tmp_path):
    r, log = _run(_bins(tmp_path), "run-stage", "research", QUOTASHIFT_APPROVED="run-stage",
                  QUOTASHIFT_STAGE_APPROVAL="x2_cal_g1m0", QUOTASHIFT_X2_INPUTS_SHA256=SHA)
    assert r.returncode == 0, r.stderr
    o = _overrides(log)
    run = next(c for c in o["containerOverrides"] if c["name"] == "runner")
    assert run["command"][:4] == ["python", "scripts/x2_runner_entry.py", "run", "--"]
    assert "scripts/x2_stage.py" in run["command"] and "--live" in run["command"] and "calA" in run["command"]
    env = {e["name"]: e["value"] for e in run["environment"]}
    assert env == {"QUOTASHIFT_APPROVED": "x2_cal_g1m0", "QUOTASHIFT_X2_PLATFORM": "g1m0",
                   "QUOTASHIFT_TARGET": "x2-g1-qwen", "QUOTASHIFT_X2_INPUTS_SHA256": SHA}
    dl = next(c for c in o["containerOverrides"] if c["name"] == "inputs-download")
    assert dl["command"][:3] == ["s3", "cp", f"s3://qs-results/inputs/{SHA}.tar.gz"]
    assert "assignPublicIp=DISABLED" in next(x for x in log if x.startswith("aws ecs run-task"))
    assert "--enable-execute-command" not in next(x for x in log if x.startswith("aws ecs run-task"))


def test_run_stage_x2_qual_runs_in_the_task_without_ecs_exec(tmp_path):
    r, log = _run(_bins(tmp_path), "run-stage", "research", QUOTASHIFT_APPROVED="run-stage",
                  QUOTASHIFT_STAGE_APPROVAL="x2_qual_g1m1", QUOTASHIFT_X2_INPUTS_SHA256=SHA)
    assert r.returncode == 0, r.stderr
    assert "--enable-execute-command" not in next(x for x in log if x.startswith("aws ecs run-task"))
    run = next(c for c in _overrides(log)["containerOverrides"] if c["name"] == "runner")
    assert run["command"] == ["python", "scripts/x2_runner_entry.py", "qualify"]
    env = {e["name"]: e["value"] for e in run["environment"]}
    assert env["QUOTASHIFT_TARGET"] == "x2-g1-mistral" and env["QUOTASHIFT_APPROVED"] == "x2_qual_g1m1"


def test_qualify_cmd_wraps_the_frozen_driver_unchanged():
    assert ent.qualify_cmd("g1m0") == ["script", "-qfec", "python scripts/x2_qualify.py --platform g1m0 --live", "/dev/null"]


def test_run_qualify_answers_yes_logs_and_refuses_reruns(tmp_path, monkeypatch):
    fake = [sys.executable, "-c", "import sys; a=input('Type yes: '); print('GOT', a); print('phase 1: pass'); sys.exit(0 if a == 'yes' else 3)"]
    monkeypatch.setenv("QUOTASHIFT_APPROVED", "x2_qual_g1m0")
    log = tmp_path / "results" / "x2_qual_g1m0.log"
    assert ent.run_qualify("g1m0", cmd=fake, log=log, cwd=tmp_path) == 0
    assert "GOT yes" in log.read_text() and "phase 1: pass" in log.read_text()
    monkeypatch.setenv("QUOTASHIFT_APPROVED", "x2_cal_g1m0")
    with pytest.raises(SystemExit):
        ent.run_qualify("g1m0", cmd=fake, log=log, cwd=tmp_path)
    monkeypatch.setenv("QUOTASHIFT_APPROVED", "x2_qual_g1m0")
    rec = tmp_path / "experiments" / "x2" / "g1m0" / "QUALIFICATION.json"
    rec.parent.mkdir(parents=True)
    rec.write_text("{}")
    with pytest.raises(SystemExit):                      # one run per platform; no retry
        ent.run_qualify("g1m0", cmd=fake, log=log, cwd=tmp_path)


@pytest.mark.parametrize(("token", "sha", "why"), [
    ("x2_cal_g0m0", SHA, "G0 never runs on AWS"), ("x2_cal_g1m0", "", "inputs sha required"),
    ("x2_calA_g1m0", SHA, "not an X2 token"), ("x2_qual_g1m0", "XYZ", "malformed sha")])
def test_run_stage_x2_refusals(tmp_path, token, sha, why):
    r, log = _run(_bins(tmp_path), "run-stage", "research", QUOTASHIFT_APPROVED="run-stage",
                  QUOTASHIFT_STAGE_APPROVAL=token, QUOTASHIFT_X2_INPUTS_SHA256=sha)
    assert r.returncode in (2, 3), (why, r.stdout, r.stderr)
    assert not any(x.startswith("aws ecs run-task") for x in log), why


def test_run_stage_x2_rejects_arbitrary_extra_arguments(tmp_path):
    r, log = _run(_bins(tmp_path), "run-stage", "research", "--path", "direct", QUOTASHIFT_APPROVED="run-stage",
                  QUOTASHIFT_STAGE_APPROVAL="x2_main_g1m0", QUOTASHIFT_X2_INPUTS_SHA256=SHA)
    assert r.returncode == 3 and not any(x.startswith("aws ecs run-task") for x in log)


def test_run_stage_x1_path_unchanged(tmp_path):
    r, log = _run(_bins(tmp_path), "run-stage", "research", "--platform", "g1m0", "--phase", "calA", "--live",
                  QUOTASHIFT_APPROVED="run-stage", QUOTASHIFT_STAGE_APPROVAL="x1_calA_g1m0")
    assert r.returncode == 0 and "scripts/x1_stage.py" in next(x for x in log if x.startswith("aws ecs run-task"))


def test_x2_inputs_refusals(tmp_path):
    r, log = _run(_bins(tmp_path), "x2-inputs", "research", "g0m0", QUOTASHIFT_APPROVED="x2-inputs")
    assert r.returncode == 3 and "G1 platforms only" in r.stderr
    # (The "experiments/x2/<p> missing" refusal was exercised on g1m1 until its record directory was committed in
    # 147879c; both G1 platforms now have one, and running x2-inputs for real would rewrite the local inputs tarball.)
    assert (REPO / "experiments" / "x2" / "g1m1").is_dir() and (REPO / "experiments" / "x2" / "g1m0").is_dir()
    r, _ = _run(_bins(tmp_path / "c" if (tmp_path / "c").mkdir() is None else tmp_path), "x2-inputs", "research", "g1m0")
    assert r.returncode == 3 and "approval-gated" in r.stderr


# ------------------------------------------------------------------------------------------------ entry wrapper
def _tree(root: Path, plat: str = "g1m0") -> None:
    for rel, body in ((f"experiments/x2/{plat}/QUALIFICATION.json", '{"status": "pass"}'),
                      (f"experiments/x2/{plat}/calA/x2_{plat}_calA_aa_ind_L110_C8.yaml", "a: 1\n"),
                      (f"reports/x2/{plat}/calA/STAGE_LOG.json", '{"status": "completed"}')):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)


def test_pack_is_deterministic_and_extract_verifies(tmp_path):
    _tree(tmp_path / "repo")
    a = ent.pack("g1m0", tmp_path / "a.tgz", tmp_path / "repo")
    b = ent.pack("g1m0", tmp_path / "b.tgz", tmp_path / "repo")
    assert a == b
    files = ent.extract("g1m0", inputs=tmp_path / "a.tgz", want_sha=a, root=tmp_path / "app")
    assert sorted(files) == sorted(["experiments/x2/g1m0/QUALIFICATION.json",
                                    "experiments/x2/g1m0/calA/x2_g1m0_calA_aa_ind_L110_C8.yaml",
                                    "reports/x2/g1m0/calA/STAGE_LOG.json"])
    with pytest.raises(SystemExit):
        ent.extract("g1m0", inputs=tmp_path / "a.tgz", want_sha="0" * 64, root=tmp_path / "app2")
    with pytest.raises(SystemExit):                              # inputs of another platform
        ent.extract("g1m1", inputs=tmp_path / "a.tgz", want_sha=a, root=tmp_path / "app3")


@pytest.mark.parametrize("name", ["../evil", "/etc/passwd", "experiments/x2/g1m0/../../x", "scripts/x2_stage.py",
                                  "experiments/x2/FROZEN_SHA256.json"])
def test_extract_rejects_unsafe_or_foreign_members(tmp_path, name):
    tgz = tmp_path / "bad.tgz"
    with tarfile.open(tgz, "w:gz") as tf:
        ti = tarfile.TarInfo(name)
        ti.size = 1
        tf.addfile(ti, io.BytesIO(b"x"))
    with pytest.raises(SystemExit):
        ent.extract("g1m0", inputs=tgz, want_sha=ent.sha256(tgz), root=tmp_path / "app")


def test_overrides_validation():
    env = {"QUOTASHIFT_X2_INPUTS_SHA256": SHA, "QUOTASHIFT_STAGE_APPROVAL": "x2_main_g1m0"}
    o = ent.overrides("main", "g1m0", "b", ["--rerun", "x2_g1m0_X2a", "--reason", "harness fix"], env)
    assert o["containerOverrides"][0]["command"][-4:] == ["--rerun", "x2_g1m0_X2a", "--reason", "harness fix"]
    for kind, plat, extra, e in (("main", "g1m1", [], env), ("main", "g1m0", ["--path", "direct"], env),
                                 ("qual", "g1m0", [], {**env, "QUOTASHIFT_STAGE_APPROVAL": "x2_qual_g1m0", "QUOTASHIFT_X2_INPUTS_SHA256": ""}),
                                 ("qual", "g1m0", ["--k", "4"], {**env, "QUOTASHIFT_STAGE_APPROVAL": "x2_qual_g1m0"}),
                                 ("cal", "g0m0", [], {**env, "QUOTASHIFT_STAGE_APPROVAL": "x2_cal_g0m0"})):
        with pytest.raises(SystemExit):
            ent.overrides(kind, plat, "b", extra, e)


def test_entry_refuses_outside_vpc_for_g0_and_for_non_x2_commands(tmp_path, monkeypatch):
    for k in ("QUOTASHIFT_IN_VPC_RUNNER", "QUOTASHIFT_X2_PLATFORM", "QUOTASHIFT_TARGET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("QUOTASHIFT_X2_PLATFORM", "g0m0")
    with pytest.raises(SystemExit):
        ent.main(["run", "--", "python", "scripts/x2_stage.py"])
    monkeypatch.setenv("QUOTASHIFT_X2_PLATFORM", "g1m0")
    with pytest.raises(SystemExit):
        ent.main(["run", "--", "python", "scripts/x2_stage.py"])          # not in the VPC runner
    _tree(tmp_path / "repo")
    sha = ent.pack("g1m0", tmp_path / "app" / "inputs" / "inputs.tar.gz", tmp_path / "repo")
    monkeypatch.setattr(ent, "APP", tmp_path / "app")
    monkeypatch.setattr(ent, "INPUTS", tmp_path / "app" / "inputs" / "inputs.tar.gz")
    for k, v in (("QUOTASHIFT_IN_VPC_RUNNER", "1"), ("QUOTASHIFT_TARGET", "x2-g1-qwen"), ("QUOTASHIFT_X2_INPUTS_SHA256", sha)):
        monkeypatch.setenv(k, v)
    with pytest.raises(SystemExit):
        ent.main(["run", "--", "bash", "-c", "echo hi"])                  # only the frozen X2 drivers


# ------------------------------------------------------------------------------------------------ IAM proposal / readiness
def test_x2_operator_iam_addition_is_scoped():
    pol = json.loads((REPO / "infra" / "iam" / "x2-operator-additions.json").read_text())
    (st,) = pol["Statement"]
    assert st["Effect"] == "Allow" and st["Action"] == "ecs:ExecuteCommand"
    assert all(r.startswith("arn:aws:ecs:us-east-1:*:") and "quotashift-" in r for r in st["Resource"])
    assert st["Condition"]["StringEquals"] == {"aws:RequestedRegion": "us-east-1", "ecs:container-name": "runner"}


def test_readiness_stats_and_no_address_leak():
    import x2_network_readiness as nr
    s = nr.rtt_stats([1.0, 2.0, 3.0, 4.0, 100.0], 6)
    assert s["n"] == 5 and abs(s["loss"] - 1 / 6) < 1e-9 and s["median_ms"] == 3.0 and s["p95_ms"] == 100.0
    assert nr.rtt_stats([], 10)["loss"] == 1.0
    assert nr.IPV4.search("10.0.0.1") and not nr.IPV4.search("x2-g0-qwen")
    for f in (REPO / "reports" / "x2" / "readiness").glob("*.json"):
        assert not nr.IPV4.search(f.read_text()), f


def test_overlays_are_layered_in_order_and_unknown_ones_refused(tmp_path):
    env = _bins(tmp_path)
    r, log = _run(env, "plan", "research", QUOTASHIFT_OVERLAYS="x2 m1-mistral")
    plan = next(x for x in log if x.startswith("terraform") and " plan " in x)
    assert plan.index("envs/research.tfvars") < plan.index("envs/research.x2.tfvars") < plan.index("envs/research.m1-mistral.tfvars")
    r, log = _run(_bins(tmp_path / "z" if (tmp_path / "z").mkdir() is None else tmp_path), "plan", "research",
                  QUOTASHIFT_OVERLAYS="x2 ../../etc")
    assert r.returncode == 3 and "unknown overlay" in r.stderr


# ------------------------------------------------------------------------------------------------ X2 Amendment A2 (DRAFT)
@pytest.mark.parametrize(("token", "driver"), [("x2a2_main_g1m0", "scripts/x2_a2_stage.py"),
                                               ("x2a2_freeze_main_g1m0", "scripts/freeze_x2_a2_traces.py")])
def test_run_stage_x2a2_routes_to_the_a2_drivers(tmp_path, token, driver):
    r, log = _run(_bins(tmp_path), "run-stage", "research", QUOTASHIFT_APPROVED="run-stage",
                  QUOTASHIFT_STAGE_APPROVAL=token, QUOTASHIFT_X2_INPUTS_SHA256=SHA)
    assert r.returncode == 0, r.stderr
    run = next(c for c in _overrides(log)["containerOverrides"] if c["name"] == "runner")
    assert driver in run["command"] and "--live" in run["command"]
    assert {e["name"]: e["value"] for e in run["environment"]}["QUOTASHIFT_APPROVED"] == token


@pytest.mark.parametrize("token", ["x2a2_cal_g1m0", "x2a2_qual_g1m0", "x2a2_freeze_calA_g1m0", "x2a2_main_g0m0"])
def test_run_stage_x2a2_covers_main_only(tmp_path, token):
    r, log = _run(_bins(tmp_path), "run-stage", "research", QUOTASHIFT_APPROVED="run-stage",
                  QUOTASHIFT_STAGE_APPROVAL=token, QUOTASHIFT_X2_INPUTS_SHA256=SHA)
    assert r.returncode in (2, 3) and not any(x.startswith("aws ecs run-task") for x in log)


# ------------------------------------------------------------------------------------------------ X2-A3 dispatch
def _cmd(kind, plat, extra=()):
    tok = f"x2a2_{kind[3:]}_{plat}" if kind in ent.A2_KINDS else f"x2_{kind}_{plat}"
    o = ent.overrides(kind, plat, "b", list(extra), {"QUOTASHIFT_X2_INPUTS_SHA256": SHA, "QUOTASHIFT_STAGE_APPROVAL": tok})
    return o["containerOverrides"][0]["command"]


def test_a3_dispatch_mistral_through_x2_a3_qwen_unchanged():
    head = ["python", "scripts/x2_runner_entry.py", "run", "--", "python"]
    assert _cmd("freeze_calA", "g1m1") == [*head, "scripts/x2_a3.py", "freeze", "--phase", "calA", "--platform", "g1m1",
                                           "--live"]
    assert _cmd("cal", "g1m1", ["--rerun", "B", "--reason", "r"]) == [
        *head, "scripts/x2_a3.py", "stage", "--phase", "calA", "--platform", "g1m1", "--live", "--out-root",
        "/app/results/reports/x2", "--rerun", "B", "--reason", "r"]
    assert _cmd("a2_freeze_main", "g1m1") == [*head, "scripts/x2_a3.py", "freeze", "--phase", "main", "--platform",
                                              "g1m1", "--live"]
    assert _cmd("a2_main", "g1m1") == [*head, "scripts/x2_a3.py", "stage", "--phase", "main", "--platform", "g1m1",
                                       "--live", "--out-root", "/app/results/reports/x2"]
    assert _cmd("qual", "g1m1") == ["python", "scripts/x2_runner_entry.py", "qualify"]
    # Qwen: byte-for-byte the pre-A3 commands
    assert _cmd("cal", "g1m0") == [*head, "scripts/x2_stage.py", "--platform", "g1m0", "--phase", "calA", "--live",
                                   "--out-root", "/app/results/reports/x2"]
    assert _cmd("freeze_calA", "g1m0") == [*head, "scripts/freeze_x2_traces.py", "--platform", "g1m0", "--phase",
                                           "calA", "--live"]
    assert _cmd("a2_main", "g1m0") == [*head, "scripts/x2_a2_stage.py", "--platform", "g1m0", "--live", "--out-root",
                                       "/app/results/reports/x2"]


def test_a3_dispatch_refuses_plain_x2_main_for_mistral(capsys):
    for kind in ("main", "freeze_main"):
        with pytest.raises(SystemExit):
            _cmd(kind, "g1m1")
        assert "never the plain X2 main driver" in capsys.readouterr().err


def test_a3_wrapped_command_parses_back_to_the_same_frozen_driver_and_args():
    import x2_a3

    for kind, drv in (("freeze_calA", "freeze_x2_traces.py"), ("cal", "x2_stage.py"),
                      ("a2_freeze_main", "freeze_x2_a2_traces.py"), ("a2_main", "x2_a2_stage.py")):
        c = _cmd(kind, "g1m1")
        k, phase, plat, rest = x2_a3.parse(c[c.index("scripts/x2_a3.py") + 1:])
        assert x2_a3.DRIVERS[(k, phase)] == drv and plat == "g1m1" and "--live" in rest


def test_entry_run_refuses_unwrapped_mistral_driver(monkeypatch, capsys):
    monkeypatch.setenv("QUOTASHIFT_X2_PLATFORM", "g1m1")
    monkeypatch.setenv("QUOTASHIFT_IN_VPC_RUNNER", "1")
    monkeypatch.setenv("QUOTASHIFT_TARGET", "x2-g1-mistral")
    monkeypatch.setattr(ent, "extract", lambda plat: [])
    monkeypatch.setattr(ent, "seed_reports", lambda plat: None)
    monkeypatch.setattr(ent, "export", lambda plat: None)
    with pytest.raises(SystemExit):
        ent.main(["run", "--", "python", "scripts/freeze_x2_traces.py", "--platform", "g1m1", "--phase", "calA"])
    assert "only through scripts/x2_a3.py" in capsys.readouterr().err
