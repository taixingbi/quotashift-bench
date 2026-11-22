# A7–A9 experiment design (protocol v3) — pre-registered 2026-11-21, before any A7–A9 run

Scope: attack-side characterization on the owned, private, self-hosted vLLM only (192.168.86.173, vLLM 0.17.1,
Qwen2.5-7B-Instruct). No defenses, no scheduling changes, no public targets. Synthetic, benign, owned prompts.
Historical A1–A5 (protocol v1) and the v2 replication series are untouched (docs/HISTORICAL_ARCHIVE.md).

## Protocol v3 (shared)

`protocol_version: 3` extends v2 (ADR-Q13): per-arm salted prompt construction, counterbalanced arm order
(odd paired seeds run the control first), per-arm before/after engine counter snapshots, unrelated-traffic and
counter-reset flags, fail-closed `expect_prefix_caching`. v3 adds:

- **Reuse-preserving salting** (A7, A9-prefix): when prefix reuse is the experimental variable, the per-request v2
  nonce is NOT applied (it would destroy reuse). Instead every shared prefix is derived from
  `H(isolation_salt, scenario, seed, arm, tenant)`, so reuse happens only *within* an arm, never across arms.
- **Lifecycle plans** (A8): deterministic per-request plans (complete / cancel after N streamed chunks / client
  timeout after T s / bounded retry), kept beside the trace so the request schema and historical hashes are unchanged.
- **Optional verified cache reset** (`cache_reset: vllm_endpoint`): `POST /reset_prefix_cache` before each arm,
  verified with a probe (a prompt sent twice must hit, then miss after the reset). Fails closed if unverifiable.
- **Direction-aware endpoints**: `effect_direction: increase | two_sided` and per-scenario thresholds with a written
  justification. Classification from the 95% bootstrap CI over paired seeds: *supported* (CI entirely beyond the
  threshold region), *negative* (CI entirely inside `(1/thr, thr)` for two-sided, `< thr` for increase),
  otherwise *inconclusive*.
- **Cost accounting** per run: requested vs realized tokens, prefill-computed tokens (Δprompt − Δprefix hits),
  generation tokens, engine prefill/decode time sums, engine-busy seconds, GPU dynamic energy (when power is
  sampled), KV usage max/mean, waiting max.

Thresholds are **not** inherited from A1–A5 (1.5×). Justification for the values below: 1.25× is the smallest
effect we treat as practically relevant for a single shared GPU; it is ≥ 2× the typical half-width of the
per-seed spread we expect from the A7-V A/A null run (to be measured first). If A7-V's 95% CI half-width
exceeds 0.25, the A7–A9 suites are declared **underpowered** at n = 5 and reported as exploratory.

Common: ≥ 5 paired seeds; identical victim traces within a pair; fixed caps; fixed FCFS admission; P50/P95/P99
reported where n ≥ 20 completed victim requests per arm (else P50/P95 only, flagged); arms with
`unrelated_traffic_suspected` are excluded from claims and reported.

## A7 — Prefix-cache state interference (`experiments/v3/a7_prefix_cache.yaml`)

- **Hypothesis H7:** the competitor's prefix-cache state changes victim TTFT under identical request count,
  arrival schedule, total requested tokens, I/O composition and output limits. Two-sided: reuse can *reduce*
  interference (cheaper competitor prefill) or *increase* it (resident shared blocks vs. eviction dynamics).
- **Threat model:** an authorized tenant controls only its own prompt structure (shared vs. unique prefixes)
  within its quota; it cannot see or send victim prompts.
- **Variable:** competitor prefix reuse. **A7-A (attack arm):** every competitor request starts with the same
  768-token arm-salted prefix (reused within the arm). **A7-C (control):** identical lengths, but each prefix is
  unique to its request (non-reusable).
- **Victims:** each victim tenant has its own 192-token arm-salted shared system prefix (realistic tenant
  prompt reuse), identical structure in both arms, so victim cache benefit can be displaced or not.
