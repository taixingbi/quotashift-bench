# Protocol X2: cross-platform validation of the QuotaShift mechanism (rev 2, FREEZE CANDIDATE)

**Status: rev 2, candidate for X2 Freeze Commit 1. Not frozen, not approved to run; nothing has been run.**
- **Rev 1** (`dbca42a`): draft.
- **Rev 2** (2026-11-25) applies the owner's review of rev 1:
  - keep the full 2 × 2, including gpu-node-2;
  - offline Q1 sizing approved;
  - before/after snapshots accepted conditionally;
  - both the C = 32 and direct controls kept;
  - 1.25× and the new seeds kept.
- **Freeze:** X2 Freeze Commit 1 (`x2_freeze1`) pins this document with the code and specification (`scripts/pin_x2.py`).
- **Separate from X1:**
  - X1 is closed at preflight (`docs/X1_CLOSEOUT.md`) and its frozen files and records are untouched;
  - X2 re-verifies X1's manifests and the v5 pins at every check;
  - **no X1 data are used as evidence.** The only X1 input is the A1 idle-TTFT timing distribution, used solely to size Q1 (§4). That use is disclosed.

**Companion documents:**
- `docs/X2_INSTRUMENTATION_SPEC.md`: the measurement procedure, normative;
- `docs/X2_HOST_AUDIT.md`;
- `reports/x2/Q1_POWER.md`;
- `docs/X2_DEPLOYMENT_READINESS.md`.

## 1. Question

The original QuotaShift mechanism (v4/v5):
- **Setup:** under identical, authorized per-tenant token budgets, a competitor that spends its budget on
  **decode-heavy** requests (D) instead of **short** requests (S) holds the gateway's FCFS concurrency slots longer.
- **Effect:** this raises victim tenants' user-facing TTFT.
- **Where the delay comes from:** the gateway queue, not GPU contention. It requires a binding cap: C = 8 binds; C = 32 and the direct path do not.

**X2 asks:** does the effect **and** its cap-dependence replicate on independent model × GPU platforms? Each platform is
qualified and load-calibrated on its own, with no anchor.

## 2. Lessons from X1 that X2 is designed around

| X1 problem | X2 response |
|---|---|
| A 1 Hz host sampler on the GPU host, started over ssh before ON segments, was associated with an intermittent TTFT slowdown and failed qualification | No in-band instrumentation inside measured windows; boundary snapshots outside a 15 s guard; qualification of **the exact production procedure** per platform (§4) |
| The G0 measurement path is wireless at both ends (found in the X2 audit) | Phase 1 records the path; G0 needs wired Ethernet before X2-Q (readiness blocker B-X2-1); Q0 reports host and path stability |
| G1 under X1 targets polled DCGM on the GPU host during arms; G0 did not | X2 targets `gpu_telemetry: none`; the G1 overlay disables the DCGM and X1 sampler daemons |
| Every platform's grid was anchor-relative | **Self-calibration** from each platform's own Phase-1 hold time (§5) |
| The rev 4 equivalence rule had no error rate; A1's t-interval is liberal for X1-shaped (intermittent, skewed) effects | Q1's test, n and failure rule are fixed by a simulation whose size is checked under intermittent and heavy-tailed alternatives (§4) |
| Anchor-dependent verdict | Platform-symmetric verdict (§6) |

## 3. Platforms (owner decision: full 2 × 2)

| | G0: RTX 3090 (gpu-node-2, owned LAN host) | G1: NVIDIA L4 (AWS g6.xlarge, us-east-1) |
|---|---|---|
| Qwen2.5-7B-Instruct @ `a09a35458c702b33eeacc393d103063234e8bc28` | g0m0 | g1m0 |
| Mistral-7B-Instruct-v0.3 @ `c170c708c41dac9275d15a8fff4eca08d52bab71` | g0m1 | g1m1 |

- **Serving template:** vLLM 0.17.1, identical to X1 §2.1.
- **No platform has a special role.**
- **gpu-node-2 remains a candidate.** The X1 failure does not disqualify it under a different, independently qualified procedure, but its qualification is not blind to that history.
- **gpu-node-1** stays out of scope.

## 4. Instrumentation and qualification (normative detail: `docs/X2_INSTRUMENTATION_SPEC.md`)

### 4.1 Measured-window policy

- **Window:** from 15 s before an arm to its end.
- **Inside a window:** no host action by the harness and no GPU telemetry polling. Only the workload and the frozen v5 `/metrics` scrape (0.5 s, both arms) run.
- **Resident processes** are inventoried at every snapshot. A change flags the arm; a vLLM pid change fails it.

