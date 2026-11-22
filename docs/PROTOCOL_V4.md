# Protocol v4: request granularity, token accounting, GPU compute and gateway concurrency

Status: **pre-registration draft for owner review (2026-11-21). No v4 GPU run has been made.** Decision record:
ADR-Q18 (`docs/DECISIONS.md`). Scope is unchanged from the project charter: attack-side, reproducible
characterization on an owned, private target. There are no defenses, no RL, no scheduler contribution, and no RISK-Sched.
A1–A9 historical measurements, classifications and the corrected analyses
(`reports/v3/SUITE_S_CORRECTED_ANALYSIS.md`) are preserved and are not re-run.

**Research goal.** Characterize how request granularity (requests × tokens per request), token accounting
(authorized vs realized), GPU compute (energy, engine time) and gateway concurrency (a fixed in-flight cap and FCFS queue)
interact in multi-tenant LLM serving.

## 0. What the corrected A2/A9 results showed, and what v4 changes

| Finding (A1–A9 corrected analysis) | v4 response |
|---|---|
| Token-matched short controls (A2, A9-tok) could not execute their budget: gateway queue P95 50–60 s, 54–60% of control victims censored (A2), 93–94% competitor completion (A9-tok), and 74.6% in v3.1 long context | R1 calibrates a **common feasible load** before any comparison, and the ADR-Q17 gates are enforced |
| **New in this review:** the historical `matched_total_short` control generates its pool at **2× the needed rate and keeps the earliest requests**, so it delivers its whole token budget in the **first ~50% of the window** (last competitor arrival ≈ 28–30 s of 60 s in A2, ≈ 56–65 s of 120 s in A9-tok and v3.1; `scenario.py` `_matched_total_short_control`) | The new `token_matched_fixed` control spreads N requests i.i.d. uniform over the **whole** window. A new `arrival_coverage` gate fails any arm whose first competitor arrival is after 25% of the window or whose last is before 75%. The historical control is unchanged, and its results are left as recorded |
| Pre-registered TTFT was backend TTFT (ADR-Q16) | v4 primaries are **user-facing TTFT**, alongside offered-load SLO success and gateway queue time |
| Planned token units were whitespace words (ADR-Q17) | Every v4 size is in **real Qwen2.5 tokens**: calibrated and exactly verified on the live tokenizer, frozen, and re-verified before sending. `ignore_eos: true` makes realized output equal authorized output |
| A9 energy is nearly flat per arm (~300 W while active) | v4 reports **absolute energy** and **energy per realized token** beside per-authorized-token energy |

## 1. Fixed serving configuration (identical in every v4 file and arm)

- **Target.** Self-hosted vLLM 0.17.1 with the owner's local `cached_tokens` patch (SELFHOST §7a), Qwen/Qwen2.5-7B-Instruct,
  `max_model_len` 4096, prefix caching on, chunked prefill on (`/server_info`), `gpu_memory_utilization` 0.80, 4,662 KV
  blocks × 16 tokens. The server reports `revision=None`; see §8.
- **Not exposed by the server:** vLLM's `max_num_seqs` and `max_num_batched_tokens` are not in `/server_info`, so they are
  unknown to the harness. The owner should record the launch flags (§8). They are held fixed by not restarting the server
  within a block. A server restart starts a new series (the `ServerRestarted` stop).
- **Gateway** (R1, R2, and the gateway arm of R3): FCFS, `max_global_inflight: 8`, 60 s gateway queue timeout, per-tenant
  token ledger, no rate limits. **Direct path** (R3 direct arm): no gateway ledger, queue cap, queue timeout or in-flight
  cap (harness cap 512), so vLLM's own scheduler does all the queueing.
- **Per-request timeout** 120 s, runtime 120 s (smokes 40 s), counterbalanced arm order, `cache_reset: none`, and a unique
  `isolation_salt` per file (warm-cache guard).

## 2. Common workload

- **Victims:** 3 tenants × Poisson 0.3 rps, short shape. Prompts are lognormal with median 64 real tokens and a 32-token
  floor; `max_tokens` is 64 (= realized). The SLO is user-facing TTFT ≤ 2 s and E2E ≤ 30 s. Victims are identical across arms
  apart from the per-arm 4-word nonce.
- **Competitor:** one tenant. Each phase fixes `input_tokens` and `output_tokens` in real tokens and an exact `request_count` N,
  with arrivals N i.i.d. uniform over the window (a Poisson process conditioned on N).
- **Token accounting:** authorized = Σ(input + `max_tokens`). With `ignore_eos`, realized = authorized for every completed
  request. Gates `planned_vs_reported_tokens` and `realized_output_equals_authorized` verify this per request.
- **Seeds:** main runs use 42–46 (R1, 5 paired seeds) and 42–44 (R2, R3 R2-points, 3 seeds). Calibration uses seed 1000,
  smokes seed 900; these are disjoint from the main runs and never analysed with them.
