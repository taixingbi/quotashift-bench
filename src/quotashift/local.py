"""Local execution (mock by default, or live against a selected target) of a QuotaShift scenario.

Compiles the scenario to a planned schedule, runs it in-process against the mock
vLLM engine through the fixed FCFS gateway, and writes results via the shared
runner. No cloud, no GPU, no external target. Mock timings are simulator outputs,
flagged `synthetic_backend: true` in the manifest and never a GPU measurement.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quotashift.config import BackendConfig, ExperimentConfig, GatewayConfig, LedgerConfig, RunControl
from quotashift.runtime.runner import REPO, run_experiment
from quotashift.scenario import ScenarioConfig
from quotashift.targets import TargetProfile


def backend_for(scenario: ScenarioConfig, target: TargetProfile | None) -> BackendConfig:
    """Mock backend when `target` is None; otherwise the target's real vLLM."""
    if target is None:
        return BackendConfig(kind="mock", model=scenario.model, ignore_eos=scenario.ignore_eos)
    s = scenario.safety
    need = s.max_input_tokens_per_request + s.max_output_tokens_per_request
    if need > target.max_model_len:
        raise ValueError(f"scenario per-request tokens {need} exceed target {target.name} "
                         f"max_model_len={target.max_model_len}")
    return BackendConfig(kind="vllm", base_url=target.backend_url, model=target.model, ignore_eos=scenario.ignore_eos,
                         model_revision=target.model_revision,
                         gpu_source=("none" if target.gpu_telemetry == "none" else
                                     "exporter" if target.gpu_exporter_url else "nvidia-smi"),
                         gpu_exporter_url=None if target.gpu_telemetry == "none" else target.gpu_exporter_url,
                         gpu_type=(f"{target.gpu_type} ({target.gpu_type_source})" if target.gpu_type else None))


def run_scenario_local(
    scenario: ScenarioConfig, results_root: Path, *, phase_order: list[str] | None = None,
    target: TargetProfile | None = None, trace: list | None = None,
    experiment_id: str | None = None, seed: int | None = None, path: str = "gateway",
    lifecycle_plans: dict | None = None,
) -> Path:
    """Run one scenario arm locally.

    `trace` overrides the compiled schedule (used to run a control arm); `experiment_id`
    names the results subtree (e.g. `<id>__attack` / `<id>__control`); `seed` overrides
    the scenario seed for repetitions. The serving config (caps, quotas, gateway) is
    identical across arms and seeds — only the schedule differs.
    """
    seed = scenario.seed if seed is None else seed
    backend = backend_for(scenario, target)
    wl = scenario.workload_config()
    if trace is None:
        trace = scenario.build_trace(seed=seed, phase_order=phase_order)
    s = scenario.safety
    per_request_tokens = s.max_input_tokens_per_request + s.max_output_tokens_per_request
    # Per-tenant in-flight token quota: enough for the global in-flight cap, applied
    # equally to every tenant (fixed, isolation-only; no borrowing). Hard request/time
    # budgets are enforced by the compiled trace and the runner timeout.
    quota = s.max_global_inflight * per_request_tokens
    tenants = [*scenario.victim_tenants, *scenario.competing_tenants]
    if path not in ("gateway", "direct"):
        raise ValueError(f"path must be gateway|direct, got {path!r}")
    sg = scenario.gateway
    if path == "direct":
        # Direct -> vLLM: requests are submitted at their trace arrival time with no gateway ledger,
        # limits, queue caps or in-flight cap (the engine's own FCFS queue does all queueing).
        # Hard request caps are still enforced by the compiled trace and runner timeouts.
        gw_cfg = GatewayConfig(ledger=None, max_queue_wait_s=None)
        conc_cap = 512
    else:
        ledger = LedgerConfig(quotas={t: quota for t in tenants}, allow_borrow=False)
        if sg is None:
            gw_cfg = GatewayConfig(ledger=ledger)  # historical default
        else:
            gw_cfg = GatewayConfig(ledger=ledger, rate_limits=sg.rate_limits, max_queue_per_tenant=sg.max_queue_per_tenant,
                                   max_queue_total=sg.max_queue_total, max_queue_wait_s=sg.max_queue_wait_s)
        conc_cap = s.max_global_inflight
    cfg = ExperimentConfig(
        experiment_id=experiment_id or scenario.scenario_id,
        description=f"QuotaShift scenario {scenario.scenario_id} "
                    f"({'local mock' if target is None else f'target {target.name}'})",
        workload=wl,
        backend=backend,
        gateway=gw_cfg,
        run=RunControl(
            request_timeout_s=s.per_request_timeout_seconds,
            max_requests_cap=s.max_total_requests + 1,
            max_concurrency_cap=conc_cap,
            metrics_interval_s=scenario.metrics_interval_s or 0.5,
        ),
        schedulers={"fcfs": {}},
        path=path,  # type: ignore[arg-type]
    )
    return run_experiment(cfg, "fcfs", seed, results_root, config_base=REPO, trace_override=trace,
                          lifecycle_plans=lifecycle_plans)