- **Matched:** request ids, count, arrival times, every request's word/token count, max_tokens, victim traffic,
  serving config. Tokenized lengths are verified equal across arms on the live tokenizer (single-token vocab).
  **[Correction 2026-11-21, ADR-Q17]** This holds for the nonce/prefix vocabulary only; the pseudo-syllable filler is
  ~2.1 tokens per word, so v3 token counts are whitespace words (docs/KNOWN_LIMITATIONS.md). v3.1 fixes this.
- **Mechanism observable:** engine Δprefix hits / Δqueries, prefill-computed tokens, KV usage, waiting depth.
- **Primary metric:** victim TTFT P95 ratio A7-A / A7-C, two-sided, threshold 1.25 (effect if ≥ 1.25 or ≤ 0.8).
- **Confounders:** residual cache residency from the previous arm (handled by per-arm salting + counterbalanced
  order; *only a verified reset makes the start state equal* — without it A7 is labelled **exploratory**);
  realized output length (`ignore_eos` off by default → reported); per-tenant cached tokens are not observable
  (vLLM returns `prompt_tokens_details: null` on this server) so hit attribution is engine-global.
- **Falsification:** CI inside (0.8, 1.25) → negative; hit-ratio difference between arms < 0.1 → manipulation
  failed (experiment invalid, reported).

### A7-V — Cache-isolation validation (separate protocol, `experiments/v3/a7v_cache_isolation_validation.yaml`)
A/A design: both arms send the identical workload with the v2 per-request nonce (no intended reuse). Endpoint:
per-arm hit ratio ≤ 0.01 in every arm, and the TTFT P95 ratio CI contains 1. Its CI half-width is the noise
floor used above. Never combined with A7 data.

## A8 — Request lifecycle / cancellation churn

Two configs, because retries change the offered count:

- **A8a `a8_lifecycle_churn.yaml`:** competitor decode-heavy requests; attack plans per request (deterministic by
  seed): 40% cancelled by the client after 16 streamed chunks (documented client mechanism: closing the stream),
  20% client timeout after 1.0 s, 40% complete. Control: identical requests, all complete. **Exactly matched:**
  offered requests, arrival schedule, requested tokens. **Differs by design:** realized GPU work (reported).
- **A8b `a8_retry_churn.yaml`:** 50% of competitor requests time out after 1.0 s and are retried once after a
  0.5 s backoff (`max_retries` ≤ 2 by schema, retries only after cancel/timeout). Control: the same requests
  complete, plus an equal-shaped normal request pre-scheduled at each planned retry time (arrival + 1.0 + 0.5 s),
  so *planned* offered count and requested tokens match. Retries that do not fire (request finished < 1 s) are
  counted and reported.
- **Hypothesis H8:** lifecycle churn changes victim TTFT P95 beyond what its realized work explains. One-sided
  increase, threshold 1.25 (naively, cancellation *reduces* work, so ≥ 1.25 indicates lifecycle overhead).
- **Threat model:** an authorized tenant uses only the documented client API (stream close, client timeout,
  bounded retry); no protocol abuse, no unbounded loops.
- **Secondary:** realized-work-normalized ratio; cancellation cleanup latency (client: decision → stream closed;
  engine: running/KV recovery from 0.25 s scrapes); token reservations/refunds; gateway/engine in-flight.
- **Correctness gates (must hold, not hypotheses):** after each arm gateway in-flight = 0, ledger reserved = 0,
  rate-limit reservations released, engine `num_requests_running` returns to 0 within 10 s. A violation stops the
  experiment (`LifecycleLeak`) and is recorded as a defect for a minimal bounded reproduction.
- **Confounders:** engine-side abort timing is only observable at scrape resolution; cancellation reduces decode
  work; retries add prefill.
- **Falsification:** CI < 1.25 → negative for H8.

