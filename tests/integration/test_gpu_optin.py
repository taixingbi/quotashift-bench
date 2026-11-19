"""Real-GPU tests: opt-in only (QUOTASHIFT_GPU_TESTS=1 and QUOTASHIFT_VLLM_URL=http://host:8000)."""

import asyncio
import os

import pytest

from quotashift.serving.openai_backend import OpenAICompatBackend

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(os.environ.get("QUOTASHIFT_GPU_TESTS") != "1" or not os.environ.get("QUOTASHIFT_VLLM_URL"),
                       reason="real-GPU tests are opt-in: set QUOTASHIFT_GPU_TESTS=1 and QUOTASHIFT_VLLM_URL"),
]


def test_vllm_endpoint_metrics_resolve():
    async def go():
        be = OpenAICompatBackend(os.environ["QUOTASHIFT_VLLM_URL"], os.environ.get("QUOTASHIFT_VLLM_MODEL", "Qwen/Qwen3-1.7B"))
        try:
            return await be.info(), await be.scrape_metrics()
        finally:
            await be.aclose()
    info, snap = asyncio.run(go())
    assert snap is not None
    for k in ("num_requests_running", "num_requests_waiting", "kv_cache_usage_perc", "num_preemptions_total"):
        assert snap.values[k] is not None, f"{k} missing; resolved={snap.resolved_names}"