def current_server_start(target: TargetProfile) -> float | None:
    """vLLM `process_start_time_seconds` now (read-only GET); None if unavailable."""
    import httpx

    from quotashift.instrumentation.prom import parse_prometheus_text, resolve

    try:
        r = httpx.get(target.backend_url.rstrip("/") + "/metrics", timeout=10.0)
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    return resolve(parse_prometheus_text(r.text)).values.get("process_start_time_seconds")


def warm_cache_reruns(results_root: Path, experiment_id: str, trace: list, server_start: float | None) -> list[Path]:
    """Earlier runs of the byte-identical trace (same trace_sha256) on the SAME vLLM server start.

    The prefix cache persists across runs, so re-sending identical prompts without a verified reset measures
    a warm cache (observed 2026-11-21: an A7 smoke repeated on the same server start hit 98.6% in both arms).
    Protocol rule (PLAN.md): a new `isolation_salt` per replication, or `cache_reset: vllm_endpoint`."""
    if server_start is None:
        return []
    from quotashift.workload.generator import trace_hash

    sha = trace_hash(trace)
    hits = []
    for man in sorted((results_root / experiment_id).glob("*/manifest.json")):
        try:
            m = json.loads(man.read_text())
            summ = json.loads((man.parent / "metrics_summary.json").read_text())
        except (OSError, ValueError):
            continue
        st = ((summ.get("engine_counters") or {}).get("engine_state_at_start") or {}).get("process_start_time_seconds")
        if m.get("trace_sha256") == sha and st == server_start:
            hits.append(man.parent)
    return hits


