from __future__ import annotations

from pathlib import Path

import pytest

from risksched.schema import (
    ArrivalProcess,
    LengthDist,
    SLOSpec,
    SLOType,
    TenantProfile,
    WorkloadConfig,
)

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo() -> Path:
    return REPO


def tenant(tid: str, rate: float = 1.0, out_median: float = 50, prompt_median: float = 100, max_out: int = 256,
           process: str = "poisson", **arr) -> TenantProfile:
    return TenantProfile(
        tenant_id=tid,
        workload_class=f"class_{tid}",
        arrival=ArrivalProcess(process=process, rate_rps=rate, **arr),
        prompt_tokens=LengthDist(dist="lognormal", median=prompt_median, sigma=0.5, min=8, max=2000),
        max_output_tokens=max_out,
        sim_output_tokens=LengthDist(dist="lognormal", median=out_median, sigma=0.6, min=1, max=max_out),
        slo=SLOSpec(slo_type=SLOType.INTERACTIVE, ttft_deadline_ms=1000, tpot_target_ms=100),
    )


@pytest.fixture
def small_workload() -> WorkloadConfig:
    return WorkloadConfig(
        workload_id="t3",
        duration_s=20,
        max_model_len=4096,
        tenants=[tenant("A", 2.0), tenant("B", 0.5, prompt_median=800), tenant("C", 0.2, process="onoff",
                                                                              burst_rate_rps=4.0, mean_on_s=3, mean_off_s=5)],
    )
