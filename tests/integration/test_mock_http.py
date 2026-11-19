import asyncio
import json

import pandas as pd
import pytest

from risksched.config import BackendConfig, ExperimentConfig, GatewayConfig, RunControl
from risksched.gateway.core import Gateway
from risksched.instrumentation.recorder import RunRecorder, validate_events
from risksched.runtime.clients import OpenLoopClient
from risksched.runtime.live import LiveConfig, run_live
from risksched.runtime.runner import local_mock_server, run_experiment
from risksched.schedulers.simple import FCFSPassThrough
from risksched.schema import SLOType, WorkloadConfig
from risksched.serving.engine_model import EngineParams
from risksched.serving.openai_backend import OpenAICompatBackend
from risksched.workload.generator import generate_trace
from tests.conftest import tenant

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def mock_url():
    with local_mock_server(BackendConfig(kind="mock_http", engine=EngineParams(max_model_len=4096))) as url:
        yield url


def _req(rid="r1", n=50, max_tokens=8):
    from risksched.schema import Request
    return Request(request_id=rid, tenant_id="A", arrival_time_s=0, prompt_token_ids=tuple(range(1000, 1000 + n)),
                   input_token_count=n, max_output_tokens=max_tokens, workload_class="c",
                   slo_type=SLOType.INTERACTIVE, ttft_deadline_ms=1000, seed=1, trace_id="t")


def test_stream_usage_and_first_token(mock_url):
    async def go():
        be = OpenAICompatBackend(mock_url, "mock-model", send_mock_oracle_header=True)
        hits = []
        try:
            res = await be.stream(_req(), on_first_token=lambda: hits.append(1), oracle_output_tokens=5)
            snap = await be.scrape_metrics()
            info = await be.info()
            toks = await be.tokenize("a b c")
        finally:
            await be.aclose()
        return res, hits, snap, info, toks
    res, hits, snap, info, toks = asyncio.run(go())
    assert res.ok and res.output_tokens == 5 and res.output_tokens_source == "usage"
    assert res.prompt_tokens == 50 and res.n_chunks == 5 and hits == [1]
    assert snap.values["generation_tokens_total"] >= 5
    assert snap.resolved_names["kv_cache_usage_perc"] == "vllm:kv_cache_usage_perc"
    assert info["/version"]["mock"] is True
    assert toks is not None and len(toks) == 3


def test_ignore_eos_forces_max_tokens(mock_url):
    async def go():
        be = OpenAICompatBackend(mock_url, "mock-model", ignore_eos=True)
        try:
            return await be.stream(_req(max_tokens=12), on_first_token=lambda: None)
        finally:
            await be.aclose()
    assert asyncio.run(go()).output_tokens == 12


def test_over_context_is_backend_error_not_crash(mock_url):
    async def go():
        be = OpenAICompatBackend(mock_url, "mock-model")
        try:
            return await be.stream(_req(n=4000, max_tokens=500), on_first_token=lambda: None)
        finally:
            await be.aclose()
    res = asyncio.run(go())
    assert not res.ok and res.http_status == 400


def test_backend_down_yields_backend_error_rows():
    wl = WorkloadConfig(workload_id="down", duration_s=2, tenants=[tenant("A", 3.0)])
    items = generate_trace(wl, 1)
    rec = RunRecorder("t", "down")
    gw = Gateway(FCFSPassThrough(), ["A"], rec)

    async def go():
        be = OpenAICompatBackend("http://127.0.0.1:9", "m", connect_timeout_s=0.5)
        try:
            return await run_live(OpenLoopClient(items), gw, be, LiveConfig(end_time_s=10, metrics_interval_s=0.5))
        finally:
            await be.aclose()
    ts = asyncio.run(go())
    statuses = {r["terminal_status"] for r in rec.rows.values()}
    assert statuses == {"backend_error"}
    assert validate_events(rec.events, set(rec.rows)) == []
    assert ts and not any(r["scrape_ok"] for r in ts)  # metric interruption recorded


def test_slow_backend_timeout_and_cutoff():
    slow = EngineParams(max_model_len=4096, c0_s=0.05, max_num_seqs=1)
    wl = WorkloadConfig(workload_id="slow", duration_s=2, max_model_len=4096, tenants=[tenant("A", 4.0, out_median=200)])
    items = generate_trace(wl, 2)
    with local_mock_server(BackendConfig(kind="mock_http", engine=slow)) as url:
        rec = RunRecorder("t", "slow")
        gw = Gateway(FCFSPassThrough(), ["A"], rec)

        async def go():
            be = OpenAICompatBackend(url, "mock-model", send_mock_oracle_header=True)
            try:
                return await run_live(OpenLoopClient(items), gw, be,
                                      LiveConfig(end_time_s=4, request_timeout_s=1.5, metrics_interval_s=0.5))
            finally:
                await be.aclose()
        asyncio.run(go())
    st = pd.Series([r["terminal_status"] for r in rec.rows.values()]).value_counts().to_dict()
    assert st.get("timed_out", 0) > 0
    assert sum(st.values()) == len(items)
    assert validate_events(rec.events, set(rec.rows)) == []


def test_end_to_end_runner_mock_http(tmp_path):
    wl = WorkloadConfig(workload_id="e2e", duration_s=4, max_model_len=4096,
                        tenants=[tenant("A", 2.0), tenant("B", 1.0, prompt_median=600)])
    cfg = ExperimentConfig(experiment_id="it", workload=wl,
                           backend=BackendConfig(kind="mock_http", engine=EngineParams(max_model_len=4096)),
                           gateway=GatewayConfig(max_queue_wait_s=10), run=RunControl(drain_s=10, request_timeout_s=10))
    out = run_experiment(cfg, "fcfs", 3, tmp_path, config_base=tmp_path)
    for f in ("manifest.json", "config.resolved.yaml", "requests.parquet", "events.parquet",
              "metrics_timeseries.parquet", "metrics_summary.json", "trace.jsonl"):
        assert (out / f).exists(), f
    s = json.loads((out / "metrics_summary.json").read_text())
    m = json.loads((out / "manifest.json").read_text())
    assert s["accounting_conserved"] and s["event_validation_ok"]
    assert m["synthetic_backend"] is True and "NOT GPU" in m["integrity_note"]
    assert m["clock"] == "monotonic" and m["trace_sha256"]
