# Protocol X1: independent cross-model and cross-GPU validation (DRAFT, not frozen, not run)

**Status:** design draft for owner review, 2026-11-24.
- Nothing here is approved, frozen or executed.
- No hardware has been provisioned and no cost has been incurred.
- Every GPU, cloud or `terraform apply` step stays behind `scripts/aws_ops.sh` and needs separate owner approval.
- No prices, instance types, AMI IDs, model revisions or image digests are asserted here. Each must be looked up and recorded at P1 time.

## 1. Purpose

Protocol v5 established four results on **one** platform (Qwen2.5-7B-Instruct, RTX 3090, vLLM 0.17.1, fixed FCFS
gateway; `docs/RESULTS_V4_V5.md`):

| Claim | v5 evidence |
|---|---|
| **K1** Under equal token budgets, a decode-heavy competitor amplifies victim TTFT at a binding FCFS cap (C = 8) | H1: 1.565× at L = 200; 18.1× at L = 400, flagged "threshold not above noise" |
| **K2** The amplification disappears when the cap stops binding (C = 32, or no gateway) | H2b: 0.993; direct path: 0.997 and 0.998 |
| **K3** The harm is gateway admission queueing, not engine contention | backend TTFT flat; engine queue ≈ 0; H5 ρ = 0.998 |
| **K4** A FCFS replay of measured hold times predicts victim queueing at an unseen cap | H3: 18/18 validated scores; the L = 400 error direction was wrong |

X1 asks whether **K1–K4 hold on a different model and on a different GPU**. It is small on purpose:
- It tests transfer of the mechanism, not effect sizes. Absolute ratios are expected to differ between platforms.
- It uses **new seeds and newly generated traces**, so it is independent of v4 and v5 data.
- It remains attack-side only: there is no defense and no scheduler variation.

## 2. Platforms: a 2 × 2 crossing with one anchor

| | GPU G0: RTX 3090 (the v5 host) | GPU G1: different architecture and memory class |
|---|---|---|
| **Model M0:** Qwen2.5-7B-Instruct | **anchor** (v5 platform, *re-run with new seeds*) | P2: cross-GPU |
| **Model M1:** different family, similar size | P1: cross-model | P3: cross-both |

**M1 requirements:**
- an open-weights, instruction-tuned model of about 7–8B parameters from a different model family;
- different tokenizer and architecture details;
- fits G0 in fp16 with `max_model_len` 4096.

The candidate list, licence check and pinned revision are a P0 decision, to be looked up and recorded. Tokenizer-exact
traces are regenerated per model, as in v5 P2.

**G1 requirements:**
- a GPU of a different generation or memory size from the RTX 3090;
- available either in the owned isolated VPC (`docs/TERRAFORM_PROPOSAL.md`) or as a second owned host.

Instance type, price, AMI and driver are looked up at P1 and approved under `docs/aws_cost_controls.md`.

**Held fixed on every platform:**
- vLLM 0.17.1, unless the G1 driver stack forces a change, in which case the version becomes a recorded platform attribute;
- serving flags (`max_model_len` 4096, default scheduler, prefix caching as in v5);
- the gateway code and FCFS policy, the gate set, the export tool and the analysis code.

**Why the anchor is re-run.** Re-running the anchor with new seeds separates platform effects from seed or trace luck,
and gives a within-X1 baseline.

## 3. Load normalisation (the key design choice)

Token rates such as L = 200 tok/s do not transfer: a different GPU or model changes service times and therefore slot
occupancy. X1 sets load **per platform** by its offered slot demand at C = 8, rather than by token rate. The rule is
fixed before any X1 run:

1. **Calibration stage (separate seeds 7000–7002, never analysed).** For each platform, run the *control* arm (short
   64/64 competitor) at C = 8 on a grid of token rates. Measure the control slot demand,
   ρ_ctl = Σ holds / (8 × 120 s). This is the v5 post-hoc quantity, now promoted to a preregistered calibration
   variable.
2. **Choose two operating points per platform:**
   - **"low":** the rate whose ρ_ctl is closest to **0.43**, matching v5 L = 200;
   - **"high":** the rate whose ρ_ctl is closest to **0.72**, matching v5 L = 400.
   
   Ties go to the lower rate. The chosen rates are frozen before the main stage.
3. **Feasibility check.** If no grid rate reaches ρ_ctl ≥ 0.40 with a control-arm victim SLO ≥ 0.95, that platform's
   "low" point is reported as infeasible. It is not substituted.

## 4. Cells per platform (5 blocks × 10 seeds, seeds 8000–8009)

| Block | Comparison | Load | Cap | Tests |
|---|---|---|---|---|
| X-a | D vs S | low | C = 8 | K1 (primary) |
| X-b | D vs S | low | C = 32 | K2 |
| X-c | D vs S | low | direct | K2 / K3 |
| X-d | A/A-ind | low | C = 8 | noise floor for X-a |
| X-e | D vs S | high | C = 8 | K1 at depth, K4 extrapolation (descriptive) |
| X-f | A/A-ind | high | C = 8 | noise floor for X-e (the v5 gap) |

That is 6 blocks per platform, and 24 blocks in all. At v5's measured pace of about 50 min per 10-seed block, that is
roughly 20 h of GPU time plus calibration. G1 cost is unknown until P1 lookup.

**Leaner fallback**, if the owner wants it smaller: drop X-c and X-f on P1–P3, and keep them on the anchor only.

**P vs S is deliberately omitted.** H6 settled it as equivalent at v5. If a reviewer wants the negative control
carried across platforms, add one P vs S low C = 8 block per platform.