- **Frozen workloads.** `experiments/v4/FROZEN_TRACES.json` holds a trace SHA-256 for every scenario × seed × arm. Each trace
  was built on the live tokenizer, exactly verified, budget-checked and coverage-checked (`scripts/freeze_v4.py`).
  `quotashift experiment` refuses before sending anything (exit 3) if a trace differs. All files are generated from one
  spec (`scripts/build_v4.py`; a test checks the files equal the spec).

## 3. R1: Feasible token-matched comparison

**Hypothesis H-R1.** At an offered load where every arm executes its whole budget, prefill-heavy or decode-heavy
competitor traffic changes victim user-facing TTFT relative to a token-matched short-request workload. Two-sided.

**Shapes (real tokens):** P = 1024 in / 32 out (prefill-heavy), D = 64 / 256 (decode-heavy), S = 64 / 64 (short).

### R1.1 Matching dimensions

| Dimension | P vs S, D vs S (`token_matched_fixed`) | A/A S vs S (`identical_workload`) |
|---|---|---|
| Victim traffic (ids, arrivals, lengths, SLO) | identical | identical |
| Competitor authorized tokens | matched (≤ 0.17% in every frozen pair; max one 128-token request) | identical |
| Competitor realized tokens | = authorized (ignore_eos), so matched | identical |
| Arrival law / window | N i.i.d. uniform over the full 120 s in both arms | identical |
| Serving config, gateway, seeds | identical | identical |
| **Varies** | request count, tokens per request, input/output composition | nothing (per-arm nonce only) |

### R1.2 Calibration and selection of the common load L* (separate traces)

- **Grid:** L ∈ {200, 300, 400} authorized competitor tokens/s. Probes `experiments/v4/calibration/v4_cal_{P,D,S}_L{L}`
  (9 probes). Each is an A/A pair at seed 1000, so it gives two replicate executions of the same workload.
- **Rule** (`scripts/v4_analysis.py select-load`, constants fixed in code): a probe is feasible iff every integrity gate
  passes, competitor completion is ≥ **0.98** in both replicates, victim censoring is **0**, and gateway saturation (scrapes
  at in-flight = 8) is ≤ **0.25**. **L\*** is the largest L such that L and every lower grid level are feasible for **all three**
  shapes. If none is feasible, stop and report: a lower level is not added without review.
- **Exclusion:** calibration results are never pooled with or reported as R1 results.
- **Expectation** (non-binding; from measured A9/v3.1 service times of ~1.45 s per 64/64 request, ~5.3 s per 256-output
  request and ~22 ms per output token at concurrency ≤ 8): D is the bottleneck, using about 3.4 / 5.1 / 6.8 of 8 slots at
  L = 200 / 300 / 400, plus about 1.3 for victims. So L\* = 200 or 300 is expected and L = 400 is expected to overload.

### R1.3 Blocks (run only at L\*; files are pre-registered for every L)

| Block | Attack | Control | Seeds | Runs |
|---|---|---|---|---|
| `v4_r1_aa_short_L*` | S × N_S | identical (A/A) | 5 | 10 |
| `v4_r1_prefill_vs_short_L*` | P × N_P | token-matched S over the full window | 5 | 10 |
| `v4_r1_decode_vs_short_L*` | D × N_D | token-matched S over the full window | 5 | 10 |

N per L: P 23/34/45, D 75/112/150, S 188/281/375 (L = 200/300/400). Token-matched S counts are 188–190 / 280 / 371–375.

### R1.4 Endpoints and classification

- **Primary (each comparison):** victim **user-facing TTFT P95** ratio (attack/control). Two-sided threshold **1.25×**,
  95% percentile-bootstrap CI over 5 paired seeds, CI classification as in v3 (supported / negative / inconclusive). Each
  comparison is its own pre-registered hypothesis, and no family-wise claim is made.
- **Precision gate:** if the A/A CI half-width at L\* is > 0.25, R1 is labelled exploratory (as S0).
- **Key secondary endpoints, reported with CIs and no claim:**
  - **Victim:** offered-load SLO success (attack vs control, absolute and ratio); gateway queue P95; backend TTFT P95; E2E P95.
  - **Cost:** absolute GPU dynamic energy (arm window, plus with tail); energy per 1k realized tokens (= per authorized token here); engine service seconds; GPU utilization; power.
- **Validity:** every ADR-Q17 gate in enforce mode (competitor completion ≥ 0.95, victim censoring ≤ 0.05, HTTP 400 and
  backend errors ≤ 1%, admission ≥ 0.95), plus `arrival_coverage` and `realized_output_equals_authorized`. Any failure makes
  the block **invalid** (exit 5).

## 4. R2: Request-granularity sweep

