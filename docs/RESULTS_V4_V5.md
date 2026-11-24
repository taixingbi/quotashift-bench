# QuotaShift: consolidated v4/v5 results

**Status:** draft for scientific review, 2026-11-24. This report reports frozen results; it does not re-decide them. Every
preregistered verdict below is copied from the frozen analysis outputs (`reports/v5/ANALYSIS_{A,B}.md`,
`reports/v5/analysis_{A,B}.json`) or from the v4 stage records (`experiments/PLAN.md`). Nothing was rerun and no frozen
code, threshold, prediction or seed was changed. Material produced for this report, after all stages finished, is
labelled **[post-hoc]**.

**Reproduce the post-hoc tables and figures:** `uv run python scripts/v5_consolidated.py` (read-only), which writes
`reports/v5/consolidated/`.

---

## 1. Setting and question

**Question.** On a shared LLM-serving deployment, do different request shapes and arrival patterns degrade a victim
tenant differently when every tenant has the same authorized token budget? We measure this from the attack side only:
no defense, scheduler or mitigation is proposed or evaluated.

**System under test** (identical for every v4 and v5 run):
- One vLLM 0.17.1 server, serving Qwen/Qwen2.5-7B-Instruct (snapshot `a09a354…`) on one RTX 3090.
  - Settings: fp16, `max_model_len` 4096, `max_num_batched_tokens` 2048, `max_num_seqs` 256.
  - The same server process (start time 1795268683.89) served every v4 and v5 stage.
  - These values come from the P1 host record, `experiments/v5/HOST_VERIFICATION.json`. Its evidence levels are given there; the snapshot is identified by exclusion and `max_num_seqs` is inferred from source defaults, both owner-accepted.
- An optional FCFS gateway with a global in-flight cap C sits in front of the server. The alternative is the direct path: clients talk to vLLM directly, with no cap.
- Tenants:
  - three victim tenants sending short interactive requests;
  - one competitor tenant, whose request *shape* is the experimental variable.

**Comparisons** (attack arm vs its control arm; the two arms are token-matched):

| Label | Attack arm (competitor shape, in/out tokens) | Control arm |
|---|---|---|
| D vs S | decode-heavy, 64/256 | token-matched short, 64/64 |
| P vs S | prefill-heavy, 1024/32 | token-matched short, 64/64 |
| A/A-ind | short | short, with an independent trace (noise floor) |

**Loads.** L = 200 and L = 400 authorized competitor tokens/s.

**Endpoint.** Per seed, ℓ = log(victim mean user-facing TTFT, attack) − log(same, control).
- The cell estimate is the **geometric mean of the per-seed ratios**, exp(mean ℓ), with a 95% t interval.
- v4 used the P95 ratio as its primary endpoint. v5 changed to the mean, because the post-hoc v4 audit showed the P95 ratio to be fragile (§5.1).

---

## 2. Validity of the data

| | v4 | v5 Stage A (L = 200) | v5 Stage B (L = 400) |
|---|---|---|---|
| Runs | R1 30 arms, R2 84, R3 38 (plus calibration) | 12 blocks, 240 arms | 7 blocks, 140 arms |
| Seeds per cell | 5 in R1/R3 (42–46); 3 in R2 (descriptive) | 10 (5000–5009) | 10 (5000–5009) |
| Gates | all passed | all passed; no flags; no reruns | all passed; no flags; no reruns |
| Server identity | one start time | one start time, checked before and after every block | same |
| Victim censoring | 0 | 0 | 0 |
| Competitor completion | 1.00 | 1.00 | 1.00 |
| Provenance | clean tree | clean tree at `167ecb0` | clean tree at `2418751` |

- **Strata.** Every v5 cell is in stratum E∧Vb: execution-feasible, with a feasible victim SLO at baseline.
- **Exports.** The v5 raw data is exported sanitized, with a checksummed manifest per stage (§8).
- **Gateway behaviour.** v5 added three checks:
  - the cap is configured correctly;
  - occupancy rebuilt from request timestamps matches the sampled gateway count: 1.000 in every arm;
  - the gateway and scraper timestamps align: lag 0.000 s.
  
  Together they confirm the gateway behaves as a global FCFS queue with exactly C slots.