## A9 — Token budget vs GPU compute-cost mismatch

- **Hypothesis H9:** equal authorized tokens do not imply equal GPU cost. Families with matched authorized tokens
  differ in measured cost per 1,000 authorized tokens.
- **Families (competitor):** prefill (1024 in / 32 out), decode (48 / 256), long context (3584 / 256), prefix
  reuse (prefill family with a shared 768-token prefix in the attack arm). Each vs a short-request reference.
- **Two separate series (never pooled):** token-budget-matched (`a9_tok_*`, control `matched_total_short`) and
  request-rate-matched (`a9_rate_*`, control `rate_matched_short`, tokens differ → cost normalized per 1k
  authorized tokens).
- **Primary metric:** GPU *dynamic* energy per 1,000 authorized tokens, ratio attack/control, two-sided,
  threshold 1.25. Energy = ∫(P(t) − P_idle) dt from time-aligned board-power samples, P_idle measured right
  before each arm. **Requires GPU telemetry on the host**; if power is unavailable the primary endpoint is
  reported as *unavailable* (not substituted) and A9 is reported on secondaries only, labelled exploratory.
- **Secondary:** engine service seconds (Δprefill-time + Δdecode-time sums) per 1k authorized tokens,
  prefill-computed tokens, generation tokens, engine-busy seconds, KV usage, victim TTFT P95 ratio, and
  interference per 1k authorized tokens = (victim TTFT P95 ratio − 1) / (competitor authorized tokens / 1000).
- **Not GPU cost:** GPU utilization % is reported but never used alone as a cost measure.
- **Distinct from A2/A3:** A2/A3 measure victim degradation; A9's endpoint is cost per authorized token.
- **Confounders:** board power includes idle/other processes and victims' (identical) work; 1 s sampling;
  engine time sums overlap across batched requests (they measure request-seconds, not exclusive GPU time).
- **Falsification:** energy-ratio CI inside (0.8, 1.25) for a family → token accounting is a fair cost proxy
  for that family (negative for H9).

## Run budget (Phase 4, not started)

See `experiments/PLAN.md` § Suite S (A7–A9). Each block is launched explicitly after approval.

## Amendments (dated; none changes a metric, threshold or control)