### 4.2 Boundary snapshots (owner: accepted conditionally)

- **Procedure:** before-snapshot → 15 s guard → arm → after-snapshot.
- **Per-arm means:** host CPU, API-server and EngineCore CPU, MemAvailable, OOM and swap deltas, inventory.
- **Fail:** OOM, vLLM pid change, MemAvailable < 1 GiB.
- **Flag:** host ≥ 80%, API ≥ 0.85 core, MemAvailable < 2 GiB, swap-in, inventory change.
- **Limitation:** intra-arm bursts are not observable.
- **Transport:** ssh on G0; an idle HTTP snapshot daemon on G1.

### 4.3 Qualification per platform (before calibration; one run; no retry)

**Phase 1** (fail → not admissible):
- **Checks:** identity, KV, verified cache reset, smoke lengths.
- **Measurements:** the platform's own isolated S/D hold times, runner → server RTT, an inventory baseline.

**Q0 — host stability** (reported, not a gate):
- 16 pairs of identical idle segments.

**Q1 — instrumentation invariance** (gate):
- **Design:** **K = 64** balanced pairs of segments (P = production snapshot procedure, N = the same idle time without it).
- **Each segment:** a verified cold cache, 3 warm-ups, and **M = 40** identical-prompt requests timed on the runner, with the `/metrics` poller running.
- **Tolerance:** δ = max(1 ms, 2% × the N median), the X1 tolerance unchanged.
- **Decision:** PASS iff the **95% t-interval** of the mean paired difference lies strictly inside ±δ (test **T1s**). Otherwise the platform is not admissible.

**Sizing** (`reports/x2/Q1_POWER.md`; rules fixed before the first run):

| Candidate | Worst-case size at ±δ | Outcome |
|---|---|---|
| T1 (90%, as X1 A1) | 0.062–0.072 | rejected: liberal under X1-shaped intermittent effects |
| T2 (bootstrap-t) | 0.083 | rejected |
| T3 (trimmed mean) | 0.44–0.49 | rejected |
| **T1s at K = 64, M = 40** | **0.039** | **chosen:** power 1.00 base, 0.806 pessimistic |

**Power is lost on hosts with frequent large slow segments:** 0.01–0.20 when 20–30% of segments are up to 10 ms slow.

## 5. Calibrated load independence

1. **Platform-local grid.**
   - Six rates whose **predicted** control slot demand ρ̂ = (108 victim + S-competitor requests) × the own isolated S hold / (8 × 120 s) equals 0.30, 0.40, 0.50, 0.60, 0.75 and 0.90.
   - The grid uses only that platform's own Phase-1 measurement (`scripts/build_x2.py grid`).
2. **Calibration A.** Seeds 22000–22002, A/A-ind short-short at C = 8.
   - **low** = the grid point whose realised control ρ_ctl is closest to 0.43 (ties go lower).
   - It is **infeasible** unless some point has ρ_ctl ≥ 0.40 with control SLO ≥ 0.95. An infeasible point is reported and never substituted.
   - Only control-arm data enter the selection.
3. **Freeze ordering, per platform.**
   - The calibration-A traces are frozen after a qualification pass and before any calibration-A run.
   - The main traces and rates are frozen after calibration A and before any main run.
   - Pins are `x2_freeze_<phase>_<plat>`; the stage driver re-checks them before every live block.
4. **Independence.** No platform's rate, qualification or admissibility depends on another's.

## 6. Hypotheses, families and verdict (frozen v5 statistics, imported unchanged)

ℓ is the per-seed log ratio of victim mean user-facing TTFT, attack/control.

| ID | Claim (platform p, at its own low point) | Block, n | Test | Family |
|---|---|---|---|---|
| **X2-H1** (primary) | D vs S at C = 8 **exceeds 1.25** | X2a, 24 (noise floor: X2b A/A-ind, 24) | one-sided t of mean ℓ > log 1.25 | Holm over 4 platforms; p = 1 if not admissible or not evaluable |
| **X2-H2** | D vs S on the **direct path** is equivalent within [0.8, 1.25] | X2c, 10 | TOST | Holm over 8 = 4 × H2 + 4 × H3 |
| **X2-H3** | D vs S at **C = 32** is equivalent within [0.8, 1.25] | X2d, 10 | TOST | same family |
| **X2-H4** | At C = 8, attack backend TTFT within [0.9, 1.1] × control **and** the engine queue negligible | X2a | v5 rule | own criterion |