---

## 3. Confirmatory findings (preregistered)

### 3.1 v4 (Protocol v4; primary endpoint: victim P95 user TTFT ratio; 5 seeds; FCFS gateway at C = 8)

| Test | Result | Verdict |
|---|---|---|
| R1 A/A short, L = 200 | 0.956 [0.848, 1.038] | negative (noise floor) |
| R1 decode vs short, L = 200 | **4.36 [2.24, 6.34]** | **supported** |
| R1 prefill vs short, L = 200 | 1.047 [0.878, 1.216] | negative |
| R3 direct path: decode vs short | 0.996 [0.958, 1.026] | negative |
| R3 direct path: prefill vs short | 1.151 [1.057, 1.254] | inconclusive |

**v4 conclusion.** At this serving configuration, shape-dependent victim harm came from admission queueing at the
8-slot gateway, not from GPU interference.
- In the decode cell the backend TTFT P95 ratio was 1.01, while the gateway queue P95 rose from 20 to 697 ms.
- On the direct path the backend TTFT P95 rose by only 8–80 ms.

### 3.2 v5 (Protocol v5; primary endpoint: geometric mean of per-seed mean-TTFT ratios; 10 seeds)

**Family F1 = {H1, H2a, H2b}**, Holm at α = 0.05. These hypotheses are defined at L = 200 only.

| Hypothesis | Estimate | Test | Verdict |
|---|---|---|---|
| **H1:** D vs S at C = 8 exceeds 1.25 | 1.565, 95% CI [1.236, 1.982]; 90% CI [1.293, 1.895] | one-sided t against log 1.25: p = 0.0298; Holm threshold at its step 0.05 | **supported** |
| **H2a:** the D vs S effect falls as C rises | × 0.796 per doubling of C [0.711, 0.892] | p_t 0.0007, p_perm 0.0020, p = 0.0020 | **supported** |
| **H2b:** D vs S at C = 32 is equivalent to 1 | 0.993, 90% CI [0.980, 1.006] | TOST p = 1.4 × 10⁻¹⁰; threshold above noise | **equivalent** |

- **H1 and its cell classification differ.** H1 is supported, but the cell-level classification of the same cell is
  **inconclusive**: the 95% CI lower bound (1.236) falls just below 1.25. Both are frozen rules and both are
  reported. The one-sided test at α = 0.05 corresponds to the 90% bound (1.293), which clears 1.25. The 95% bound
  does not.
- **Per-seed D vs S ratios at L = 200** (seeds 5000–5009):

  | C | Ratios |
  |---|---|
  | 8 | 1.568 1.452 1.676 1.251 1.356 **0.955** 3.089 1.205 1.758 2.179 |
  | 16 | 1.003 0.990 1.017 0.987 0.993 0.952 1.000 0.982 0.996 0.979 |
  | 32 | 0.986 0.990 1.019 1.018 0.995 0.955 1.029 0.982 0.973 0.982 |

**Family F2 = H6**, the shape negative control: P vs S is equivalent within [0.8, 1.25] at each C. Holm correction is
applied across the three caps.

| C | Geo-mean [95% CI] | TOST p | Verdict |
|---|---|---|---|
| 8 | 0.994 [0.924, 1.070] | 4.3 × 10⁻⁵ | **equivalent** |
| 16 | 1.048 [1.005, 1.092] | 2.5 × 10⁻⁶ | **equivalent** |
| 32 | 1.073 [1.039, 1.107] | 8.0 × 10⁻⁷ | **equivalent** |

**Hypotheses with their own frozen criteria:**

