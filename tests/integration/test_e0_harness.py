import json

import pandas as pd
import pytest

from risksched.config import BackendConfig
from risksched.profiling.e0 import ProfileConfig, ProfileSpec, RateSweep, load_profile_config, run_profile
from risksched.runtime.runner import SafetyError
from risksched.serving.engine_model import EngineParams


def _cfg(kind="mock", **spec):
    base = dict(prompt_lengths=[64, 2048], output_lengths=[16, 64], concurrencies=[1, 4], trials=2,
                min_requests_per_cell=4, requests_per_slot=1, max_model_len=2100, warmup_requests=1,
                rate_sweep=RateSweep(prompt_tokens=64, output_tokens=16, rates_rps=[2, 50, 400], duration_s=5, trials=2,
                                     ttft_deadline_ms=500))
    return ProfileConfig(experiment_id="e0t", backend=BackendConfig(kind=kind, engine=EngineParams(max_model_len=2100)),
                         profile=ProfileSpec(**(base | spec)))


def test_mock_profile_grid_complete_and_skips_marked(tmp_path):
    out = run_profile(_cfg(), seed=1, results_root=tmp_path)
    cells = pd.read_parquet(out / "cells.parquet")
    assert len(cells) == 2 * 2 * 2 * 2  # every grid cell has a row, including skipped ones
    sk = cells[cells.status == "skipped_unsupported"]
    assert set(zip(sk.prompt_tokens, sk.max_tokens, strict=False)) == {(2048, 64)}
    ok = cells[cells.status == "ok"]
    assert (ok.realized_eq_requested_frac == 1.0).all()  # ignore_eos profiling
    assert (ok.event_validation_errors == 0).all()
    s = json.loads((out / "summary.json").read_text())
    assert s["synthetic_backend"] is True
    assert s["controlled_saturation_observed"] is True
    figs = {p.name for p in (out / "figures").glob("*.png")}
    assert "e0_output_tok_per_s_vs_concurrency.png" in figs and "e0_rate_sweep.png" in figs
    cap = json.loads((out / "figures" / "e0_rate_sweep.caption.json").read_text())
    assert cap["synthetic"] is True


def test_mock_profile_deterministic(tmp_path):
    a = pd.read_parquet(run_profile(_cfg(), 5, tmp_path / "a", skip_rate_sweep=True) / "cells.parquet")
    b = pd.read_parquet(run_profile(_cfg(), 5, tmp_path / "b", skip_rate_sweep=True) / "cells.parquet")
    cols = ["prompt_tokens", "max_tokens", "concurrency", "trial", "status", "output_tok_per_s", "ttft_p95_ms"]
    pd.testing.assert_frame_equal(a[cols], b[cols])


@pytest.mark.slow
def test_mock_http_profile_one_cell(tmp_path):
    cfg = _cfg(kind="mock_http", prompt_lengths=[64], output_lengths=[16], concurrencies=[2], trials=1,
               rate_sweep=None)
    out = run_profile(cfg, 1, tmp_path)
    cells = pd.read_parquet(out / "cells.parquet")
    assert list(cells.status) == ["ok"]
    assert cells.output_tokens_source.iloc[0] == "usage"
    assert json.loads(cells.resolved_metric_names.iloc[0])["kv_cache_usage_perc"] == "vllm:kv_cache_usage_perc"


def test_budget_abort_rows(tmp_path):
    out = run_profile(_cfg(max_total_seconds=0.0), 1, tmp_path)
    cells = pd.read_parquet(out / "cells.parquet")
    assert set(cells.status) <= {"aborted_budget", "skipped_unsupported"}


def test_mock_http_rejects_time_scale(tmp_path):
    cfg = _cfg(kind="mock_http")
    cfg = cfg.model_copy(update={"backend": cfg.backend.model_copy(update={"time_scale": 0.1})})
    with pytest.raises(SafetyError):
        run_profile(cfg, 1, tmp_path)


def test_repo_e0_configs_parse(repo):
    full = load_profile_config(repo / "configs/experiments/e0.yaml")
    assert full.backend.kind == "vllm" and full.backend.model_revision
    assert full.profile.concurrencies == [1, 4, 8, 16, 32, 64]
    assert full.profile.prompt_lengths == [256, 1024, 4096, 8192]
    assert full.profile.output_lengths == [128, 512, 1024, 2048]
    load_profile_config(repo / "configs/experiments/e0_smoke.yaml")
