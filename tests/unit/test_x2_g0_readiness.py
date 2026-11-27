"""X2 G0 offline readiness (no GPU, no host access, no AWS): launch-template parity, A3 routing for g0m1, the counter
identity guard, A2 coverage at G0 rates, and that nothing here can write canonical live artifacts."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import build_x2  # noqa: E402
import build_x2_a2  # noqa: E402
import x2_a2_validate as av  # noqa: E402
import x2_a3  # noqa: E402
import x2_counter_check as cc  # noqa: E402

from quotashift.workload import tokenize as T  # noqa: E402
from quotashift.workload import tokenize_a3 as A3  # noqa: E402

SERVER = (REPO / "scripts" / "x1_g0_server.sh").read_text()
# the live G1 vLLM task definition (rev 2, recorded 2026-11-27) minus model id / revision / host / port
G1_ARGS = ["--max-model-len", "4096", "--gpu-memory-utilization", "0.80", "--dtype", "float16", "--enable-prefix-caching",
           "--enable-prompt-tokens-details", "--max-num-seqs", "256", "--max-num-batched-tokens", "2048"]
MISTRAL_ARGS = ["--tokenizer-mode", "mistral", "--config-format", "mistral", "--load-format", "mistral"]


@pytest.fixture(autouse=True)
def _restore():
    yield
    A3.uninstall()


def _flags(text: str) -> list[str]:
    return re.findall(r"--[a-z-]+(?:\s+[0-9.]+|\s+float16)?", text)


@pytest.mark.parametrize("plat", ["g0m0", "g0m1"])
def test_g0_launch_template_matches_platform_pins_and_g1_flags(plat):
    spec = build_x2.PLATFORMS[plat]
    line = next(ln for ln in SERVER.splitlines() if ln.strip().startswith(f"{plat})"))
    assert spec["model"] in line and spec["revision"] in line
    tgt = yaml.safe_load((REPO / "configs" / "targets" / f"x2-g0-{'qwen' if plat == 'g0m0' else 'mistral'}.yaml").read_text())
    assert (tgt["model"], tgt["model_revision"], tgt["max_model_len"]) == (spec["model"], spec["revision"], 4096)
    serve = SERVER[SERVER.index("vllm\" serve"):SERVER.index("> \"$LOG\"")]
    got = " ".join(serve.split())
    for i in range(0, len(G1_ARGS), 1):
        assert G1_ARGS[i] in got, G1_ARGS[i]
    assert " ".join(G1_ARGS[0:2]) in got and "--max-num-batched-tokens 2048" in got and "--gpu-memory-utilization 0.80" in got
    block = SERVER[SERVER.index(f"  {plat})"):].split(";;", 1)[0]          # the platform's case arm
    assert ("--tokenizer-mode mistral --config-format mistral --load-format mistral" in block) == (plat == "g0m1")
    assert "vllm0171" in SERVER                                   # pinned vLLM 0.17.1 env


def test_g1_overlay_mistral_args_equal_the_g0_template():
    tf = (REPO / "infra" / "terraform" / "envs" / "research.m1-mistral.tfvars").read_text()
    assert all(a in tf for a in MISTRAL_ARGS)
    line = next(ln for ln in SERVER.splitlines() if "EXTRA=(--tokenizer-mode" in ln)
    assert line.split("EXTRA=(", 1)[1].split(")", 1)[0].split() == MISTRAL_ARGS


def test_g0m1_routes_through_a3_and_g0m0_keeps_the_frozen_counter():
    assert x2_a3.problems("g0m1", live=False) == []
    assert any("Mistral platforms only" in x for x in x2_a3.problems("g0m0", live=False))
    A3.install()
    assert type(T.VllmTokenizer("http://127.0.0.1:9", build_x2.PLATFORMS["g0m1"]["model"])).__name__ == \
        "SequentialMistralTokenizer"
    q = T.VllmTokenizer("http://127.0.0.1:9", build_x2.PLATFORMS["g0m0"]["model"])
    assert type(q) is A3.FROZEN_VLLM_TOKENIZER and q._workers == 16


def test_x2_a3_g0_stage_and_freeze_commands_pass_args_to_the_frozen_drivers():
    k, ph, plat, rest = x2_a3.parse(["stage", "--platform", "g0m1", "--phase", "calA", "--live"])
    assert x2_a3.DRIVERS[(k, ph)] == "x2_stage.py" and rest == ["--platform", "g0m1", "--live", "--phase", "calA"]
    k, ph, plat, rest = x2_a3.parse(["freeze", "--platform", "g0m1", "--phase", "main", "--live"])
    assert x2_a3.DRIVERS[(k, ph)] == "freeze_x2_a2_traces.py" and rest == ["--platform", "g0m1", "--live"]


def test_x2_a3_refuses_g0_offline_freeze_into_canonical_dirs(capsys):
    # frozen driver refusals pass through: no g0m1 qualification / calA files exist, so nothing is written
    rc = x2_a3.main(["freeze", "--platform", "g0m1", "--phase", "calA", "--offline"])
    assert rc == 3 and not (REPO / "experiments" / "x2" / "g0m1").exists()


@pytest.mark.parametrize("ident,model,ok", [
    ({"kind": "vllm /tokenize", "model": "mistralai/Mistral-7B-Instruct-v0.3", "amendment": "X2-A3",
      "counting": "sequential", "workers": 1}, "mistralai/Mistral-7B-Instruct-v0.3", True),
    ({"kind": "vllm /tokenize", "model": "mistralai/Mistral-7B-Instruct-v0.3"}, "mistralai/Mistral-7B-Instruct-v0.3", False),
    ({"kind": "vllm /tokenize", "model": "Qwen/Qwen2.5-7B-Instruct"}, "Qwen/Qwen2.5-7B-Instruct", True),
    ({"kind": "vllm /tokenize", "model": "Qwen/Qwen2.5-7B-Instruct", "amendment": "X2-A3"}, "Qwen/Qwen2.5-7B-Instruct", False),
    ({"kind": "whitespace", "model": "Qwen/Qwen2.5-7B-Instruct"}, "Qwen/Qwen2.5-7B-Instruct", False),
])
def test_counter_identity_rule(ident, model, ok):
    assert (cc.problems(ident, model) == []) == ok


def test_counter_check_cli_on_completed_g1_records_and_a_bad_file(tmp_path):
    for plat in ("g1m0", "g1m1"):
        for phase in ("calA", "main"):
            assert cc.main(["--platform", plat, "--phase", phase]) == 0
    bad = tmp_path / "t.json"
    bad.write_text(json.dumps({"tokenizer": {"kind": "vllm /tokenize", "model": "mistralai/Mistral-7B-Instruct-v0.3"}}))
    assert cc.main(["--platform", "g0m1", "--phase", "calA", "--file", str(bad)]) == 1
    assert cc.main(["--platform", "g0m1", "--phase", "calA"]) == 3                # not frozen yet


def test_a2_coverage_guaranteed_except_5_toks():
    for r in range(5, 1001, 5):
        nd = build_x2.count("D", r)
        ntm = max(1, round(nd * sum(build_x2.SHAPES["D"]) / sum(build_x2.SHAPES["S"])))
        n = min(nd, ntm, build_x2.count("S", r))
        assert (av.p_gate_strat(n) == 1.0) == (r != 5), (r, n)
    assert build_x2.count("D", 5) == 2 and build_x2.count("D", 10) == 4


def test_g0_a2_main_files_differ_only_by_the_a2_keys_and_are_deterministic():
    for plat in ("g0m0", "g0m1"):
        a = build_x2_a2.build_main_a2(plat, {"low": 50, "low_feasible": True})
        b = build_x2_a2.build_main_a2(plat, {"low": 50, "low_feasible": True})
        o = build_x2.with_reruns(build_x2.build_main(plat, {"low": 50, "low_feasible": True}))
        assert a == b and set(a) == set(o)
        for rel, text in a.items():
            assert build_x2_a2.amend(o[rel]) == text and f"x2_{plat}_" in text


def test_mock_qualification_refuses_repo_output_and_marks_synthetic(tmp_path):
    for plat in ("g0m0", "g0m1"):
        r = subprocess.run([sys.executable, str(REPO / "scripts" / "x2_qualify.py"), "--platform", plat, "--mock",
                            "--out-root", str(REPO / "reports" / "nope")], capture_output=True, text=True, cwd=REPO)
        assert r.returncode == 3 and not (REPO / "reports" / "nope").exists()
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "x2_qualify.py"), "--platform", "g0m1", "--mock",
                        "--out-root", str(tmp_path)], capture_output=True, text=True, cwd=REPO)
    rec = json.loads((tmp_path / "QUALIFICATION_g0m1.json").read_text())
    assert r.returncode == 0 and rec["synthetic"] is True and not (REPO / "experiments" / "x2" / "g0m1").exists()


def test_live_g0_qualification_refuses_without_token_or_tty():
    env = {k: v for k, v in os.environ.items() if k != "QUOTASHIFT_APPROVED"}
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "x2_qualify.py"), "--platform", "g0m0", "--live"],
                       capture_output=True, text=True, cwd=REPO, env=env, stdin=subprocess.DEVNULL)
    assert r.returncode == 3 and "x2_qual_g0m0" in r.stderr and "did not confirm" in r.stderr