| Hypothesis | Verdict | Basis |
|---|---|---|
| **H3:** FCFS replay predicts victim gateway queueing | **supported** | All 18 *validated-envelope* (cell, arm) predictions at L = 200 pass in 10/10 seeds. The 12 L = 400 scores are extrapolated: under the frozen rule they are reported but **excluded from the verdict** (§4, §6) |
| **H4:** relocation, i.e. as C rises, victim delay moves from the gateway queue to the backend | **not supported** | (a) **fails**: backend TTFT at C = 32 vs C = 8 is 1.005 [0.986, 1.024], p = 0.28. (b) holds: queue reduction C8 − C32 = 57.7 ms [24.3, 91.0], p = max(0.0018, 0.0010). (c) holds: the engine queue is negligible in every D vs S arm |
| **H5:** consistency check, i.e. victim queueing tracks slot saturation | **supported** | Spearman ρ = 0.916 with the fraction of time at cap and 0.998 with the fraction of victims arriving during saturation; n = 300 gateway arms, both stages |

- **Why H4 fails.** The cap removes the queueing without moving it into the engine. At C = 32 the victims suffer no
  extra delay anywhere: their TTFT ratio is 0.993 and their backend TTFT is unchanged. This is an absence of
  relocation. It does not contradict the admission-queueing account, and the verdict stays **not supported** as
  preregistered.
- **Per-seed H4(b) queue reductions, C8 − C32 (ms):** 60.8, 37.7, 57.6, 36.3, 29.1, 5.8, 165.5, 17.2, 66.0, 100.6.

### 3.3 Replication across protocols

v4 R1 and v5 H1 test the same cell: D vs S, L = 200, C = 8. The seeds, the number of seeds and the endpoint differ.

| | v4 R1 | v5 H1 |
|---|---|---|
| Endpoint | P95 ratio | geo-mean of mean ratios |
| Seeds | 5 | 10 |
| Estimate | 4.36 [2.24, 6.34] | 1.565 [1.236, 1.982] |
| Verdict | supported | supported |

The effect replicates in direction and preregistered verdict. Its size is smaller in v5: the v4 post-hoc mean ratio was
1.80. The gap between 4.36 and 1.565 is mostly the change of endpoint, not a change of effect (§5.1). The direct path
is null in both protocols for D vs S: 0.996 in v4, 0.997 in v5.

---

## 4. Descriptive findings at L = 400 (Stage B)

No confirmatory family is defined at L = 400. Everything in this section is a preregistered **descriptive** outcome
(H7) or an **extrapolated** H3 score. None of it is a confirmatory test.

### 4.1 Cells

| Cell | Geo-mean [95% CI] | Classification | Threshold above noise |
|---|---|---|---|
| D vs S, C = 8 | **18.12 [12.51, 26.24]** | supported increase | **no** |
| D vs S, C = 16 | 1.031 [0.990, 1.074] | equivalent | yes |
| D vs S, C = 32 | 1.003 [0.989, 1.017] | equivalent | yes |
| D vs S, direct | 0.998 [0.982, 1.014] | equivalent | not evaluable (no L = 400 direct A/A cell) |
| A/A-ind, C = 8 | 0.968 [0.831, 1.126] | equivalent | — |
| A/A-ind, C = 16 / 32 | 1.008 / 1.010 | equivalent | — |

**Disclosure: L = 400, C = 8 fails the threshold-above-noise rule.**
- The rule (§6 of the protocol) counts the 1.25 threshold only if log 1.25 > 2 × the A/A-ind 95% half-width at the same (C, L).
- At L = 400, C = 8 the A/A per-seed ratios range from 0.718 to 1.358, so twice the half-width exceeds log 1.25 (0.223). The control arm alone already saturates the 8 slots 29% of the time.
- The D vs S classification at this cell therefore carries the preregistered flag "threshold not above noise", and it must be cited with that flag.
- The effect is very large next to that noise: the lowest per-seed ratio is 7.37. Even so, the flag does not lapse.
- **Per-seed D vs S ratios, L = 400, C = 8:** 27.98 19.72 29.33 7.37 18.39 16.47 19.17 38.93 8.52 16.61.

### 4.2 H7: what was expected and what was observed

| Pre-registered expectation | Observed |
|---|---|
| L = 400, C = 8: attack-arm victim SLO success falls sharply; 82% of victims predicted to have a gateway queue > 500 ms | SLO success 0.346 (per seed 0.09–0.69) vs control 0.997. Paired difference −0.651 [−0.789, −0.513]. 81.6% of victims had user TTFT > 500 ms and 65.4% > 2 s |
| C ≥ 16: no such collapse | SLO success 1.000 in every C ≥ 16 and direct arm |

