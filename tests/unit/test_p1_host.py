"""P1 host verification tooling (scripts/p1_host_evidence.py on the host, scripts/p1_verify_host.py on the runner).
Synthetic evidence and a synthetic HF cache only; nothing contacts the GPU host."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import p1_host_evidence as he  # noqa: E402
import p1_verify_host as pv  # noqa: E402

START = 1795268683.89
A, B = "a" * 40, "b" * 40
W1, W2 = "1" * 64, "2" * 64


def _cache(tmp: Path, snaps: dict[str, list[str]], mtime: float = START - 1000) -> dict:
    repo = tmp / "hub" / "models--Qwen--Qwen2.5-7B-Instruct"
    (repo / "blobs").mkdir(parents=True)
    (repo / "refs").mkdir()
    (repo / "refs" / "main").write_text(B)
    for commit, blobs in snaps.items():
        d = repo / "snapshots" / commit
        d.mkdir(parents=True)
        for i, b in enumerate(blobs):
            (repo / "blobs" / b).write_bytes(b"w")
            os.utime(repo / "blobs" / b, (mtime, mtime))
            (d / f"model-0000{i + 1}.safetensors").symlink_to(repo / "blobs" / b)
        (d / "config.json").write_text("{}")
        os.utime(d, (mtime, mtime), follow_symlinks=False)
    return he.hf_cache("Qwen/Qwen2.5-7B-Instruct", {"HF_HUB_CACHE": str(tmp / "hub")}, str(tmp))


def _ev(cache: dict, opened: list[str] | None = None, log: list[str] | None = None, argv: list[str] | None = None) -> dict:
    argv = argv or ["/venv/bin/python", "-m", "vllm.entrypoints.openai.api_server", "--model", "Qwen/Qwen2.5-7B-Instruct",
                    "--max-num-seqs", "256", "--max-num-batched-tokens", "2048"]
    return {"expect_start": START, "matched_pid": 10, "match_count": 1, "collected_epoch": START + 9e4, "collector_version": 1,
            "vllm_processes": [{"pid": 10, "ppid": 1, "start_epoch": START, "argv": argv}],
            "weight_files": {"10": {"maps": opened or [], "fds": []}}, "python_vllm_version": "0.17.1",
            "hf_cache": cache, "startup_log": {"source": "journal:vllm.service", "lines": log or []},
            "environ_allowlisted": {"HF_HUB_CACHE": "/home/tb/.cache/huggingface/hub"}}


def test_snapshot_direct_from_process_files(tmp_path):
    c = _cache(tmp_path, {A: [W1], B: [W2]})
    s = pv.resolve_snapshot(_ev(c, opened=[str(tmp_path / f"hub/models--Qwen--Qwen2.5-7B-Instruct/blobs/{W1}")]))
    assert (s["status"], s["commit"], s["method"]) == ("verified_direct", A, "process_files")  # refs/main says B


def test_refs_main_alone_is_never_evidence(tmp_path):
    c = _cache(tmp_path, {A: [W1], B: [W2]})          # two snapshots, refs/main -> B, nothing open, nothing logged
    s = pv.resolve_snapshot(_ev(c))
    assert s["status"] == "unresolved" and s["commit"] is None and "refs/main alone" in s["method"]
    rec, issues = pv.build_record(_ev(c), "0.17.1", START, verified_by="owner", waiver=None, accept_exclusion=True)
    assert rec["model_snapshot_sha"] is None and any("snapshot" in i for i in issues)


def test_snapshot_from_startup_log(tmp_path):
    c = _cache(tmp_path, {A: [W1], B: [W2]})
    s = pv.resolve_snapshot(_ev(c, log=[f"INFO loading /x/models--Qwen--Qwen2.5-7B-Instruct/snapshots/{B}/model.safetensors"]))
    assert (s["status"], s["commit"], s["method"]) == ("verified_direct", B, "startup_log")


def test_exclusion_needs_explicit_owner_acceptance(tmp_path):
    c = _cache(tmp_path, {A: [W1]})
    assert pv.resolve_snapshot(_ev(c))["status"] == "verified_by_exclusion"
    _, issues = pv.build_record(_ev(c), "0.17.1", START, verified_by="owner", waiver=None, accept_exclusion=False)
    assert any("--accept-exclusion" in i for i in issues)
    rec, issues = pv.build_record(_ev(c), "0.17.1", START, verified_by="owner", waiver=None, accept_exclusion=True)
    assert issues == [] and rec["model_snapshot_sha"] == A


def test_exclusion_rejected_when_snapshot_is_newer_than_the_process(tmp_path):
    c = _cache(tmp_path, {A: [W1]}, mtime=START + 60)   # downloaded after the server started
    assert pv.resolve_snapshot(_ev(c))["status"] == "unresolved"


def test_flags_argv_then_log_never_defaults(tmp_path):
    c = _cache(tmp_path, {A: [W1]})
    bare = ["python", "-m", "vllm.entrypoints.openai.api_server", "--model", "Qwen/Qwen2.5-7B-Instruct"]
    rec, issues = pv.build_record(_ev(c, argv=bare), "0.17.1", START, verified_by="o", waiver=None, accept_exclusion=True)
    assert rec["max_num_seqs"] is None and any("max_num_seqs source-default rule does not apply" in i for i in issues)
    log = ["non-default args: {'model': 'Qwen/Qwen2.5-7B-Instruct', 'max_num_seqs': 256}",
           "Chunked prefill is enabled with max_num_batched_tokens=2048."]
    rec, issues = pv.build_record(_ev(c, argv=bare, log=log), "0.17.1", START, verified_by="o", waiver=None,
                                  accept_exclusion=True)
    assert (rec["max_num_seqs"], rec["max_num_seqs_source"], rec["max_num_batched_tokens"]) == (256, "startup_log", 2048)
    assert issues == []
    assert pv.flag_from_argv(["--max-num-seqs=64"], "--max-num-seqs") == 64
    assert pv.flag_from_log(["max_num_seqs=256", "max_num_seqs=128"], "max_num_seqs") == (None, [128, 256])  # ambiguous


def test_live_identity_and_version_must_agree(tmp_path):
    c = _cache(tmp_path, {A: [W1]})
    _, issues = pv.build_record(_ev(c), "0.17.1", START + 500, verified_by="o", waiver=None, accept_exclusion=True)
    assert any("live process_start_time_seconds" in i for i in issues)
    _, issues = pv.build_record(_ev(c), "0.18.0", START, verified_by="o", waiver=None, accept_exclusion=True)
    assert any("vllm version" in i for i in issues)
    ev = _ev(c)
    ev["matched_pid"], ev["match_count"] = None, 0
    _, issues = pv.build_record(ev, "0.17.1", START, verified_by="o", waiver=None, accept_exclusion=True)
    assert any("no unique vllm process" in i for i in issues)


def test_record_is_sanitized_before_writing(tmp_path):
    c = _cache(tmp_path, {A: [W1]})
    host = next(h for h, n in pv.ex.target_hosts().items() if n == "selfhost")
    argv = ["/home/tb/venv/bin/python", "-m", "vllm.entrypoints.openai.api_server", "--host", host,
            "--max-num-seqs", "256", "--max-num-batched-tokens", "2048"]
    rec, _ = pv.build_record(_ev(c, argv=argv), "0.17.1", START, verified_by="o", waiver=None, accept_exclusion=True)
    text = str(pv.sanitize(rec))
    assert "/home/" not in text and host not in text and "selfhost" in text


def test_collector_env_allowlist_never_keeps_tokens():
    keep = ["HF_HOME", "HF_HUB_CACHE", "HF_HUB_OFFLINE", "VLLM_CACHE_ROOT", "VLLM_USE_V1", "CUDA_VISIBLE_DEVICES"]
    drop = ["HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "VLLM_API_KEY", "AWS_SECRET_ACCESS_KEY", "PATH", "HOME"]
    assert all(he.ENV_ALLOW.match(k) and not he.ENV_DENY.search(k) for k in keep)
    assert not any(he.ENV_ALLOW.match(k) and not he.ENV_DENY.search(k) for k in drop)


def test_collector_is_read_only_by_construction():
    src = (REPO / "scripts" / "p1_host_evidence.py").read_text()
    for forbidden in ("os.kill", "signal.", "open(", ".write(", "os.remove", "unlink", "rmtree", "systemctl", "nvidia-smi"):
        if forbidden == "open(":
            assert src.count("open(") == 2 and '"rb" if binary else "r"' in src and 'open(p, "rb")' in src
            continue
        assert forbidden not in src, forbidden


# ---------------------------------------------------------------- owner-approved source-default rule (P1 decision 2)
def _ev_default(tmp_path, **over):
    c = _cache(tmp_path, {A: [W1]})
    argv = ["/env/bin/python3.11", "/env/bin/vllm", "serve", "Qwen/Qwen2.5-7B-Instruct", "--max-model-len", "4096"]
    log = ["(APIServer pid=10) INFO non-default args: {'model': 'Qwen/Qwen2.5-7B-Instruct', 'max_model_len': 4096}",
           "(APIServer pid=10) INFO Chunked prefill is enabled with max_num_batched_tokens=2048.",
           "(EngineCore_DP0 pid=11) INFO config: ... 'max_cudagraph_capture_size': 512, ..."]
    ev = _ev(c, argv=argv, log=log)
    ev["vllm_source"] = {"sha256": dict(pv.SOURCE_DEFAULT_RULE["source_sha256"])}
    ev["gpu_models"] = ["NVIDIA GeForce RTX 3090"]
    for k, v in over.items():
        ev[k] = v
    return ev


def _rec(ev, **kw):
    kw = {"verified_by": "Owner", "waiver": None, "accept_exclusion": True} | kw
    return pv.build_record(ev, "0.17.1", START, **kw)


def test_source_default_rule_needs_explicit_owner_acceptance(tmp_path):
    rec, issues = _rec(_ev_default(tmp_path))
    assert rec["max_num_seqs"] is None and any("--accept-source-default-max-num-seqs" in i for i in issues)
    rec, issues = _rec(_ev_default(tmp_path / "b"), accept_source_default=True)
    assert issues == [], issues
    assert (rec["max_num_seqs"], rec["max_num_seqs_source"]) == (256, "inferred_from_source_default")
    inf = rec["max_num_seqs_inference"]
    assert inf["owner_approved_by"] == "Owner" and "not a direct observation" in inf["uncertainty"]
    assert inf["consistency_check"]["max_cudagraph_capture_size"] == 512
    assert "consistency check only" in inf["consistency_check"]["note"]
    assert (rec["max_num_batched_tokens"], rec["max_num_batched_tokens_source"]) == (2048, "startup_log")
    assert rec["model_snapshot_evidence_level"] == "verified_by_exclusion"   # evidence level is preserved
    assert pv.v5_stage.host_record_problems(rec) == []


def test_source_default_rule_is_narrow(tmp_path):
    bad = {
        "performance_mode": {"vllm_processes": [{"pid": 10, "ppid": 1, "start_epoch": START, "argv": [
            "/env/bin/vllm", "serve", "Qwen/Qwen2.5-7B-Instruct", "--performance-mode", "throughput"]}]},
        "sha": {"vllm_source": {"sha256": {"engine/arg_utils.py": "0" * 64}}},
        "gpu": {"gpu_models": ["NVIDIA H100 80GB HBM3"]},
        "version": {"python_vllm_version": "0.18.0"},
    }
    for i, (name, over) in enumerate(bad.items()):
        rec, issues = _rec(_ev_default(tmp_path / str(i), **over), accept_source_default=True)
        assert rec["max_num_seqs"] is None, name
        assert any("rule does not apply" in x for x in issues), (name, issues)
    ev = _ev_default(tmp_path / "x")
    ev["startup_log"]["lines"] = [ln.replace("=2048", "=4096") for ln in ev["startup_log"]["lines"]]   # doubled branch
    rec, _ = _rec(ev, accept_source_default=True)
    assert rec["max_num_seqs"] is None and not rec["max_num_seqs_inference"]["conditions"]["logged_max_num_batched_tokens_is_2048"]
    ev = _ev_default(tmp_path / "y")
    ev["startup_log"]["lines"][0] = ev["startup_log"]["lines"][0].replace("}", ", 'max_num_seqs': 64}")   # override logged
    assert _rec(ev, accept_source_default=True)[0]["max_num_seqs"] == 64   # then it is simply read from the log


def test_p1_gate_rejects_weaker_evidence_without_recorded_owner_decision(tmp_path):
    rec, _ = _rec(_ev_default(tmp_path), accept_source_default=True)
    g = pv.v5_stage.host_record_problems
    r2 = dict(rec, max_num_seqs_inference={k: v for k, v in rec["max_num_seqs_inference"].items() if k != "owner_approved_by"})
    assert any("owner-approved rule" in p for p in g(r2))
    r3 = dict(rec, model_snapshot_evidence=dict(rec["model_snapshot_evidence"], owner_accepted_by=None))
    assert any("without recorded owner acceptance" in p for p in g(r3))
    assert any("not accepted" in p for p in g(dict(rec, max_num_seqs_source="assumed_default")))
