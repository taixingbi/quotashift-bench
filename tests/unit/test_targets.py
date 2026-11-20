import pytest

from quotashift import targets as T
from quotashift.local import backend_for
from quotashift.scenario import load_scenario


def _write(d, name, url="http://10.0.0.5:8000", kind="selfhost", mml=4096):
    (d / f"{name}.yaml").write_text(
        f"name: {name}\nkind: {kind}\nbackend_url: {url}\nmodel: m\nmax_model_len: {mml}\n")


def test_repo_profiles_load():
    assert set(T.list_targets()) >= {"aws", "selfhost"}
    for n in ("aws", "selfhost"):
        p = T.load_target(n)
        assert p.model == "Qwen/Qwen2.5-7B-Instruct" and p.max_model_len == 4096


def test_toggle_roundtrip(tmp_path, monkeypatch):
    monkeypatch.delenv(T.ENV_VAR, raising=False)
    _write(tmp_path, "aws", url="http://vllm.quotashift.internal:8000", kind="aws")
    _write(tmp_path, "selfhost")
    T.set_active("aws", tmp_path)
    assert T.active_target(tmp_path).kind == "aws"
    T.set_active("selfhost", tmp_path)
    assert T.active_target(tmp_path).name == "selfhost"
    monkeypatch.setenv(T.ENV_VAR, "aws")
    assert T.active_target(tmp_path).name == "aws"


def test_rejects_public_endpoint_and_unknown(tmp_path, monkeypatch):
    monkeypatch.delenv(T.ENV_VAR, raising=False)
    _write(tmp_path, "pub", url="http://8.8.8.8:8000")
    with pytest.raises(ValueError, match="rejected"):
        T.load_target("pub", tmp_path)
    with pytest.raises(ValueError, match="unknown target"):
        T.set_active("nope", tmp_path)
    with pytest.raises(ValueError, match="invalid"):
        T.load_target("../etc", tmp_path)


def test_backend_for(repo, tmp_path):
    sc = load_scenario(repo / "experiments/smoke.yaml")
    assert backend_for(sc, None).kind == "mock"
    b = backend_for(sc, T.load_target("selfhost"))
    assert b.kind == "vllm" and b.base_url == "http://192.168.86.173:8000"
    _write(tmp_path, "tiny", mml=512)
    with pytest.raises(ValueError, match="max_model_len"):
        backend_for(sc, T.load_target("tiny", tmp_path))
