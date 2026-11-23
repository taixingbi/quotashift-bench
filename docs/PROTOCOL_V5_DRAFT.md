# Protocol v5 — gateway concurrency cap × request shape (DRAFT for pre-registration review)

**Status:** DRAFT, written 2026-11-22. **Not frozen, not approved, nothing run.**
- **What does not change:** Protocol v4 (`docs/PROTOCOL_V4.md`) and its results.
- **When it freezes:** v5 freezes only after owner review, at the commit that also adds its YAMLs and a frozen trace
  manifest, and before any v5 GPU run.
- **Governance:** ADR-Q19 (proposed), in `docs/DECISIONS.md`.

## 0. Motivation (from v4 and the v4 post-hoc exploratory analysis)

| v4 observation | v5 response |
|---|---|
| R1 decode vs short was 4.36× through the 8-slot FCFS gateway and 0.996× on direct vLLM (R3) | Vary the gateway cap (8, 16, 32) as a pre-registered blocking factor, keep a direct-vLLM reference, and test whether the amplification shrinks as the cap grows |
| Post-hoc: a FCFS replay of measured arrival and hold times reproduces victim queueing exactly. Victims queue only during transient all-slots-busy episodes. Decode-heavy work uses 1.51× the slot-seconds of token-matched short work | Pre-register slot-time demand and transient saturation as explanatory variables, computed by a frozen analysis script |
| Post-hoc: the P95 ratio is a threshold statistic (about the 6th-largest of about 110 victims). It splits seeds into about 1.0–1.8 vs about 6.3 (log SD 0.87); the mean ratio is stabler (log SD 0.34) | Primary endpoint becomes the **mean** user-facing TTFT ratio. P95 and tail mass are secondary; there are 10 seeds |
| The R2 "regime" rule used only execution criteria, so it called s96 (6% victim SLO success) "feasible" | Separate **execution feasibility** from **victim-SLO feasibility** and stratify by both |
| A/A pairs replayed the same trace, so the noise floor excluded variation between traces | A/A arms use **independently sampled** competitor traces |
| Engine queue time was unavailable in v4 | Capture the vLLM `request_queue_time_seconds` histogram (plus prefill, decode and TTFT) as per-arm deltas |

## 1. Fixed serving configuration (identical across every cell and its control)

- vLLM 0.17.1, Qwen2.5-7B-Instruct, RTX 3090, max_model_len 4096, prefix caching on, chunked prefill on,
  gpu_memory_utilization 0.8.
- One vLLM server start per stage (gate). The gateway is FCFS with a 60 s queue timeout.
- Real-token prompts (`prompt_token_unit: tokenizer`) and `ignore_eos: true`.
- Victims are exactly as in v4: 3 tenants at 0.3 rps each, 64-token output, user-facing TTFT SLO 2 s, E2E SLO 30 s.
- **The only serving parameter that varies** is the gateway cap C (`safety.max_global_inflight`). It is a between-block
  factor, identical in each block's attack and control arms.
- The per-tenant token ledger quota is `C × max per-request tokens`, so it never binds. This is recorded in every
  manifest.

## 2. Design

| Factor | Levels |
|---|---|
| Gateway cap C | 8, 16, 32; plus **direct vLLM** (no gateway) as a reference path |
| Comparison | **D vs S**: decode 64/256 vs short 64/64, token-matched. **P vs S**: prefill 1024/32 vs short, token-matched. **A/A-ind**: short vs short with independent competitor traces |
| Load L (authorized competitor tok/s) | **200** (v4 L\*), in Stage A. **400**, in Stage B (D vs S and A/A-ind only); at C = 8 in v4 calibration it was execution-feasible but over the saturation limit |
| Seeds | **10 per cell**, new disjoint range 5000–5009. Each seed samples the victim trace and both competitor traces independently. The same seed's traces are replayed at every C and on the direct path (crossed design), so cap effects are paired within seed |

- **Arrivals** follow the v4 mechanisms: fixed-count, i.i.d. uniform over a 120 s window; a `token_matched_fixed`
  control; and the arrival-coverage gate.
- **Victim trace** is identical between the attack and control arms of a seed (paired), as in v4.

## 3. Hypotheses (two-sided unless stated)

- **H1 (replication).** At C = 8, L = 200, D vs S gives a mean user-facing TTFT ratio outside [0.8, 1.25].
  Predicted: > 1.25.
- **H2 (cap dose-response).** For D vs S at L = 200, the per-seed log ratio decreases with log2(C), with a negative
  slope. At C = 32 the ratio is inside the equivalence band [0.8, 1.25], with a 90% CI inside the band (TOST).