def run_matched_pairs(
    scenario: ScenarioConfig, results_root: Path, *, reps: int, target: TargetProfile | None = None,
    path: str = "gateway", allow_warm_rerun: bool = False,
) -> dict:
    """Run the attack and its matched control over `reps` seeds (Phase 5 orchestration).

    Seeds are `scenario.seed + i`. Both arms use the identical serving config; only the
    schedule differs. Returns run directories per arm keyed by seed, plus the control
    label and the matched-budget report per seed so the analysis can record the pairing.
    """
    from quotashift.budget import budget_report, summarize_trace

    seeds = [scenario.seed + i for i in range(reps)]
    from quotashift.workload.tokenize import VllmTokenizer, WhitespaceTokenizer, verify_trace

    count = VllmTokenizer(target.backend_url, target.model) if target is not None else WhitespaceTokenizer()
    exact = scenario.prompt_token_unit == "tokenizer"
    tokenization: dict[str, Any] = {"tokenizer": count.identity, "prompt_token_unit": scenario.prompt_token_unit,
                                    "per_seed": {}}
    frozen = load_frozen_traces(scenario)
    for s in seeds:  # fail closed BEFORE any request is sent: every planned request must fit the context
        a_tr, c_tr, _ = paired_traces(scenario, s, count)
        if frozen is not None:  # v4: the traces about to be sent must be exactly the reviewed, frozen ones
            check_frozen(frozen, scenario, s, a_tr, c_tr)
        tokenization["per_seed"][s] = {
            arm: verify_trace(tr, count, max_model_len=scenario.model_max_len, exact=exact, label=f"{arm} seed {s}")
            for arm, tr in (("attack", budget_view(scenario, a_tr, s)), ("control", c_tr))}
    attack: dict[int, Path] = {}
    control: dict[int, Path] = {}
    budgets: dict[int, dict] = {}
    order: dict[int, list[str]] = {}
    resets: dict[int, dict] = {}
    server_start: float | None = None  # process_start_time_seconds of the first arm; must not change
    guard_start = (current_server_start(target) if target is not None and scenario.cache_reset == "none"
                   and not allow_warm_rerun else None)
    if guard_start is not None:  # refuse BEFORE any run: identical prompts already sent to this server start
        prior: list[Path] = []
        for s in seeds:
            a_tr, c_tr, _ = paired_traces(scenario, s, count)
            prior += warm_cache_reruns(results_root, f"{scenario.scenario_id}__attack", a_tr, guard_start)
            prior += warm_cache_reruns(results_root, f"{scenario.scenario_id}__control", c_tr, guard_start)
        if prior:
            raise WarmCacheRerun(
                f"{len(prior)} earlier run(s) sent byte-identical prompts to this vLLM server start "
                f"({guard_start}); the prefix cache is warm. Use a new isolation_salt for a new replication, "
                f"or cache_reset: vllm_endpoint. First: {prior[0]}")
    label: str = scenario.comparison.primary_control
    v2 = scenario.protocol_version >= 2
    # X2 boundary snapshots (docs/X2_INSTRUMENTATION_SPEC.md): opt-in via QUOTASHIFT_X2_BOUNDARY, set only by X2 drivers.
    # Unset (v4/v5/X1 and every other caller): None, and nothing below changes behaviour.
    from quotashift.x2.snapshot import from_env as _x2_boundary_from_env

    boundary = _x2_boundary_from_env()
    boundary_log: dict[int, dict] = {}
    for i, s in enumerate(seeds):
        atk_trace, ctl_trace, label = paired_traces(scenario, s, count)
        # budget gate is evaluated on exactly the traces that will be sent (post-nonce in v2)
        budgets[s] = budget_report(summarize_trace(budget_view(scenario, atk_trace, s)), summarize_trace(ctl_trace),
                                   scenario.comparison)
        arms = ["attack", "control"]
        if v2 and i % 2 == 1:
            arms.reverse()  # counterbalanced: odd paired seeds run the control first
        order[s] = arms
        for arm in arms:
            if scenario.cache_reset == "vllm_endpoint" and target is not None:
                from quotashift.instrumentation.cache_reset import reset_and_verify

                rv = reset_and_verify(target.backend_url, target.model, tag=f"{scenario.scenario_id}-{s}-{arm}")
                resets.setdefault(s, {})[arm] = rv
                if not rv["verified"]:
                    raise CacheResetUnverified(f"cache reset before {arm} seed {s} not verified: {rv}")
            plans = None
            if arm == "attack" and scenario.lifecycle is not None:
                from quotashift.workload.lifecycle import lifecycle_plans

                plans = lifecycle_plans(scenario, atk_trace, s)
            pre = boundary.before(f"{scenario.scenario_id}/{s}/{arm}") if boundary is not None else None
            out = run_scenario_local(
                scenario, results_root, target=target, trace=atk_trace if arm == "attack" else ctl_trace,
                experiment_id=f"{scenario.scenario_id}__{arm}", seed=s, path=path, lifecycle_plans=plans)
            if boundary is not None and pre is not None:
                rec = boundary.after(pre, out)
                boundary_log.setdefault(s, {})[arm] = {"flags": rec["flags"], "metrics": rec["metrics"],
                                                       "transport": rec["transport"], "guard_s": rec["guard_s"]}
            (attack if arm == "attack" else control)[s] = out
            summ = json.loads((out / "metrics_summary.json").read_text())
            st = ((summ.get("engine_counters") or {}).get("engine_state_at_start") or {}).get("process_start_time_seconds")
            ec = summ.get("engine_counters") or {}
            if ec.get("server_restarted") or (st is not None and server_start is not None and st != server_start):
                raise ServerRestarted(f"vLLM restarted during the experiment (start {server_start} -> {st}, "
                                      f"arm {arm} seed {s}); runs across server starts are never pooled")
            server_start = st if server_start is None else server_start
            chk = summ.get("cleanup_checks") or {}
            if chk.get("leak_detected"):  # stop the stress experiment; record the defect
                raise LifecycleLeak(f"cleanup check failed after {arm} seed {s}: {chk} (run dir {out})")
    res = {"seeds": seeds, "attack": attack, "control": control, "control_label": label, "budgets": budgets,
           "arm_order": order, "protocol_version": scenario.protocol_version, "path": path,
           "cache_resets": resets, "tokenization": tokenization}
    if boundary is not None:
        res["x2_host_snapshots"] = boundary_log
    return res


def budget_view(scenario: ScenarioConfig, atk: list, seed: int) -> list:
    """Attack trace as budgeted: + planned retry twins when the control pre-schedules them (A8b)."""
    lc = scenario.lifecycle
    if lc is not None and lc.control_preschedule_retries:
        from quotashift.workload.lifecycle import control_with_retry_twins

        return control_with_retry_twins(scenario, atk, seed)
    return atk