### 4.3 SLO, censoring, queueing and engine contention: all 19 cells

Each value is the mean over 10 seeds, given as control / attack.
- *SLO* is the victim's offered-load SLO success rate.
- *GwQ* is the victim gateway queue.
- *Backend* is the victim backend TTFT.
- *At cap* is the fraction of time with k = C, measured against a reference cap on the direct path.
- *Demand* **[post-hoc]** is the offered slot-seconds divided by (C × 120 s). It is undefined on the direct path.

Victim censoring is 0 in every arm.

| Cell | SLO ctl | SLO atk (min) | User TTFT ms | GwQ mean ms | GwQ P95 ms | Backend ms | > 500 ms | At cap | Demand |
|---|---|---|---|---|---|---|---|---|---|
| D vs S L200 C8 | 1.000 | 0.998 (0.98) | 85 / 139 | 3.3 / 57.7 | 5 / 464 | 82.1 / 81.7 | 0.001 / 0.052 | 0.020 / 0.109 | 0.43 / 0.58 |
| D vs S L200 C16 | 1.000 | 1.000 | 83 / 82 | 0 / 0 | 0 / 0 | 82.5 / 81.7 | 0 / 0 | 0 / 0 | 0.22 / 0.29 |
| D vs S L200 C32 | 1.000 | 1.000 | 83 / 82 | 0 / 0 | 0 / 0 | 82.7 / 82.1 | 0 / 0 | 0 / 0 | 0.11 / 0.14 |
| D vs S L200 direct | 1.000 | 1.000 | 82 / 82 | 0 / 0 | 0 / 0 | 82.2 / 81.9 | 0 / 0 | ref. | — |
| **D vs S L400 C8** | 0.997 | **0.346 (0.09)** | 184 / 3698 | 99.2 / **3616.2** | 603 / 7167 | 85.0 / 81.9 | 0.085 / 0.816 | 0.288 / 0.861 | 0.72 / **1.00** |
| D vs S L400 C16 | 1.000 | 1.000 | 86 / 88 | 0 / 3.1 | 0 / 0 | 85.7 / 85.3 | 0 / 0.004 | 0 / 0.015 | 0.36 / 0.51 |
| D vs S L400 C32 | 1.000 | 1.000 | 86 / 86 | 0 / 0 | 0 / 0 | 86.1 / 86.4 | 0 / 0 | 0 / 0 | 0.18 / 0.26 |
| D vs S L400 direct | 1.000 | 1.000 | 86 / 86 | 0 / 0 | 0 / 0 | 85.8 / 85.6 | 0 / 0 | ref. | — |
| P vs S L200 C8 | 1.000 | 1.000 | 87 / 86 | 3.7 / 0 | 4 / 0 | 83.4 / 86.5 | 0.002 / 0 | 0.021 / 0.001 | 0.44 / 0.19 |
| P vs S L200 C16 | 1.000 | 1.000 | 82 / 86 | 0 / 0 | 0 / 0 | 82.5 / 86.4 | 0 / 0.001 | 0 / 0 | 0.22 / 0.09 |
| P vs S L200 C32 | 1.000 | 1.000 | 83 / 89 | 0 / 0 | 0 / 0 | 83.1 / 89.1 | 0 / 0 | 0 / 0 | 0.11 / 0.05 |
| P vs S L200 direct | 1.000 | 1.000 | 83 / 89 | 0 / 0 | 0 / 0 | 83.3 / 88.6 | 0 / 0.001 | ref. | — |
| A/A L200 C8 | 1.000 | 1.000 | 87 / 92 | 3.5 / 8.7 | 0 / 58 | 83.1 / 83.5 | 0.002 / 0.007 | 0.025 / 0.032 | 0.43 / 0.43 |
| A/A L200 C16, C32, direct | 1.000 | 1.000 | 83–84 | 0 / 0 | 0 / 0 | 83–84 | 0 / 0 | ≤ 0.03 | 0.22, 0.11 |
| A/A L400 C8 | 1.000 | 1.000 | 183 / 182 | 98.8 / 96.6 | 553 / 570 | 84.4 / 85.4 | 0.098 / 0.089 | 0.289 / 0.285 | 0.72 / 0.72 |
| A/A L400 C16, C32 | 1.000 | 1.000 | 85–88 | 0 / 0 | 0 / 0 | 85–88 | 0 / 0 | ≤ 0.001 | 0.36, 0.18 |