**Verdict:**
- A platform **replicates** iff H1 is supported **and** H2, H3 and H4 hold on it.
- **REPLICATES** iff ≥ 3 of 4 platforms replicate.
- **REPLICATES-ON-k** (k = 1, 2) is descriptive.
- Otherwise **NOT REPLICATED AT THIS POWER**.
- An inadmissible platform is reported as such, never as evidence about the mechanism.
- "H1 not supported" is never reported as absence of the mechanism.

**No interim looks:** real data are analysed only when every expected cell of every admissible platform exists.

**Power** (`scripts/x2_verdict_power.py` → `reports/x2/VERDICT_POWER.json`):
- **Method:** the X2 verdict, the per-platform conjunction H1 ∧ H2 ∧ H3 ∧ H4, simulated with the frozen v5 rules on the v5 noise estimates used by X1 P0. 1,000 repetitions per scenario.

| True ratio | τ = 0, 1× noise | τ = 0, 1.5× | τ = 0.2, 1× | τ = 0.2, 1.5× |
|---|---|---|---|---|
| 1.4 | 0.138 | 0.021 | 0.236 | 0.138 |
| **1.565 (v5)** | **0.937** | 0.418 | 0.591 | 0.370 |
| 1.8 | 1.000 | 0.971 | 0.900 | 0.752 |

- **False REPLICATES** with the effect on only 2 of 4 platforms: 0.000.
- **Bound:** the conjunction is limited by H1 alone. H2, H3 and H4 almost never fail at the v5 noise levels.
- **Matches X1 P0:** the v5-effect value agrees with P0 (0.938).

## 7. Seeds and isolation (new; disjoint from v4, v5 and X1; tested)

| Use | Seeds |
|---|---|
| already used (not reused) | v4 42–46, 900, 1000; v5 4900, 5000–5009; X1 4990, 7000–7007, 8000–8023; X1 preflight prompts 1–2, 77–78, 100–104, 200–279, 900–902, 9000–9059 |
| X2 smoke | 20990 |
| X2 qualification prompts / warm-ups | 21000–21039 / 21900–21902 |
| X2 Phase 1 hold-time probes | 21100–21139 |
| X2 calibration A | 22000–22002 |
| X2 main (X2a, X2b: 24; X2c, X2d: 10) | 23000–23023 |

Isolation salts are `x2-<platform>-<scenario>-r1`, and `-r2` for the single pre-generated rerun.

## 8. Stages and approvals (all new tokens; nothing pre-approved)

| Stage | Content | Token |
|---|---|---|
| X2-F1 | X2 Freeze Commit 1: pin the candidate manifest (`reports/x2/FREEZE_CANDIDATE_SHA256.json`) | `x2_freeze1` |
| X2-Q(p) | Server under the template (G0: restart to the platform's model; G1: deploy); Phase 1 + Q0 + Q1 | `x2_qual_<p>` (+ `x2_aws_*` for G1) |
| X2-C(p) | Freeze and pin calA traces; calibration A; select low; freeze and pin main traces | `x2_freeze_calA_<p>`, `x2_cal_<p>`, `x2_freeze_main_<p>` |
| X2-M(p) | Main stage | `x2_main_<p>` |

**Estimated time per platform:** 1.4–1.8 h qualification, 1.9 h calibration A, 6.7 h main, about 0.5 h server start.
That is about 10.5–11 h per platform and about 43 h in all.

**G1 cost estimate:** about $32 planned, $42 pessimistic. Details are in the readiness report.

## 9. Threats to validity (X2-specific)

1. **Designed after X1's failure.** X1 produced no mechanism data, so no outcome informed X2's hypotheses, thresholds or n. G0 qualification is not blind to X1's history.
2. **Coarse host accounting.** Arm means only; intra-arm bursts are not visible. X2-H4 and the engine-queue rule are the generation-path safeguard.
3. **A noisy host or path can fail Q1 for lack of power,** not because of the instrument. This is reported as "equivalence not established". Q0 shows the host's own variability.
4. **Self-calibrated operating points differ in absolute rate** by design; load is matched in slot demand.
5. **Narrower scope than X1.** No high-load point and no FCFS replay.
6. **Heterogeneity.** At τ = 0.2, P(REPLICATES) is about 0.59 even at the v5 effect, so a non-replication verdict is weak evidence.
7. **The G0 host is a shared desktop machine.** It runs a desktop session, a k3s agent and package timers. Their changes are flagged; disabling them is an owner action (readiness).
8. **Frozen v5 code** is verified against the v5 pins at freeze and before every live block; X1 manifests are re-verified too.