- **2026-11-21 (after Phase 3 smokes, tooling fix):** the unrelated-traffic attribution check compared engine
  token deltas with usage from *completed* requests only, so cancelled/timed-out requests (prefilled and partly
  decoded by vLLM, but reporting no usage) produced false `unrelated_traffic_suspected=True` on every A8 attack arm.
  The check now adds an upper bound for requests that reached the engine without completing (prompt: 1.25 × the
  run's real/planned token ratio × planned input; generation: their requested max_tokens) and records
  `attribution_mode: exact | bounded | unverifiable`. Re-run A8 smokes: all arms `False`. A bounded check is weaker
  than an exact one (unrelated traffic smaller than the bound would not be detected).
- **2026-11-21:** `POST /reset_prefix_cache` returns HTTP 404 on 192.168.86.173 (not enabled), so the verified-reset
  A7 variant (`a7_prefix_cache_reset`) is blocked; A7 runs as pre-registered **exploratory**.
- **2026-11-21:** GPU board power is not yet sampled (no exporter on the host), so A9's primary endpoint is
  `unavailable` in smokes; it is not substituted by a secondary.
- **2026-11-21 (re-verified after the owner restarted vLLM per
  [vllm-qwen-serving/per_tenant_cache](https://github.com/taixingbi/vllm-qwen-serving/blob/main/per_tenant_cache/PER_TENANT_PREFIX_CACHE_GUIDE.md),
  i.e. `VLLM_SERVER_DEV_MODE=1 --enable-prefix-caching --enable-prompt-tokens-details --gpu-memory-utilization 0.80`;
  server start 2026-11-21 11:05:29 UTC, vLLM 0.17.1):**
  - `/reset_prefix_cache` is in `/openapi.json`, and the harness's `reset_and_verify` passed: HTTP 200, probe
    hits went from 96 before the reset to 0 after it. **The verified-reset A7 variant (`a7_prefix_cache_reset`)
    is unblocked**, and A7 runs as confirmatory under it. The no-reset `a7_prefix_cache` stays exploratory,
    as pre-registered.
  - Per-request `usage.prompt_tokens_details.cached_tokens` is now reported (chat and streaming completions:
    a repeat of the same 569-token prompt returned `cached_tokens: 560`). A cold request returns `null`, which
    counts as *missing telemetry, not 0*. Per-tenant hit ratios are observable; the harness now records them
    (`cached_tokens` in run summaries, reported-only with coverage) as a **secondary** metric. They never replace
    a pre-registered endpoint. Live A7 smoke: Σ per-request cached tokens = engine Δhits, exactly.
  - GPU telemetry is still unavailable: no exporter answers on the host, and the runner has no SSH key. A9's
    primary endpoint stays blocked.
  - The restart changes the serving config (`gpu_memory_utilization` 0.85 → 0.80, 4662 GPU KV blocks), so smokes
    and full runs from before 11:05:29 UTC are **not pooled** with runs after it.
  - Dev mode also exposes `/collective_rpc`, `/update_weights`, `/sleep`, `/pause` and similar endpoints without
    authentication. The harness calls only `/reset_prefix_cache`. Keep the server on the isolated LAN only.
- **2026-11-21 06:36–06:51 local (GPU power verified; measurement-method correction, before any full A9 run):**
  - **Telemetry source:** `nvidia_gpu_exporter` v2.0.0 on the GPU host, port 9835, readable from the runner
    without SSH (per vllm-qwen-serving `self-hosted-sample-output.md`, "Reading the same GPU state from the
    Mac"). The harness now parses its `nvidia_smi_*` metrics. They're labelled by uuid; the index comes from
    `nvidia_smi_gpu_info`, and units are converted (ratio → %, bytes → MiB, Hz → MHz). The GPU is now
    **measured**: RTX 3090, uuid a837190a-d9c2-ed45-994b-55319c6e258e, driver 595.71.05, CUDA 13.2,
    350 W limit. Scrapes take about 100 ms; arm samples are spaced about 0.6 s apart.
  - **Defect found and fixed: the idle baseline.** The original baseline (3 samples right before an arm)
    measured **216 W** before an arm that started right after the previous arm. A util-0 + power-stability
    check still accepted a **124 W** plateau. On the 3090, measured: after work the GPU keeps load clocks
    (SM 1725 / mem 9501 MHz) at about 130 W with 0% util for about 16 s, then drops to idle (SM 210 /
    mem 405 MHz, about 31 W, with about 40 W blips every 7 s).
    - **New criterion:** the last 6 samples (0.5 s apart) must show util 0, SM clock ≤ 500 MHz and power spread
      ≤ 15 W. The wait is bounded at 90 s; if the GPU doesn't settle, idle power is `None` and dynamic energy is
      unavailable (never guessed). Idle power is the window **median**, which is robust to the blips.
    - **Why this is a correction, not a metric change:** the pre-registered definition is "P_idle measured right
      before each arm"; the old code didn't measure idle power. The metric, threshold and control are unchanged.
  - **Added secondary: the post-arm tail.** After the arm's engine drain, the harness keeps sampling until the
    GPU is idle again (bounded at 90 s) and reports `gpu_tail` and `gpu_dynamic_energy_with_tail_j`. The tail
    is energy caused by the arm that falls outside its window: in smokes about 22 s and about 2.0 kJ per arm,
    roughly 30–45% of the arm-window dynamic energy. The **primary** endpoint stays the pre-registered
    arm-window dynamic energy; the with-tail value is reported beside it, and any disagreement in direction is
    reported.
  - **Classification gate:** `classification` is `insufficient_seeds` when fewer than the pre-registered 5
    paired seeds have the metric. Before this, a 1-seed run printed "supported" from a zero-width CI.
  - Smokes `reports/v3/smoke_power/a9_tok_prefill_smoke` and `..._settled` used the defective baselines
    (control idle 216 W and 124 W). They're **invalid** and kept only as evidence of the defect. Use
    `..._clock` (2 seeds; harness validation only, no finding).
- **2026-11-21 ~08:05–08:09 local (patched vLLM; reporting only):** the owner restarted .173 on vLLM 0.17.1
  with a local patch to `chat_completion/serving.py` (`num_cached_tokens is not None`), so zero-hit **chat**
  requests report `cached_tokens: 0` instead of null. Measured: chat cold → 0; `/v1/completions` cold → still null.
  The patch changes **reporting only**, not caching, isolation or scheduling. No metric, threshold, control,
  workload or endpoint changes. New server start (1795266115.27) means a new series, per the pooling rule.
  - **Harness changes:** 0 counted as an observation (unchanged); `noncompleted` counted separately; mock mirrors
    the per-endpoint behaviour; per-arm engine reconciliation added (`nulls_implied_zero`,
    `hit_ratio_all_completed_reconciled`, derived and labelled; secondary).
  - **A7 smoke, 1 paired seed, patched server:** identical to the pre-patch smoke (victim coverage 0.885 and
    reported-only 0.520 in both arms; competitor 0.686 attack, n/a control), because the live runner uses
    `/v1/completions`. Reconciliation residual was 0 in both arms with exact attribution, so the nulls are zeros:
    victim all-completed ratio 0.452 (both arms), competitor 0.585 (attack) and 0.000 (control). Single seed;
    harness validation only, not an effect.
- **2026-11-21 08:45–08:47 local (completions patch; reporting only):** the owner applied the same fix to the
  completions serving code and restarted (start 1795268683.89 = 13:44:43 UTC, PID 455271, owner-stated). This is
  a new series. Measured: cold `/v1/completions` → `cached_tokens: 0` (stream and non-stream). A7 smoke, 1 paired
  seed, unchanged config: coverage 1.000 everywhere, 0 nulls, reconciliation residual 0 in both arms (9424 / 4240),
  and observed ratios identical to the earlier derived values (victim 0.452 both arms; competitor 0.585 attack,
  0.000 control). No metric, threshold, control, workload or endpoint changed; the mock now mirrors the fully
  patched target. Single seed, not an effect.
- **2026-11-21 09:00–09:08 local (tooling; no metric, threshold or control changed):** added a fail-closed engine
  preflight (awake + idle, bounded at 30 s), a stop on server restart, a per-suite target snapshot,
  `prefill_computed_tokens_measured` from `prompt_tokens_by_source_total` (secondary, beside the
  pre-registered estimate), and a warm-cache re-run guard. The guard came from an invalid smoke: an A7 smoke repeated
  on the same server start with the same salt hit 98.6% of prompt tokens in both arms, because the prefix cache
  persists across runs. Each Suite S block therefore runs once per salt per server start.

## Amendment 2026-11-21 — Suite S audit and protocol v3.1

- Audit: `reports/v3/SUITE_S_FORENSIC_AUDIT.md`; corrected analysis: `reports/v3/SUITE_S_CORRECTED_ANALYSIS.md`.
- `a9_tok_longctx` and `a9_rate_longctx` (v3) are **invalid** (competitor HTTP 400 on context length) and are
  replaced by the v3.1 blocks in `docs/PROTOCOL_V3_1_LONGCTX_AMENDMENT.md`. All other thresholds, metrics and
  classifications are unchanged.
- TTFT definitions and report labels: ADR-Q16; validity gates: ADR-Q17 (`docs/ADR_TTFT_METRIC_CORRECTION.md`).
