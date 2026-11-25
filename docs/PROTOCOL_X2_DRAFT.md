# Protocol X2: cross-platform validation of the QuotaShift mechanism (DRAFT PROPOSAL)

**Status: DRAFT for owner review. Not pre-registered, not frozen, not approved, nothing implemented, nothing run.**
- **Separate from X1.** X1 is closed at preflight (`docs/X1_CLOSEOUT.md`); its frozen files and records are untouched.
- **Own everything.** X2 has its own protocol, seeds, freeze manifests and approval tokens (`x2_*`).
- **No X1 data as evidence.** The only X1 input is the A1 idle-TTFT timing distribution, used solely to size X2's instrumentation-qualification test (§4.3). That use is disclosed.

## 1. Question

The original QuotaShift mechanism (v4/v5):
- **Setup:** under identical, authorized per-tenant token budgets, a competitor that spends its budget on
  **decode-heavy** requests (D) instead of **short** requests (S) holds the gateway's FCFS concurrency slots longer.
- **Effect:** this raises victim tenants' user-facing TTFT.
- **Where the delay comes from:** the gateway queue, not GPU contention. It requires a binding cap: C = 8 binds; C = 32 and the direct path do not.

**X2 asks:** does this mechanism, the effect **and** its cap-dependence, replicate on independent model × GPU platforms?
Each platform must be qualified and load-calibrated on its own, without any platform serving as a reference for another.

## 2. Lessons from X1 that X2 is designed around

| X1 problem | X2 design response |
|---|---|
| The 1 Hz host sampler process on the GPU host, started over ssh before ON segments, was associated with an intermittent idle-TTFT slowdown (+0.85 ms, 90% CI +0.26 to +1.44; 5 of 24 pairs +3–5 ms) and failed qualification | **No in-band instrumentation** on the GPU host during any measured window (§4.1). Host accounting by arm-boundary snapshots outside a guard interval (§4.2). Qualification tests **the exact production procedure** (§4.3) |
| All platforms' load grids were scaled by the anchor's decode rate, so one inadmissible platform blocked every other | **Self-calibration**: each platform's calibration grid comes only from its own measurements (§5). No anchor, no cross-platform reference |
| The rev 4 equivalence rule had no error rate; the A1 fix was post hoc | Every qualification test, statistic, n and failure rule is fixed **before** any X2 data. Its size is checked by simulation under heavy-tailed pair differences like those seen in A1 (§4.3) |
| Verdict categories depended on the anchor (ANCHOR-ONLY) | Platform-symmetric verdict; inadmissible platforms count as "not supported" and are reported as inadmissible (§6) |
| Broad scope (H1–H5, two load points, FCFS replay) | Focused on the mechanism: the effect, its cap-dependence, and localisation to the gateway queue (§6). High-load and FCFS-replay questions are out of scope |

## 3. Platforms (owner decision needed)

**Default:** the same four cells as X1, each treated as an independent platform with no anchor role:
- Qwen2.5-7B-Instruct and Mistral-7B-Instruct-v0.3, at the X1-pinned revisions;
- on the RTX 3090 (gpu-node-2) and the L4 (AWS g6.xlarge);
- serving template: vLLM 0.17.1, identical to X1 §2.1.

**Disclosed risk:** gpu-node-2 is the host where X1's instrument failed qualification. X2's G0 qualification is therefore
**not blind** to that history, and a G0 failure under X2 would be reported as such.

**Alternatives for the owner:**
- replace G0 with a different owned host. gpu-node-1 is the v5 server and has been out of scope so far; using it would make G0 a same-host replication of v5, not a cross-platform one;
- or run G1 only (2 platforms), with a correspondingly weaker verdict.

## 4. Instrumentation qualification

### 4.1 No in-band host instrumentation

During every measured window (calibration arms, main arms, qualification segments) **no process is started, and no
ssh session opened, on the GPU host**. The runner sends only:
- the workload;
- the frozen v5 harness's own server requests (`/metrics` at block boundaries, the verified cache-reset probe).

These are identical in both arms.

### 4.2 Host accounting by boundary snapshots

**How the snapshots are taken:**
- Before each arm and after it, one ssh call reads, once:
  - `/proc/stat`;
  - `/proc/<api>/stat` and `/proc/<engine>/stat`;
  - `/proc/meminfo`;
  - `/proc/vmstat`.
- A guard interval **G = 15 s** of idle separates the "before" snapshot from the arm's first request; the "after" snapshot is taken once the arm has ended.
- The same script runs on G0 and G1.

**What they yield, per arm:**
- mean host CPU utilisation;
- API-server and EngineCore CPU-seconds;
- OOM-kill and swap-in deltas;
- MemAvailable at both ends.

