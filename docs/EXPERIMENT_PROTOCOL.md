# Experiment Protocol (draft v0.1 — to be frozen before final evaluation)

## 1. Primary metric and pre-registered comparisons
- Primary: **SLO goodput (req/s)** with the offered-load denominator (METRIC_DEFINITIONS.md).
- Key comparisons (to be frozen after E0/E1 and before E2–E8 test runs): proposed method vs (i) vLLM FCFS,
  (ii) vLLM priority, (iii) static per-tenant token buckets, (iv) WFQ/DRR, (v) tuned GPU-aware heuristic,
  (vi) VTC/JITServe where comparable — on worst-tenant SLO attainment and aggregate SLO goodput.

## 2. Platform gates
- E0 must show *controlled saturation*: a measured knee where in-window throughput stops tracking offered load,
  repeatable across ≥3 trials, with valid event accounting (0 validation errors). Otherwise stop.
- Feasible-regime SLOs (TTFT/TPOT per tenant class) are calibrated from E0 and **fixed** before M2 comparisons.

## 3. Workload calibration (from E0, not assumed)
Tenant rates/lengths/deadlines in `configs/tenants/three_tenants.yaml` are placeholders. After E0:
set per-class TTFT/TPOT targets to a feasible percentile at ~0.5–0.8× knee load; scale tenant rates so the
aggregate sweeps 0.5–2.0× the measured knee (E2).

## 4. Runs
- Open-loop arrivals (primary); closed-loop only for E0 grid and sensitivity.
- Paired design: all methods replay the **same trace** (same seed, same `trace_sha256`).
- ≥5 independent repeats per key real-GPU condition; run order randomized per block; a fixed warm-up episode
  before each block; prefix caching disabled unless the experiment is about caching.
- Stop-time cap: `duration_s + drain_s`, then every non-terminal request is `cancelled` (`run_cutoff`) and counted.

## 5. Statistics
- Unit of analysis = run (trace). Report per-run raw values, paired differences, bootstrap 95% CI over runs.
- No significance claims from smoke runs or n<5.

## 6. Tuning and test separation
- Tuning traces: seeds 1000–1999; test traces: seeds 2000–2999 (generated once, hashes recorded).
- Equal tuning budget (number of configurations × runs) for every method, including baselines.

## 7. Failure handling
- OOM / startup failures / backend errors are explicit rows with root-cause notes; never dropped.
- E0 cells exceeding `max_model_len` are `skipped_unsupported`; cells over the time budget are `aborted_budget`.

## 8. Provenance (every run)
`manifest.json`: schema version, seed, scheduler, backend kind (+ `synthetic_backend`), backend `/version` and
`/v1/models`, config hash, trace hash, git SHA/dirty flag, Python/packages, platform, GPU static info.
Real-GPU runs must additionally record image digest, model/tokenizer revision, driver/CUDA (nvidia-smi),
and GPU clocks/temperature (sampled in `metrics_timeseries.parquet` when `nvidia-smi` exists).
