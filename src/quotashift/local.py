"""Local execution (mock by default, or live against a selected target) of a QuotaShift scenario.

Compiles the scenario to a planned schedule, runs it in-process against the mock
vLLM engine through the fixed FCFS gateway, and writes results via the shared
runner. No cloud, no GPU, no external target. Mock timings are simulator outputs,
flagged `synthetic_backend: true` in the manifest and never a GPU measurement.
"""

from __future__ import annotations

from pathlib import Path

from quotashift.config import BackendConfig, ExperimentConfig, GatewayConfig, LedgerConfig, RunControl
from quotashift.runtime.runner import REPO, run_experiment
from quotashift.scenario import ScenarioConfig
from quotashift.targets import TargetProfile


def backend_for(scenario: ScenarioConfig, target: TargetProfile | None) -> BackendConfig:
    """Mock backend when `target` is None; otherwise the target's real vLLM."""
    if target is None:
        return BackendConfig(kind="mock", model=scenario.model)
    s = scenario.safety
    need = s.max_input_tokens_per_request + s.max_output_tokens_per_request
    if need > target.max_model_len:
        raise ValueError(f"scenario per-request tokens {need} exceed target {target.name} "
                         f"max_model_len={target.max_model_len}")
    return BackendConfig(kind="vllm", base_url=target.backend_url, model=target.model,
                         model_revision=target.model_revision)


def run_scenario_local(
    scenario: ScenarioConfig, results_root: Path, *, phase_order: list[str] | None = None,
    target: TargetProfile | None = None,
) -> Path:
    backend = backend_for(scenario, target)
    wl = scenario.workload_config()
    trace = scenario.build_trace(phase_order=phase_order)
    s = scenario.safety
    per_request_tokens = s.max_input_tokens_per_request + s.max_output_tokens_per_request
    # Per-tenant in-flight token quota: enough for the global in-flight cap, applied
    # equally to every tenant (fixed, isolation-only; no borrowing). Hard request/time
    # budgets are enforced by the compiled trace and the runner timeout.
    quota = s.max_global_inflight * per_request_tokens
    tenants = [*scenario.victim_tenants, *scenario.competing_tenants]
    cfg = ExperimentConfig(
        experiment_id=scenario.scenario_id,
        description=f"QuotaShift scenario {scenario.scenario_id} "
                    f"({'local mock' if target is None else f'target {target.name}'})",
        workload=wl,
        backend=backend,
        gateway=GatewayConfig(ledger=LedgerConfig(quotas={t: quota for t in tenants}, allow_borrow=False)),
        run=RunControl(
            request_timeout_s=s.per_request_timeout_seconds,
            max_requests_cap=s.max_total_requests + 1,
            max_concurrency_cap=s.max_global_inflight,
        ),
        schedulers={"fcfs": {}},
    )
    return run_experiment(cfg, "fcfs", scenario.seed, results_root, config_base=REPO, trace_override=trace)