**Engine contention.**
- The vLLM engine queue (an engine-global histogram) averages at most 0.013 ms per request in any arm, and every observation in every arm lands in the ≤ 0.3 s bucket.
- Backend TTFT cell means are 82–89 ms throughout.
- The one systematic backend shift is **prefill**: P vs S attack arms run 3–6 ms (about 4–7%) slower in backend TTFT than their controls at every C and on the direct path. This is the source of H6's small positive ratios at C ≥ 16. It matches the v4 R3 direct-path prefill result (1.151, inconclusive).
- Decode-heavy load produces **no** measurable backend contention at either load.

---

## 5. Post-hoc analyses (exploratory, not preregistered)

### 5.1 v4 slot-time audit (2026-11-22; `reports/v4/posthoc_slot_time/SLOT_TIME_ANALYSIS.md`)
- **P95 fragility.** With about 100–115 victims per run, P95 is about the 6th-largest value. The v4 R1 decode per-seed P95 ratios were bimodal (about 1.0–1.8 vs about 6.3).
- **The mean ratio is more stable.** The mean ratio was 1.80 (1.08–2.46), with a log SD across seeds of 0.34 against 0.87 for the P95 ratio. This motivated the v5 endpoint.
- **The gateway is exactly FCFS.** A FCFS replay at C = 8 reproduced the measured victim queueing in all 114 gateway runs (Pearson r = 1.00 on log1p of the mean).
- **Erratum, kept with the original wording.** The original note claimed occupancy-reconstruction agreement of "91–99.5%" at a +0.15 s shift. That range does not reproduce: the real range is 0.77–0.995. v5 fixed the cause by recording `t_gw_rel_s`, and achieves 1.000.

### 5.2 FCFS prediction error, zero vs nonzero queueing [post-hoc]
Source: `reports/v5/consolidated/fcfs_prediction_error*.{csv,json}`; Fig. 5.

The frozen predictions (`experiments/v5/FCFS_PREDICTIONS.json`) were made before any v5 run. They replay the exact v5
arrival schedule through a single global FCFS queue with C slots, drawing service times from v4 C = 8 hold times.

**Case split (post-hoc).** A (cell, arm) is a *zero-queue* case when its frozen predicted cell mean is below 1 ms,
which is the "queueing vanishes" content of H3. Otherwise it is *nonzero*. Error is defined as observed − predicted:
a positive error means under-prediction.

| Envelope | Case | (cell, arm) pairs | Seed scores | Absolute error | Relative error | Direction |
|---|---|---|---|---|---|---|
| validated (L = 200) | zero | 13 | 130 | 0 ms exactly, all seeds (max observed 0.0 ms) | — | exact |
| validated (L = 200) | nonzero | 5 | 50 | cell MAE 0.53 ms (max 0.84); seed MAE 0.70 ms (max 3.3) | cell median abs 9.6% (1.5–12.8%); seed median abs 19.6% | **all 5 cells under-predicted** (+0.28 to +0.84 ms); 62% of seeds obs > pred |
| extrapolated (L = 400) | zero | 7 | 70 | ≤ 0.004 ms (max observed 0.0 ms) | — | exact |
| extrapolated (L = 400) | nonzero | 5 | 50 | cell MAE 57.0 ms (max 278.3); seed MAE 57.3 ms (max 480.5) | cell median abs 3.2%; seed median abs 3.7% | **4 of 5 cells over-predicted**; 66% of seeds obs < pred |

**Nonzero cases:**

