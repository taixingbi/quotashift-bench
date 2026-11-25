# X2 instrumentation specification (candidate for X2 Freeze Commit 1)

**Status:** final candidate, 2026-11-25. Not frozen. It is pinned by `scripts/pin_x2.py` at X2 Freeze Commit 1, which needs owner approval `x2_freeze1`.

**Owner decisions applied:**
- full 2 × 2, with gpu-node-2 kept as a candidate;
- before/after snapshots accepted, on the condition that the limitation is stated (§4);
- both the C = 32 and direct controls kept;
- 1.25× and the new seeds kept.

**Inputs:**
- `docs/X2_HOST_AUDIT.md`;
- `reports/x2/Q1_POWER.{json,md}`;
- X1 closeout (`docs/X1_CLOSEOUT.md`).

## 1. Purpose

Host-resource confounders (CPU, RAM, swap, resident processes) must be observable per arm, and the act of observing them
must be shown, on each platform, not to move the primary measurement (victim user-facing TTFT, timed on the runner) by
more than the X1 tolerance.

## 2. Measured-window policy

**Measured window:** from **15 s before** an arm's first request to the arm's end (drain included). The same applies to
every Q0/Q1 segment.

1. **No harness-initiated host action inside a window.** No ssh session, no process start, no snapshot request, no GPU telemetry poll. X2 targets set `gpu_telemetry: none`; the G1 overlay disables the X1 sampler and DCGM daemons.
2. **Allowed inside a window, in both arms alike:**
   - the workload;
   - the frozen v5 harness's `/metrics` scrape at its production interval (0.5 s). Q0 and Q1 run the same poller.
3. **Resident processes** (desktop, agents, timers) are part of the platform.
   - Their user-space inventory (sorted names with counts, SHA-256) is recorded at every snapshot.
   - A change between an arm's two snapshots **flags** the arm.
   - A change in the vLLM pids **fails** it.
   - No X2 sampler or exporter is resident on any GPU host. The G1 snapshot daemon is idle between requests and is requested only outside windows.
4. **The network path is part of the platform** and is recorded in Phase 1 (runner → server HTTP RTT, 20 probes). Wired paths are required for G0 before X2-Q (readiness blocker B-X2-1).

## 3. Boundary-snapshot procedure (production; `src/quotashift/x2/snapshot.py`, `scripts/x2_host_snapshot.py`)

**Per arm:**
1. **before:** one snapshot.
2. **guard:** wait **15 s**, counted from when the snapshot **returned**.
3. **arm:** the frozen v5 harness runs it.
4. **after:** one snapshot.

The per-arm record is `x2_host_snapshots.json`, written next to the arm's run.

**Snapshot contents** (read-only `/proc`, stdlib, about 50 ms):
- `/proc/stat` total and idle jiffies, and CPU count;
- vLLM API-server and EngineCore pids, and their utime + stime. These are identified exactly as the X1 sampler did;
- MemAvailable;
- `oom_kill` and `pswpin`;
- the resident inventory and its hash;
- systemd timers (best effort; G0 only).

**Transport, one per platform, each qualified by that platform's own Q1:**
- **G0:** `ssh -o BatchMode=yes <host> python3 - < x2_host_snapshot.py`. One ssh session per snapshot; no resident process.
- **G1:** HTTP GET to the snapshot daemon (`--serve 9500`, ECS daemon, host PID namespace, read-only root, no logging, runner security group only).

**Harness wiring:**
- The X2 stage driver sets `QUOTASHIFT_X2_BOUNDARY` (JSON) for the `quotashift experiment` subprocess.
- `local.run_experiment` wraps each arm when it is set.
- When it is unset (v4/v5/X1), behaviour is unchanged. A test asserts that no snapshot file is written.

## 4. Per-arm accounting and flags (pre-registered; arm means only)

| Quantity | Rule |
|---|---|
| OOM kill during the arm | **fail**: the block fails (v5 single-rerun rule) |
| vLLM pid change | **fail** |
| MemAvailable at either boundary < 1 GiB | **fail** |
| Host mean busy ≥ 80% | flag |
| API server mean ≥ 0.85 core | flag |
| MemAvailable < 2 GiB | flag |
| any swap-in | flag |
| resident inventory changed | flag |

Missing data counts as a flag. Flags are descriptive, reported per cell, and never alter a hypothesis test.

**Limitation (owner condition):** intra-arm bursts are not observable; only arm means are. Engine-queue negligibility and
backend TTFT (X2-H4) are the generation-path safeguard.

## 5. Qualification (per platform, before calibration; `src/quotashift/x2/qualification.py`, `scripts/x2_qualify.py`)

### 5.1 Phase 1 (fail → not admissible)