- **H3 (FCFS model prediction).** Pre-registered before any v5 run, from the frozen v4 FCFS replay estimates:
  - victim gateway-queue P95 at C ≥ 16 and L = 200 is ≤ 50 ms for D, S and P;
  - departures are reported as evidence against the cap-invariant hold-time assumption.
- **H4 (relocation).** As C rises, D-attack victims' backend TTFT rises relative to C = 8 (ratio > 1), and their gateway
  queue falls. The engine queue (vLLM `request_queue_time_seconds` delta) stays at zero (P95 ≤ 10 ms) at C ≤ 32,
  because max_num_seqs ≥ 64 (§5 gate).
- **H5 (explanatory).** Across gateway runs, victim mean gateway queue is positively and monotonically associated
  with (a) the time fraction at C/C and (b) the fraction of victims arriving during saturation. Pre-registered:
  Spearman ρ ≥ 0.6 for each. v4 exploratory values are 0.88 and 0.92; they are **not** pooled.
- **H6 (negative control on shape).** P vs S is inside [0.8, 1.25] at every C (TOST).
- **H7 (feasibility).** At L = 400, D vs S is execution-feasible and victim-SLO-feasible (§4) at C ≥ 16, and not
  victim-SLO-feasible at C = 8.

## 4. Feasibility: two separate criteria

- **Execution feasibility (E).** Every integrity gate passes; competitor completion ≥ 0.95 and victim censoring ≤ 0.05
  in **both** arms.
- **Victim-SLO feasibility (V).** The control arm's victim offered-load SLO success is ≥ 0.95, i.e. the baseline
  operating point is acceptable to victims.
- **Strata:**
  - Comparisons are primary only in **E ∧ V**.
  - **E ∧ ¬V** is reported separately as "victim-overloaded baseline" and is not pooled.
  - **¬E** is invalid.
- **Attack-arm SLO success is an outcome, not a criterion.**

## 5. Validity gates (fail-closed; in addition to every v4 gate)

All v4 gates apply: backend and HTTP-400 errors ≤ 1%, admission ≥ 0.95, primary present, tokenized context, planned
= reported tokens, provenance clean, censoring, arrival coverage, realized output = authorized, frozen traces, verified
cache reset, no unrelated traffic.

| New gate | Rule | Kind |
|---|---|---|
| `cap_configured` | config cap == the cell's C; observed max gateway in-flight ≤ C | fail |
| `engine_headroom` | verified `max_num_seqs ≥ 64` and `max_num_batched_tokens` recorded **from the host's launch command** | fail (pre-stage) |
| `model_revision_verified` | snapshot hash read on the host and matching the target profile | fail (pre-stage); proceeding without it needs a written owner waiver |
| `server_identity` | one `process_start_time_seconds` for the whole stage | fail |
| `engine_histograms_present` | per-arm deltas of the vLLM queue, prefill, decode and TTFT histograms captured | fail for H4, otherwise flag |
| `occupancy_reconstruction` | after the 0.15 s scrape-lag correction, rebuilt in-flight agrees exactly with sampled `gw_inflight` ≥ 90% of the time | flag |
| `no_preemption` | `num_preemptions_total` delta = 0 | flag |
| `independent_aa` | A/A competitor traces have different SHA-256 | fail |

## 6. Endpoints and statistical analysis (frozen script `scripts/v5_analysis.py`, to be written before the freeze)

- **Primary (every comparison × C).** Victim **mean user-facing TTFT** ratio, attack/control, per seed.
  - **Estimand:** the mean of the per-seed log ratios.
  - **Interval:** 95% t interval, n = 10, plus a BCa bootstrap as a sensitivity check.
  - **Threshold:** 1.25, two-sided. It is valid only if it exceeds 2× the A/A-ind half-width at the same C and L;
    otherwise the cell is flagged "threshold not above noise".
- **Multiplicity.** Holm across the 3 gateway caps within each comparison family (H1/H2, H6). H3–H5 are reported with
  their own pre-specified criteria. Everything else is descriptive.
- **Cap trend (H2).** Linear mixed model: log ratio ~ log2(C) + (1 | seed). Slope with 95% CI, plus an exact paired
  permutation test of the slope.
- **Secondary, reported for every cell:**
  - victim P95 user-facing TTFT ratio (continuity with v4);
  - tail mass: difference in the fraction of victims with user TTFT > 500 ms and > 2 s;
  - victim SLO success;
  - gateway-queue mean and P95;
  - backend TTFT mean and P95;
  - engine queue P95 from the histogram;
  - TPOT;
  - competitor slot-seconds per 1k tokens, time fraction at C/C, saturation episode count, mean and max, and victims
    arriving during saturation;
  - GPU dynamic energy per realized token.