| (cell, arm) | Envelope | Predicted ms | Observed ms | Absolute error | Relative error |
|---|---|---|---|---|---|
| D vs S L200 C8 attack | validated | 56.82 | 57.65 | +0.83 | +1.5% |
| D vs S L200 C8 control | validated | 2.97 | 3.26 | +0.28 | +9.6% |
| P vs S L200 C8 control | validated | 3.40 | 3.70 | +0.30 | +8.7% |
| A/A L200 C8 attack | validated | 7.89 | 8.73 | +0.84 | +10.6% |
| A/A L200 C8 control | validated | 3.06 | 3.45 | +0.39 | +12.8% |
| **D vs S L400 C8 attack** | extrapolated | **3894.6** | **3616.2** | **−278.3** | **−7.1%** |
| D vs S L400 C8 control | extrapolated | 99.75 | 99.24 | −0.51 | −0.5% |
| A/A L400 C8 attack | extrapolated | 99.82 | 96.63 | −3.19 | −3.2% |
| A/A L400 C8 control | extrapolated | 100.77 | 98.83 | −1.94 | −1.9% |
| D vs S L400 C16 attack | extrapolated | 2.19 | 3.12 | +0.94 | +42.9% (inside the 5 ms absolute tolerance) |

**The error direction was predicted wrongly at L = 400, C = 8.**
- The frozen protocol (§3.5) and the C = 8 leave-one-seed-out validation (bias −2.2 ms; 23 of 30 runs under-predicted) both say the predictions should err **low**: too little queueing. The reasons given were that cap-invariant holds ignore co-batching inflation and that independent resampling smooths bursts.
- At L = 200 that held: all five nonzero cells were under-predicted.
- At L = 400, C = 8 the attack arm was **over-predicted in all 10 seeds**, by 86.6 to 480.5 ms (5.2% to 10.6%). The controls and A/A arms were over-predicted by 0.5–3.2%.
- Every one of these scores still passed the frozen tolerance, but the stated direction of bias is **contradicted** in the one regime where the queue is deep.

**A candidate explanation, untested.** The L = 400 hold-time pools come from one v4 calibration seed in an over-saturated cell. Holds measured under saturation may include inflation that is absent from v5's realized trajectories. In addition, an offered demand of about 1.00 × capacity puts the queue at the edge of stability, where small service-time differences produce large queue differences. We have not tested this.

### 5.3 Slot demand vs capacity [post-hoc]
Slot demand per arm = Σ(t_terminal − t_sent) over all requests / (C × 120 s); Fig. 4a.

- **Decode-heavy competitors raise demand without raising tokens.** Under equal authorized tokens, the D attack arms offer 33% (L = 200) to 39–40% (L = 400) more slot-time than their controls, because long decodes hold slots longer (L200 C8: 0.58 vs 0.43).
- **L = 400, C = 8 is at capacity.** The attack arm reaches **1.00** of capacity (control 0.72), which matches the unbounded victim queue (3.6 s mean, 7.2 s P95) and the SLO collapse.
- **Prefill-heavy competitors do the opposite.** P attack arms offer *less* slot-time than their controls (0.19 vs 0.44 at C = 8): fewer, shorter-held requests. Their small harm is therefore in the backend, not at the gateway.

### 5.4 Smaller observations [post-hoc]
- **H1 seed heterogeneity.** One seed (5005) shows no amplification (0.955), and one shows 3.09. Per seed, the H4(b) queue reductions range from 5.8 to 165.5 ms.
- **The prefill effect is small but not zero.** P vs S is 1.048, 1.073 and 1.063 at C16, C32 and direct, with 95% CIs that exclude 1. Each lies inside the equivalence band, so H6 stands. "No effect" would overstate it.

---

## 6. Figures

All figures are in `reports/v5/consolidated/` as vector PDF and 300-dpi PNG. Colours are validated categorical slots
1–3; identity is also given by a legend and direct labels.