**Flags, set from the arm means** (to be fixed at pre-registration):
- host mean CPU ≥ 80%;
- API server ≥ 85% of a core on average;
- any OOM kill (block fail, v5 rerun rule);
- any swap-in.

**Limitation, disclosed:** short saturation bursts inside an arm are not visible. Engine-queue metrics and backend TTFT
(X2-H4) cover the generation path.

### 4.3 Qualification tests per platform (before calibration; fixed now)

**Q0 — host stability (A/A).**
- **Design:** K pairs of segments with **no procedure in either segment**. Otherwise identical to Q1: verified cold cache, 3 warm-ups, the same fixed prompt list, one request in flight, timing on the runner.
- **Purpose:** estimates the host's own segment-to-segment variability, including intermittent slow segments like those seen in A1.
- **Status:** reported. It is not a gate.

**Q1 — instrumentation invariance (the gate).**
- **Design:** K balanced pairs. Each pair has a **segment preceded by the production boundary-snapshot procedure**:
  1. the before-snapshot ssh call;
  2. the guard interval;
  3. the segment;
  4. the after-snapshot ssh call.

  The other segment has the same idle wait but no ssh.
- **Tolerance:** δ = max(1 ms, 2% × the OFF median). This is the X1 tolerance, kept unchanged so that X2 is not looser than X1.
- **Decision:** equivalence at α = 0.05.
- **Fixed before any X2 data, by a sizing simulation:**
  - **The statistic.** Candidates are:
    - t-TOST on the mean pair difference (the A1 rule);
    - a bootstrap-t TOST;
    - a TOST on a 20%-trimmed mean of the pair differences.
  - **K and M.**
- **Requirements the simulation must meet:**
  - size ≤ 0.05 at ±δ under a heavy-tailed mixture: the A1 pair distribution, i.e. about 20% of pairs shifted by 3–5 ms, plus the attempt-2 request noise at 1×, 1.5× and 2×;
  - power ≥ 0.90 at θ = 0 in the base case;
  - power ≥ 0.80 when 20% of pairs are slow in **both** arms (host noise, not instrumentation).
- **Indicative size:** K ≥ 32 pairs × M = 80, about 25–35 min per platform. This is to be confirmed by the simulation, and is not yet a commitment.
- **On failure:** the platform is not admissible. There is no retry and no amendment; the failure is reported with Q0.

**Why this should pass where X1 failed — a hypothesis, not a claim.**
- No process runs on the GPU host during the segment.
- The only ssh activity ends at least G = 15 s before the first measured request.
- If Q1 still fails, X2 has learned that boundary ssh access alone perturbs idle TTFT on that host. That would be a reportable instrumentation result.

## 5. Calibrated load independence

1. **Platform-local grid.**
   - Phase 1 measures, on the idle server, the mean gateway hold time of an isolated S request and an isolated D request: 20 each, with a verified cold cache.
   - The calibration-A grid is the set of request rates whose **predicted** control-arm slot demand ρ̂ = λ · E[hold] / 8 equals 0.30, 0.40, 0.50, 0.60, 0.75 and 0.90.
   - The grid uses only that platform's own numbers. Nothing refers to another platform or to v5 rates.
2. **Selection.**
   - Calibration A (seeds below, 3 per grid point) measures the realised ρ_ctl on the S-vs-S control arm at C = 8, as in v5/X1.
   - **low** = the grid point with ρ_ctl closest to 0.43 (ties go lower) and control SLO ≥ 0.95. If none reaches ρ_ctl ≥ 0.40, it is reported as infeasible and never substituted.
   - Only control-arm data enter the selection.
3. **Freeze ordering, per platform.**
   - The calibration traces are frozen before calibration.
   - The rates and main traces are frozen after calibration and before any main run.
   - This reuses the X1 per-phase ordering mechanism, re-implemented under `x2_*` names.
4. **Independence.** No platform's rate, qualification or admissibility depends on another's. A platform can be run, or fail, alone.

## 6. Hypotheses, families and verdict (fixed at pre-registration; frozen v5 statistics imported unchanged)

ℓ is the per-seed log ratio of victim mean user-facing TTFT, attack/control (v5 definition).

| ID | Claim (per platform p, at its own low point) | Test | Family |
|---|---|---|---|
| **X2-H1** (primary) | D vs S at C = 8 **exceeds 1.25** | one-sided t of mean ℓ > log 1.25, n = 24, with an A/A-ind noise-floor block (n = 24) | Holm over the 4 planned platforms; p = 1 if not admissible |
| **X2-H2** (cap-dependence) | D vs S on the **direct path** (no gateway cap) is equivalent within [0.8, 1.25] | TOST, n = 10 | Holm over 8 = 4 × H2 + 4 × H3 |
| **X2-H3** (cap-dependence) | D vs S at **C = 32** is equivalent within [0.8, 1.25] | TOST, n = 10 | same family |
| **X2-H4** (localisation) | At C = 8, attack backend TTFT within [0.9, 1.1] × control **and** the engine queue negligible | v5 rule | own criterion |