- **Checks:**
  - vLLM 0.17.1;
  - model listed;
  - server-reported revision;
  - prefix caching on;
  - KV ≥ 20,480 tokens;
  - verified `/reset_prefix_cache`;
  - smoke generation lengths (S 64, D 256).
- **Measurements:**
  - the platform's own isolated S and D hold times (20 each, seeds 21100–21139). The S mean defines the calibration-A grid;
  - runner → server RTT;
  - one snapshot, as the inventory baseline.

### 5.2 Segments (Q0 and Q1)

**Segment structure:**
1. state: P = production before-snapshot, or N = an idle wait of the same length;
2. 15 s guard;
3. verified cache reset;
4. 3 warm-ups (seeds 21900–21902), never analysed;
5. **M = 40** measured streamed requests:
   - one fixed prompt list (seeds 21000–21039, 60 words, `max_tokens` 8, temperature 0, `ignore_eos`), **identical in every segment**;
   - one request in flight, each on a fresh connection;
   - TTFT timed on the runner;
   - the `/metrics` poller running at 0.5 s;
6. state: P = after-snapshot, or N = the same idle wait.

**Q0 (host stability, reported, not a gate):**
- K0 = 16 pairs of N/N segments.
- Reports the mean pair difference with its 90% CI, the segment-median floor, and the count of slow segments (> floor + 2 ms).

**Q1 (instrumentation invariance, the gate):**
- **Design:** K = **64** balanced pairs. Pair k runs (N, P) if k is even and (P, N) if odd, so each first in 32 pairs, with equal mean positions.
- **Statistic:** d_k = p50(P_k) − p50(N_k), nearest-rank.
- **Tolerance:** δ = max(1 ms, 2% × the p50 of all N requests), the X1 tolerance unchanged.
- **Decision — T1s:** PASS iff the **95%** t-interval of the mean d_k (t from the frozen v5 `t_cdf`, df = 63) lies strictly inside (−δ, +δ). Otherwise FAIL.
- **Also FAIL:** any missing or non-finite request, any unverified reset, or any segment whose procedure is unverified.
- **No retry.**

### 5.3 Why T1s, K = 64, M = 40 (`reports/x2/Q1_POWER.md`)

**Rules, fixed in the script before its first run:**
- **R1:** size ≤ 0.05 at ±δ, for both constant and intermittent effects, in every noise scenario:
  - noise scale × 1, 1.5, 2;
  - normal or t₃ tails;
  - host slow segments in both arms with probability 0–0.3, of 3–5 or 3–10 ms;
  - drift 0 or 0.05 ms per segment.
- **R2:** base power ≥ 0.90.
- **R3:** power ≥ 0.80 with 1.5× noise and 20% slow segments.
- **Choice:** the cheapest design meeting all three.

| Candidate | Worst-case size | Outcome |
|---|---|---|
| T1 (the X1 A1 rule, 90% interval) | 0.062–0.072 at every K tested (48–128) | **Rejected:** the intermittent, X1-shaped effect makes pair differences right-skewed and the t interval liberal |
| T2 (bootstrap-t) | 0.083 (heavy bursts, K = 48) | **Rejected** |
| T3 (20%-trimmed mean) | 0.44–0.49 | **Rejected:** trimming hides exactly the intermittent effect X1 found |
| **T1s (95% interval) at K = 64, M = 40** | **0.039** | **Chosen:** base power 1.00, pessimistic power 0.806, about 58 min on G0 |

**Sensitivity at the chosen design:**
- size ≤ 0.028 for a constant effect and ≤ 0.041 for an intermittent one;
P(pass | no effect) over all 12 combinations of noise scale, tails and drift at each host-noise level:

| Slow segments (both arms) | P(pass \| no effect) |
|---|---|
| none | 0.995–1.00 |
| 10%, 3–5 ms | 0.93–0.99 |
| 20%, 3–5 ms | 0.76–0.90 |
| 30%, 3–5 ms | 0.60–0.79 |
| 10%, 3–10 ms | 0.46–0.65 |
| **20–30%, 3–10 ms** | **0.01–0.20** |

Such a host would fail Q1 for lack of power, and it must be reported as "equivalence not established", which is why Q0 is reported first.

**Run history (all runs kept):**
- **Run 1:** wrong boundary (a fixed 1.0 ms).
- **Run 2:** no valid candidate.
- **Run 3:** size evaluated at each design's own K, and the strict interval added. This was declared before the run, with no X2 data in existence.

## 6. Outputs

| File | Contents |
|---|---|
| `experiments/x2/<plat>/QUALIFICATION.json` | committed: Phase 1, Q0 summary, Q1 decision, design |
| `reports/x2/<plat>/qualification/segments.json` | git-ignored: per-request timings |
| `x2_host_snapshots.json` | per arm, beside each run (git-ignored with the results) |