class FrozenTraceMismatch(RuntimeError):
    """A v4 trace differs from the frozen, reviewed manifest (or is missing from it); nothing was sent."""


def load_frozen_traces(scenario: ScenarioConfig) -> dict | None:
    if scenario.frozen_traces is None:
        return None
    base = scenario._source_dir or Path.cwd()
    p = (base / scenario.frozen_traces).resolve()
    if not p.exists():
        raise FrozenTraceMismatch(f"frozen trace manifest {p} not found (run scripts/freeze_v4.py)")
    return json.loads(p.read_text())


def check_frozen(frozen: dict, scenario: ScenarioConfig, seed: int, atk: list, ctl: list) -> None:
    from quotashift.workload.generator import trace_hash

    ent = (frozen.get("scenarios") or {}).get(scenario.scenario_id, {}).get(str(seed))
    if ent is None:
        raise FrozenTraceMismatch(f"{scenario.scenario_id} seed {seed} is not in the frozen manifest")
    for arm, tr in (("attack", atk), ("control", ctl)):
        h = trace_hash(tr)
        if h != ent[arm]["trace_sha256"]:
            raise FrozenTraceMismatch(f"{scenario.scenario_id} seed {seed} {arm}: trace {h[:12]} != frozen "
                                      f"{ent[arm]['trace_sha256'][:12]}")


class LifecycleLeak(RuntimeError):
    """A cleanup/accounting check failed after an arm; the experiment is stopped (A8 safety rule)."""


class WarmCacheRerun(RuntimeError):
    """Identical prompts were already sent to the current server start without a verified reset."""


class ServerRestarted(RuntimeError):
    """vLLM's process start time changed between or within arms; the series is broken, stop."""


class CacheResetUnverified(RuntimeError):
    """A pre-registered cache reset could not be verified; fail closed."""


def paired_traces(scenario: ScenarioConfig, seed: int, count=None) -> tuple[list, list, str]:  # noqa: ANN001
    """(attack, control) traces exactly as sent. v2 applies the per-arm salted nonce to both.

    v3.1 (`prompt_token_unit: tokenizer`): after nonce/prefix structure, every prompt is calibrated so `count`
    (the live model tokenizer; whitespace when offline) gives exactly `input_token_count` tokens."""
    atk, ctl, label = _paired_traces_raw(scenario, seed)
    if scenario.prompt_token_unit == "tokenizer":
        from quotashift.workload.tokenize import WhitespaceTokenizer, calibrate_trace

        fn = count if count is not None else WhitespaceTokenizer()
        atk, _ = calibrate_trace(atk, fn)
        ctl, _ = calibrate_trace(ctl, fn)
    return atk, ctl, label


def _paired_traces_raw(scenario: ScenarioConfig, seed: int) -> tuple[list, list, str]:
    atk = scenario.build_trace(seed=seed)
    ctl, label = scenario.control_trace(seed=seed)
    if scenario.protocol_version == 3 and scenario.prefix_cache is not None:
        from quotashift.workload.prefix_cache import apply_prefix_structure

        pc, sid, salt = scenario.prefix_cache, scenario.scenario_id, scenario.isolation_salt
        common = {"victim_prefix_tokens": pc.victim_prefix_tokens, "competitor_prefix_tokens": pc.competitor_prefix_tokens,
                  "scenario_id": sid, "seed": seed, "salt": salt}
        atk = apply_prefix_structure(atk, arm="attack", competitor_mode=pc.attack_competitor_mode, **common)  # type: ignore[arg-type]
        ctl = apply_prefix_structure(ctl, arm="control", competitor_mode=pc.control_competitor_mode, **common)  # type: ignore[arg-type]
    elif scenario.protocol_version >= 2:
        from quotashift.workload.isolation import apply_arm_nonce

        sid, salt = scenario.scenario_id, scenario.isolation_salt
        atk = apply_arm_nonce(atk, arm="attack", scenario_id=sid, seed=seed, salt=salt)
        if scenario.comparison.primary_control == "lifecycle_normal":
            # nonce first, then twins copy the ORIGINAL's prompt — exactly what the attack arm's retries send
            from quotashift.workload.lifecycle import control_with_retry_twins

            base = apply_arm_nonce(scenario.build_trace(seed=seed), arm="control", scenario_id=sid, seed=seed, salt=salt)
            ctl = control_with_retry_twins(scenario, base, seed)
        else:
            ctl = apply_arm_nonce(ctl, arm="control", scenario_id=sid, seed=seed, salt=salt)
    return atk, ctl, label