- **Reporting rules.**
  - **No seed exclusion.** All per-seed values are reported.
  - **No interim looks.** Primary endpoints are not inspected until a stage is complete; only gates are monitored
    during runs. This closes the v4 deviation.
- **Power (planning, from v4).**

  | Comparison | Per-seed log SD of mean ratio in v4 | SE at n = 10 | What it can detect |
  |---|---|---|---|
  | D vs S | 0.34 | 0.11 | an effect of 1.25× (log 0.22) at about 50% power if the effect were exactly at threshold. The v4 effect (log 0.54) has > 99% power |
  | P vs S | 0.14 | 0.044 | equivalence at ±log 1.25 is well powered |
  | A/A | 0.19 | 0.059 | — |

## 7. Run counts and GPU time

Estimates use v4's measured 2.6 min of wall time per 120 s arm, which includes settle, drain and cache reset, plus
about 2 min of tokenization per block.

| Stage | Content | Blocks | Arms | Estimated GPU time |
|---|---|---|---|---|
| P. Pre-stage (no GPU load) | host verification of revision and flags; frozen-trace build on the live tokenizer | — | — | about 0.5 h (tokenize only) |
| S. Smokes (40 s, 1 seed) | D vs S at C = 16 and 32; A/A-ind at C = 8; direct D vs S | 4 | 8 | about 0.3 h |
| A. Core, L = 200 | {A/A-ind, D vs S, P vs S} × {8, 16, 32} + the same 3 on direct | 12 | 240 | **about 10.4 h** |
| B. Higher load, L = 400 | {A/A-ind, D vs S} × {8, 16, 32} + D vs S direct | 7 | 140 | about 6.1 h |
| **Total** | | **23** | **388** | **about 17.3 h** (A + B; about 10.7 h if only S + A are approved) |

## 8. Stopping rules (explicit)

1. **Pre-stage.**
   - Without host verification of the model revision and launch flags, v5 does not start, unless the owner gives a
     written waiver.
   - If `max_num_seqs` < 64, the C = 32 cells are dropped before the freeze, never after.
2. **Integrity failure.**
   - Any fail-severity gate failure stops the stage immediately.
   - No rerun reuses an isolation salt.
   - A rerun of a failed block needs a documented reason and a new salt, and the failed block is kept as invalid.
3. **Server restart.** A server restart mid-stage stops the stage. Resuming starts a new server-start series, and
   whole blocks are rerun with new salts.
4. **Fixed sample size.** n = 10 per cell; no seeds are added or dropped after any look at outcomes.
5. **Noise floor.** If A/A-ind at some C and L fails victim-SLO feasibility (control SLO success < 0.95), that (C, L)
   level is reported as ¬V and excluded from the primary stratum. The run still completes.
6. **Budget.** If cumulative wall time exceeds 1.3× the stage estimate, stop and report.
7. **Stage order.** Stage B runs only if Stage A completes with every block valid, and only with separate owner
   approval.
8. **Interpretation boundary.** Differences between caps or paths are reported as admission or batching effects of
   the execution path, never as isolated gateway software overhead and never as GPU-only effects.

## 9. Implementation prerequisites (none implemented yet; each needs tests before the freeze)

- **`independent_replicate` control:** the A/A control competitor trace comes from a seed stream independent of the
  attack arm's.
- **Seed-shared traces across caps:** the same frozen traces at C = 8, 16 and 32, and direct; the manifest keys traces
  by seed, not by cell.
- **Engine histograms:** capture deltas of the vLLM request queue, prefill, decode and TTFT histograms per arm.
- **Scrape-lag correction:** apply the 0.15 s correction for the occupancy check.
- **Port the slot-time metrics** from `scripts/v4_posthoc_slot_time.py` into the frozen `scripts/v5_analysis.py` as
  pre-registered secondaries.
- **Two-criterion classifier:** victim-SLO feasibility (V) alongside execution feasibility (E).
- **`scripts/build_v5.py` / `freeze_v5.py`:** generated YAMLs and a frozen manifest, with v4-style spec-equality tests.
- **Raw-data handling:** release-artifact export with SHA-256 manifests and sanitization (`docs/RAW_DATA_AUDIT.md`)
  for v5 raw data.

## 10. Scope boundary

This remains attack-side characterization:
- no defenses, RL or scheduler contributions;
- private owned target only;
- synthetic tenants and prompts.

The cap is varied to characterize how a fixed, authorized token budget converts into victim harm under different
admission configurations. It is not tuned as a mitigation.