| Figure | Content |
|---|---|
| `fig1_cap_sensitivity` | Geo-mean ratio [95% CI] vs C (8, 16, 32, direct) for D vs S, P vs S and A/A, at L = 200 and L = 400, with the equivalence band shaded. The L = 400 C = 8 point carries its "threshold not above noise" flag |
| `fig2_latency_and_gateway_queue` | Per-seed victim mean user TTFT (top) and gateway queue (bottom), control vs attack, for D vs S at L200 and L400 and for P vs S at L200 |
| `fig3_victim_slo_success` | Per-seed victim SLO success, control vs attack, with the baseline-feasibility floor 0.95 marked |
| `fig4_slot_time_demand` | (a) Offered slot demand / capacity [post-hoc]; (b) H5: victim queue vs fraction of victims arriving during saturation (n = 300) |
| `fig5_fcfs_prediction_error` | (a) Predicted vs observed per seed for nonzero-queue cases, validated vs extrapolated; (b) relative error of each cell mean, showing the sign reversal at L = 400 |

---

## 7. Threats to validity

1. **Single model, GPU and serving stack.**
   - Every run used one Qwen2.5-7B-Instruct snapshot on one RTX 3090 with vLLM 0.17.1, one server process and a fixed scheduler configuration (`max_num_batched_tokens` 2048, `max_num_seqs` 256).
   - The absence of engine contention may not hold for larger models, smaller-memory GPUs, a tighter `max_num_seqs`, or other schedulers and chunked-prefill settings.
   - The snapshot is identified by exclusion and `max_num_seqs` by source-default inference, both owner-accepted. Neither was observed directly.
   - §9 proposes a cross-model and cross-GPU check.
2. **Fixed FCFS gateway.**
   - The admission policy is a single global FCFS queue. Cap is the only gateway variable studied.
   - The amplification mechanism, long-held decode slots blocking short victims, is specific to slot-based, shape-blind admission. Per-tenant quotas, token-aware or fair-share admission, or preemption could remove it or move it elsewhere. That question is out of scope for an attack-side benchmark.
   - The "direct" arm compares two execution paths with different batching. It does not isolate gateway software overhead.
3. **Ten seeds.**
   - Each v5 cell has n = 10 (v4: 5; v4 R2: 3, descriptive only).
   - H1 passes at p = 0.030 with a 95% lower bound of 1.236, close to its threshold.
   - Per-seed heterogeneity is large: 0.955–3.089 at L200 C8.
   - Exact sign-flip tests have a minimum p of 1/1024 and assume sign symmetry; the max(p_t, p_perm) rule mitigates this.
   - Equivalence verdicts at small n depend on the band [0.8, 1.25], which was fixed in advance.
4. **Engine-global queue histograms.**
   - vLLM exposes queue time only as an engine-global, finish-time histogram. Per-request engine queueing, scheduler order and KV-block contention are not observed.
   - H4(c) and "no engine contention" rest on aggregate means and bucket shares. Engine queueing confined to the victims' requests could hide inside them.
5. **Synthetic workloads.**
   - Tenants, prompts and arrival processes are deterministic synthetic templates: benign prompts, fixed shapes and frozen schedules.
   - Output lengths are forced (`ignore_eos`).
   - The load is open-loop at fixed token rates, with a 120 s window per arm.
   - Real traffic has heavier-tailed shapes, closed-loop clients and session structure. The magnitudes reported here (1.57× and 18×) belong to these workloads.
6. **Extrapolated predictions.**
   - L = 400 FCFS predictions use hold pools from one v4 calibration seed in over-saturated cells.
   - They are excluded from the H3 verdict by the frozen rule. They did pass, but their error direction contradicted the stated expectation (§5.2).
   - The prediction model assumes cap-invariant holds and independent resampling. Its 90% prediction intervals were known to under-cover: the leave-one-seed-out coverage was 0.57.
7. **Noise-threshold failure at L = 400, C = 8.** The largest observed effect sits in the one cell whose threshold is not above noise (§4.1). Its magnitude is robust (every seed ≥ 7.4×), but its classification carries the flag.
8. **Measurement details.**
   - Slot release is observed at the client (`t_terminal`), not inside the gateway.
   - The v4 occupancy-agreement claim had to be corrected (§5.1).
   - A/A in v4 replayed a shared trace; v5's A/A-ind uses independent traces.