**Question.** With the total authorized competitor token budget fixed, how do request count and tokens per request move the
system between token-limited and request-limited operation, and where do gateway request-level constraints dominate
token throughput?

| Family | Composition | Budget per 120 s | Sizes s (tokens/request) → N requests |
|---|---|---|---|
| **R2-F** (fixed output) | input = s − 32, output = 32 | 120,000 (1,000 tok/s) | 96→1250, 128→938, 192→625, 256→469, 512→234, 1024→117, 2048→59, 3584→33 |
| **R2-B** (balanced) | input = output = s/2 | 48,000 (400 tok/s) | 64→750, 128→375, 256→188, 512→94, 1024→47, 2048→23 |

- **Control:** victims only (`benign_only`), as a per-seed baseline for victim metrics. 3 seeds per point.
- **Regime classification** (`feasibility_gates: classify`): a point is **feasible** iff competitor completion is ≥ 0.95 and
  victim censoring is ≤ 0.05 in every arm and seed; otherwise it is **overload**. Integrity gates still invalidate a point.
  **Feasible and overload points are reported in separate tables, and overload points are never used for cost comparisons.**
- **Limiting resource** (attack arm, mean over seeds):
  - **engine-bound** if vLLM has requests waiting in > 5% of scrapes;
  - else **request-bound (gateway)** if the gateway in-flight count is at cap in ≥ 50% of scrapes;
  - else **unconstrained**.
  The request-bound fraction (cap reached and gateway queue > 0 while vLLM has nothing waiting) is reported for every point.
- **Endpoints (descriptive, mean ± 95% bootstrap CI over seeds):**
  - **Gateway pressure:** in-flight saturation fraction, request-bound fraction, gateway queue depth.
  - **Victim:** victim gateway-queue P95; victim user-facing TTFT P95 (and ratio to the victims-only baseline); victim SLO success.
  - **Engine and GPU:** competitor completion rate; engine running/waiting; GPU utilization; competitor realized tokens/s; absolute energy.
  - **Boundary s\*** per family: the smallest size such that it and every larger size are feasible.
- **Expectation** (non-binding):
  - **R2-F:** per-request decode time for the 32 fixed output tokens (~0.7 s) dominates small requests, so slot-seconds per
    authorized token rise as s falls. Overload is expected at s ≤ 128 and feasibility from s ≈ 192, with gateway saturation
    and no vLLM queue in the overload region (request-bound).
  - **R2-B:** slot-seconds per token are roughly size-independent, so feasibility is expected across sizes. Victim gateway
    waits are expected to grow with s, because of longer residual service of in-flight requests.

## 5. R3: Gateway versus direct-vLLM isolation

- **Workloads:** R1 `prefill_vs_short` and `decode_vs_short` at L\* (5 seeds), and R2-F s ∈ {96, 256, 1024} (overload /
  boundary / feasible; 3 seeds).
- **Gateway arm:** the R1/R2 runs themselves.
- **Direct arm:** `experiments/v4/r3/*_direct.yaml`. These are the same scenario apart from the id and salt (identical
  arrival times, request sizes, token counts and seeds; prompts differ only in the nonce and are frozen), run with
  `--path direct`, on the **same vLLM server start** as their gateway counterparts. A restart between the two makes the pair invalid.
- **Analysis** (`scripts/v4_analysis.py compare-paths`): per arm and seed, direct/gateway ratios with CIs, plus an additive decomposition
  of mean victim user-facing TTFT = gateway queue + backend TTFT. The change in backend TTFT between paths is reported as
  `backend_interference_change`.
- **Interpretation rule (pre-registered):** gateway queueing and admission differences are **gateway effects**, not GPU
  effects. Only backend TTFT, engine queue and engine/GPU counters are attributed to the engine. A direct-path difference in
  completion is reported as an admission difference and is never read as GPU interference. Direct mode lets vLLM batch beyond
  8 concurrent requests, so backend TTFT may rise while user-facing TTFT falls; both are reported.

## 6. Validity gates (fail closed; ADR-Q17 plus v4)

| Gate | Rule | R1 | R2 | R3 |
|---|---|---|---|---|
| backend errors / HTTP 400 | ≤ 1% of sent, per arm | fail | fail | fail |
| admission | ≥ 0.95 per class, per arm | fail | fail | fail |
| competitor completion | ≥ 0.95 per arm | fail | regime | fail on gateway R1 pairs; regime for R2 pairs |
| victim censoring | ≤ 0.05 per arm | fail | regime | as above |
| primary metric present | every seed | fail | fail | fail |
| tokenized context and planned = reported tokens | pre-run exact check on the live tokenizer; post-run per request | fail | fail | fail |
| **frozen trace** | trace hash = `FROZEN_TRACES.json` | refuse (exit 3) | refuse | refuse |
| **arrival coverage** | first competitor arrival ≤ 0.25 T and last ≥ 0.75 T, every arm | fail | fail | fail |
| **realized output = authorized** | ignore_eos honoured per completed request | fail | fail | fail |
| provenance | clean git SHA, one server start, vLLM version, model-revision status | fail | fail | fail |
| report labels | metric-derived labels | fail | fail | fail |