## 5. Hypotheses (preregistered in the frozen X1 protocol; draft wording)

Notation: ℓ is the per-seed log ratio of victim mean user-facing TTFT, attack/control. The cell estimate is the
geometric mean with a 95% t CI, as in v5.

| ID | Claim | Test | Family |
|---|---|---|---|
| **X1-H1** | On each platform p, D vs S at (low, C = 8) exceeds 1.25 | one-sided t of mean ℓ > log 1.25, per platform | **F-X1**: Holm across the 4 platforms (fixed family; p = 1 if not evaluable) |
| **X1-H2** | On each platform, D vs S at (low, C = 32) is equivalent within [0.8, 1.25] | TOST per platform | **F-X2**: Holm across 4 |
| **X1-H3** | On each platform, D vs S on the direct path is equivalent within [0.8, 1.25] | TOST per platform | F-X2 (family of 8) |
| **X1-H4** | K3: at (low, C = 8), the attack-arm victim backend TTFT is within ±10% of control, **and** the engine queue is negligible by the v5 §5.2 rule | TOST on log backend-TTFT ratio with band [0.9, 1.1], plus the histogram rule | own criterion, per platform |
| **X1-H5** | K4: a FCFS replay calibrated **on that platform's own C = 8 low-load control runs** (calibration seeds only) predicts the (low, C = 32) and (high, C = 8) victim queue | v5 H3 cell and seed rules, unchanged; tolerances from that platform's calibration LOSO | own criterion; (high, C = 8) is labelled extrapolated and is descriptive |
| X1-D1 | Magnitude at (high, C = 8), and victim SLO collapse | descriptive (H7 style) | none |

**Generalisation verdict** (fixed in advance):
- **Mechanism generalises** iff X1-H1 is supported on ≥ 3 of the 4 platforms, X1-H2 is equivalent on ≥ 3 of 4, and X1-H4 holds on ≥ 3 of 4.
- **Platform-specific** if K1 holds only on the anchor.
- **Partially generalises** otherwise. The report names which platform failed and which claim failed there.

**Threshold-above-noise.** It is applied per block exactly as in v5. X-f gives the high-load C = 8 noise floor that v5
lacked a usable version of. If that floor still fails, X-e stays descriptive and is flagged, as at v5 L = 400.

**Expected error direction for X1-H5** (fixed in advance): no direction is predicted. The v5 lesson (§5.2 of the
results report) is that the low-load bias (under-prediction) did not hold in the saturated regime. X1 reports the sign
and magnitude per regime instead of asserting one.

## 6. Power (planning only)

- At v5 L = 200 C = 8, the per-seed SD of ℓ was 0.33. Power of a one-sided t test against log 1.25 at α = 0.05 (noncentral t):

  | True geo-mean | n = 10 | n = 16 |
  |---|---|---|
  | 1.5 | 0.49 | 0.68 |
  | 1.565 (the v5 estimate) | 0.63 | 0.83 |
  | 1.8 | 0.94 | 0.99 |

  The low power at n = 10 is the honest price of a "small" protocol. Holm across platforms lowers per-platform power further.
- **Option A:** keep n = 10 and accept that X1-H1 can fail on a platform through low power. Such a failure is reported as "not supported", never as evidence that the mechanism is absent.
- **Option B:** n = 16 on X-a and X-d only. This adds about 20% GPU time (2 of 6 blocks × 1.6).
- Recommendation: B for X-a and X-d, n = 10 elsewhere. The owner decides.

## 7. Gates, governance and artifacts (reused from v5 unchanged unless noted)

- **Stages, each separately approved:**
  - P0: model and GPU selection, recorded with lookups.
  - P1: read-only host verification per platform, using the existing collector. Any `max_num_seqs` or snapshot evidence below `verified_direct` needs explicit owner acceptance, as in v5.
  - Freeze commit 1: protocol, schedules, pins.
  - P2: tokenizer-exact trace freeze per model.
  - Freeze commit 2.
  - Calibration.
  - Freeze commit 3: chosen rates and per-platform FCFS predictions, written before any main-stage run.
  - Smoke, then the main stage per platform.
- **Gates:** every v5 gate, including cap_configured, occupancy reconstruction, timestamp alignment, server identity per block, budget, and fail-closed private-endpoint checks.
- **Analysis:** `scripts/x1_analysis.py`. It reuses the v5 pure rules by import, without modification, adds the platform dimension, and is frozen with commit 1.
- **Export:** sanitized per platform with the existing tool and the same salt policy (a new salt per platform host is acceptable; record it). The JSON output filename must match its docstring; this fixes a v5 nit.
- **Isolation:** owned and private only. Cloud hosts stay in the isolated VPC with endpoints under `*.quotashift.internal`. No third-party APIs.

## 8. What X1 cannot settle

- **Other admission policies.** Fair-share, token-aware or per-tenant quotas are out of scope by charter.
- **Per-request engine queueing.** It remains unobservable unless the pinned vLLM version exposes per-request scheduler timestamps. P0 checks this and records the answer; if they are absent, the engine-global limitation carries over.
- **Real-traffic realism.** Traces stay synthetic and benign.
- **Larger models** (≥ 30B) and multi-GPU tensor parallelism.

## 9. Owner decisions requested

1. Choose M1 and G1, or a candidate shortlist for lookup.
2. Full design (24 blocks) or the leaner fallback.
3. n = 10 everywhere, or n = 16 on X-a and X-d.
4. Whether P vs S is carried across platforms.
5. Whether to approve P0 lookups, which are read-only and cost nothing. Everything after P0 needs its own approval.