**Verdict** (platform-symmetric):
- **REPLICATES** iff X2-H1 is supported on ≥ 3 of 4 planned platforms **and**, on those same platforms, H2, H3 and H4 hold.
- **REPLICATES-ON-k** (k = 1 or 2), descriptive: H1, H2, H3 and H4 all hold on k platforms.
- **NOT REPLICATED AT THIS POWER** otherwise.
- **Reporting rules:**
  - every platform's estimate and CI is reported;
  - an inadmissible platform is reported as "not admissible (qualification)", never as evidence about the mechanism;
  - "H1 not supported" is never reported as absence of the mechanism.

**Power** (`reports/x1/P0_POWER.md`, same n and rule shape; to be re-simulated for the X2 verdict before freeze):
- P(H1 on ≥ 3 of 4) = 0.94–0.985 at the v5 effect and v5 noise;
- 0.57–0.59 with platform heterogeneity τ = 0.2;
- 0.40–0.51 at 1.5× noise.

X2's power is therefore limited by platform heterogeneity, and the protocol states this.

## 7. Seeds and isolation (new; disjoint from v4, v5 and X1)

| Use | Seeds |
|---|---|
| v4 / v5 / X1, already used (not reused) | v4 42–46, 900, 1000; v5 4900, 5000–5009; X1 4990, 7000–7007, 8000–8023; X1 preflight prompt seeds 1–2, 77–78, 100–104, 200–279, 900–902, 9000–9059 |
| X2 smoke | **20990** |
| X2 qualification prompts / warm-ups | **21000–21079 / 21900–21902** |
| X2 Phase 1 hold-time probes | **21100–21139** |
| X2 calibration A | **22000–22002** |
| X2 main (H1, A/A: 24; H2, H3: 10) | **23000–23023** |

Isolation salts are `x2-<platform>-<block>`.

## 8. Stages and approvals (all new tokens; nothing is pre-approved)

| Stage | Content | Token |
|---|---|---|
| X2-A | Review and approve this design, the platform set (§3) and the Q1 sizing simulation | `x2_design` |
| X2-F1 | Implement under `scripts/x2_*` and `src/quotashift/x2/`, with tests; Freeze 1 pins protocol, code and Q1 parameters (verifies v5 pins; X1 untouched) | `x2_freeze1` |
| X2-Q(p) | Per platform: server start under the template; Phase 1; Q0 + Q1 | `x2_qual_<p>` |
| X2-C(p) | Per platform: freeze calibration traces; calibration A; select rates; freeze main traces and rates | `x2_cal_<p>` |
| X2-M(p) | Per platform main stage: H1 + A/A 24 pairs, H2 and H3 10 each, about 5.7 h | `x2_main_<p>` |
| G1 infrastructure | AWS deploy and start for the L4 platforms, under the existing cost controls; separate per-stage approval | `x2_aws_*` |

**Estimated time per platform:** about 1 h for qualification and Phase 1, about 1.5 h for calibration A, about 5.7 h
for the main stage. That is roughly 33 h over 4 platforms. G1 cost follows the existing cost-control documents; no
price is assumed here.

## 9. Threats to validity (X2-specific)

1. **Designed after X1's failure.** The instrumentation design responds to X1's qualification failure, but X1 produced no mechanism data, so no outcome informed X2's hypotheses, thresholds or n. G0 qualification is not blind to X1 history (§3).
2. **Coarser host accounting.** Boundary snapshots cannot see intra-arm CPU bursts. The X2-H4 localisation test and the engine-queue metric are the safeguard.
3. **Boundary ssh may still perturb.** Q1 tests exactly this; if it fails, the platform is inadmissible.
4. **Self-calibrated operating points differ in absolute rate** between platforms. That is by design: load is matched in slot demand, not in tok/s.
5. **Narrower scope than X1.** No high-load point and no FCFS replay. X2 says nothing about effect magnitude at depth or about predictability.
6. **Heterogeneity.** The power at τ = 0.2 (about 0.57) means a non-replication verdict is weak evidence.
7. **Reuse of frozen v5 code** is verified against the v5 pins at freeze and before every live block.

## 10. Open items for the owner

1. The platform set (§3), and whether gpu-node-2 remains a candidate.
2. Approval to write the Q1 sizing simulation, offline. It would fix the Q1 statistic, K and M (§4.3).
3. Whether the boundary-snapshot flags (§4.2) are acceptable as the only host-resource evidence.
4. Whether to keep H3 (C = 32) as well as H2 (direct). Keeping both costs about 50 min per platform.