## 7. Phase 2 validation status (done before any v4 GPU run)

| Step | Status |
|---|---|
| 1. Real Qwen token counts | **Done** 2026-11-21 23:23–23:29 EST on the live `/tokenize` (no generation; 167,652 calls). Every request of all 278 arm traces (45 scenarios, 83,826 requests) was calibrated and verified exactly; max context ≤ 4096. Details in `FROZEN_TRACES.json` (`tokenizer`, `process_start_time_seconds` 1795268683.89) |
| 2. Freeze workloads and seeds | **Done**: `FROZEN_TRACES.json`, enforced by `quotashift experiment`; a second independent freeze reproduced all 270 earlier hashes (deterministic) |
| 3. Matching dimensions | **Documented** in §3.1 and in `CONTROL_DIMENSIONS["token_matched_fixed"]` |
| 4. Feasible ranges via separate calibration traces | **Traces and rule ready** (§3.2), and an expectation from existing measurements is given. The calibration probes themselves are short GPU runs and need approval (§9) |
| 5. Validity gates and primary endpoints | **Defined** in §3.4, §4, §5 and §6 (`evaluation/validity.py`, `scripts/v4_analysis.py`) |
| 6. Automated tests and CI | **Done**: `tests/unit/test_v4_protocol.py` (spec equality, schema fail-closed, exact counts, full-window control vs historical front-loading, frozen-trace refusal, new gates, mock end-to-end R1/R2/R3 analysis), plus the full suite, ruff and mypy |
| 7. Model-weight revision on the GPU host | **Not verifiable from this machine**: `/server_info` reports `revision=None` and the runner has no host access. The owner runs §8 |

## 8. For the owner: record on the GPU host (read-only)

```bash
ls ~/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/      # loaded snapshot hash(es)
cat ~/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/refs/main
ps -o args= -p "$(pgrep -f 'vllm serve' | head -1)"                          # launch flags (max_num_seqs, ...)
```

Put the snapshot hash in `configs/targets/selfhost.yaml: model_revision`; it then appears in every run's provenance as the
documented revision. Record `max_num_seqs` and `max_num_batched_tokens` in `docs/SELFHOST.md`.

## 9. Expected run counts and GPU time budget (owner approval needed per stage)

Per-arm wall time is estimated from v3.1: 154 s for a 120 s arm, which includes idle settle, the post-arm tail and drain.
Overload arms and long outputs add up to about 60 s of drain or queue timeout.

| Stage | Blocks | Arms | Est. GPU wall time |
|---|---|---|---|
| S. Smokes (`experiments/v4/smoke/`, 40 s, seed 900) | 4 (R1, R2-F s96, R2-B s2048, R3 direct s96) | 8 | ≈ 12 min |
| C. Calibration (R1.2) | 9 | 18 | ≈ 47 min |
| R1 at L\* | 3 | 30 | ≈ 77 min |
| R2-F | 8 | 48 | ≈ 130 min |
| R2-B | 6 | 36 | ≈ 97 min |
| R3 direct arms | 5 (2 R1 + 3 R2-F) | 38 | ≈ 100 min |
| **Total** | **35** | **178** | **≈ 7.7 h** (plus about 1–3 min of pre-run tokenization per block) |

**Order and stop rules:**
1. **S → C.** All four smokes must pass every integrity gate. Calibration then selects L\*, and I stop to report L\* for review.
2. **R1 → R2-F → R2-B → R3.** R3 direct runs immediately follow their gateway counterparts on the same server start.
3. **Stop on failure.** Any integrity-gate failure or a server restart stops the stage with no retry; a repeat needs a new salt,
   which means a new frozen entry.

Each stage writes to `reports/v4/<stage>/`, and every block prints elapsed against expected time.

## 10. Known limitations and risks

- **Concurrency regime.** The 8-slot cap is the studied constraint. Results describe this gateway configuration and do not
  generalize to other caps without new runs.
- **Engine limits.** vLLM `max_num_seqs` and `max_num_batched_tokens` are unknown until the owner records them (§8). They
  matter for R3 direct.
- **Board power** is engine-global and includes victims; sampling is about 0.65 s. Energy per realized token at overload
  points mixes in queue-drain time, so it is reported for feasible points only.
- **R2 uses 3 seeds** per point and is descriptive, so no CI classification is claimed for R2 ratios.
- **Single model and GPU** (RTX 3090, Qwen2.5-7B, float16). The fixed request tag costs 16–20 tokens, which is part of every
  request's real token count.