9. **Researcher degrees of freedom.**
   - H2b and the C ≥ 16 direction were informed by the v4 R3 direct result. This is disclosed in Protocol v5 §3.4, and H2b is labelled a replication.
   - The post-hoc analyses here (§5.2–5.4), including the 1 ms zero/nonzero split, were defined after seeing the data.

---

## 8. Data preservation

**Archive verification, 2026-11-24 18:14 local.** Each archive and its local backup was checked with
`scripts/export_v5_raw.py verify`, and every file matched its manifest.

| Stage | Tarball SHA-256 | Size | Files | Manifest (in git) |
|---|---|---|---|---|
| A | `6e0cd5a11412074fc72aee5af20a7fd5add6d23eee3ec3985d7c502da0328415` | 22,641,308 B | 1,837 | `reports/v5/RAW_DATA_MANIFEST_A.json` |
| B | `81ce39baeccd9a4ce736474c5e1c314c2104b0742cced387d24e58a694c7d49a` | 17,846,895 B | 1,072 | `reports/v5/RAW_DATA_MANIFEST_B.json` |

**Inventory of the original, unsanitized data.** `reports/RAW_ORIGINAL_SHA256.txt` lists the SHA-256 of all 4,735 files
(228 MB) under `results/v4_*`, `results/v5_*`, `reports/v4/` and `reports/v5/{smoke,stage_a,stage_b}`, with
repo-relative paths. The inventory file's own SHA-256 is `973accd2…a89accf31c5`. These originals are git-ignored. They
contain the LAN address, GPU UUID and home paths, so they are **never** to be published.

### Off-machine backup checklist
Today every copy is on one disk (`./`, `~/QuotaShift-backups/`). Nothing has been uploaded anywhere.

1. [ ] **Encrypted copy 1:** an external drive that is unplugged when not in use. Copy:
   - `~/QuotaShift-backups/` (both sanitized archives and their manifests);
   - `results/v4_*`, `results/v5_*`, `reports/v4/`, `reports/v5/{smoke,stage_a,stage_b}`;
   - `reports/RAW_ORIGINAL_SHA256.txt`.
   
   Use an encrypted volume, because the originals hold infrastructure identifiers.
2. [ ] **Encrypted copy 2:** a different place and medium, such as a second machine or an encrypted cloud bucket in an account you own. Any upload to a service is an outward-facing step that needs owner approval first.
3. [ ] **Store the export salt separately** (`~/.config/quotashift/export_salt`, 64 bytes), for example in a password manager. Do **not** store it in the same archive as the sanitized tarballs. Losing it means future exports can't reuse the same GPU pseudonyms; leaking it lets someone link pseudonyms back to the device IDs.
4. [ ] **Verify every copy after writing:**
   - `shasum -a 256 -c reports/RAW_ORIGINAL_SHA256.txt`, run from a restored tree;
   - `scripts/export_v5_raw.py verify --manifest … --tar …` for each archive.
5. [ ] **Restore drill.**
   - Restore `results/` and `reports/v5/{stage_a,stage_b}` into a scratch clone of the repository. The frozen loader resolves run directories relative to the clone's `results/`.
   - In the clone, run `uv run python scripts/v5_analysis.py --stage B --reports reports/v5/stage_a --reports reports/v5/stage_b --out <scratch> --force`.
   - Diff `<scratch>/analysis_B.json` against the committed file.
6. [ ] **v4 has no sanitized export yet.** Only the originals and the inventory exist. A v4 export would need its own tool run and owner review.
7. [ ] **Public release** (GitHub Release or Zenodo DOI for the sanitized tarballs, per `docs/RAW_DATA_AUDIT.md` §2) needs separate owner approval. Afterwards, record `release_asset_url` in each manifest.
8. [ ] **Record each completed copy** (date, medium, verifier) in `docs/RAW_DATA_AUDIT.md`.

---

## 9. Proposed next step

An independent cross-model and cross-GPU validation is designed but **not run**; see
`docs/PROTOCOL_X1_CROSS_PLATFORM_DRAFT.md`.
