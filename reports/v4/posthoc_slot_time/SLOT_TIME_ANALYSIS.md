# Protocol v4 — slot-time analysis and R1 decode statistical audit

**POST-HOC EXPLORATORY.** This analysis was not pre-registered. It does not change any pre-registered v4 result or
classification, and no seed was selected or removed. It was written on 2026-11-22, after every v4 run had finished,
for review.

- **Script:** `scripts/v4_posthoc_slot_time.py`, which only reads `results/` and `reports/v4/`.
- **Outputs in this folder:**
  - `per_run.csv` — one row per run, 152 runs: R1 30, R2 84, R3 38.
  - `victim_requests.csv` — one row per victim request.
  - `saturation_episodes.csv`
  - `occupancy_distribution.csv`
  - `r1_decode_per_seed.csv`
  - `r1_robust_stats_per_seed.csv`
  - `column_kinds.json`

## 0. What is measured, derived, estimated or unavailable

| Kind | Quantities | Source |
|---|---|---|
| **Measured** | per-request `t_offered`, `t_sent`, `t_first_token`, `t_terminal` (harness monotonic clock); slot hold = `t_terminal − t_sent`; competitor and victim slot-seconds; victim gateway queue = `t_sent − t_offered`; user-facing and backend TTFT | `requests.parquet` |
| **Measured, sampled about every 0.68 s** | gateway in-flight (`gw_inflight`), vLLM `num_requests_running` / `num_requests_waiting`, KV usage | `metrics_timeseries.parquet` |
| **Derived** (deterministic from measured timestamps) | in-flight occupancy k(t) rebuilt from the send and terminal events; time-weighted occupancy distribution; fraction of time with k ≥ 8; contiguous saturation episodes; victim arrivals during saturation; Spearman correlation of queue delay with occupancy | this script |
| **Estimate** (model-based) | queue delay at caps 16 and 32, from a global FCFS replay of the measured arrival and hold times. It assumes hold times do not depend on the cap, and that assumption is false (direct-path holds are 3–11% longer because the engine batches more) | `fcfs_replay` |
| **Unavailable** | per-request vLLM engine queue time; engine scheduler admission order; KV-block contention per request; gateway-internal release timestamps (`t_terminal` is the client-observed proxy) | not recorded by vLLM metrics or the harness |

**Validation of the reconstruction:**
- At lag 0, the rebuilt k(t) agrees exactly with the sampled `gw_inflight` 66% of the time (mean absolute error 0.42
  slots).
- Shifting the sample times by +0.15 s raises exact agreement to 91–99.5%.
- The scraper timestamps each sample before it reads the gateway count, because the vLLM and GPU metrics are fetched
  first. That offset is a measured property of the scraper; see KNOWN_LIMITATIONS.
- The rebuilt occupancy is therefore trusted. The 0.68 s sampled series is only a coarse check.

**FCFS replay at cap 8, against measured victim queueing:**
- The replay reproduces the measured victim queue mean and P95 in every block. Across all 114 gateway runs the Pearson
  correlation on log1p(mean queue) is 1.00, and R2-F s96 gives 7,052 ms replayed against 7,061 ms measured.
- The gateway therefore behaves exactly like a global FCFS queue with 8 slots. Given the arrivals and the hold times,
  it adds no queueing of its own.

## 1. Slot-time results

### R1 at L\* = 200 (gateway; means over 5 seeds)

| Block / arm | Competitor hold, mean / P95 (s) | Competitor slot-seconds | Slot-seconds per 1k authorized tokens | Total slot demand / (8 × 120 s) | Mean occupancy | Time at 8/8 | Saturation episodes: count / mean / max (s) | Victims arriving during saturation | Victim queue P95 (ms) |
|---|---|---|---|---|---|---|---|---|---|
| A/A short, attack | 1.40 / 1.46 | 263 | 10.9 | 0.43 | 3.41 | 2.7% | 18.6 / 0.19 / 0.67 | 4.0% | 122 |
| A/A short, control | 1.42 / 1.53 | 266 | 11.1 | 0.44 | 3.46 | 3.1% | 20.4 / 0.19 / 0.72 | 4.0% | 147 |
| **Decode 64/256, attack** | **5.33 / 5.42** | **400** | **16.7** | **0.57** | **4.52** | **11.2%** | **35.0 / 0.38 / 1.37** | **10.2%** | **697** |
| Decode, control (short) | 1.41 / 1.49 | 265 | 11.0 | 0.43 | 3.45 | 2.7% | 20.0 / 0.16 / 0.55 | 3.1% | 20 |
| Prefill 1024/32, attack | 0.98 / 1.23 | 23 | 0.93 | 0.18 | 1.46 | 0.0% | 0.6 / 0.02 / 0.04 | 0.2% | 0 |
| Prefill, control (short) | 1.41 / 1.49 | 268 | 11.0 | 0.44 | 3.47 | 3.0% | 20.8 / 0.17 / 0.54 | 3.1% | 32 |

- **Equal tokens do not mean equal slot-time.**
  - Decode-heavy work used **1.51×** the competitor slot-seconds of the token-matched short control (16.7 vs 11.0
    slot-s per 1k authorized tokens).
  - Prefill-heavy work used **0.09×**: 23 requests of about 1 s each.
  - That ordering matches the R1 outcomes: decode was supported, prefill negative.
- **Victims queue only while all 8 slots are busy.** Victims that arrived when fewer than 8 slots were busy had a mean
  queue of at most 1 ms in every R1 gateway block (0 in all but one: 0.96 ms in the prefill control). This does not hold under
  overload. In R2-F s96 and s128 a FCFS backlog persists: a victim that arrives at a moment when fewer than 8 slots are
  busy still waits behind earlier queued requests (mean 7–22 s at s96). "In-flight < 8 at arrival" is therefore only a
  valid "no-wait" indicator when no backlog has formed. Those that arrived during saturation waited 240–770 ms on average (decode attack:
  771 ms).
- **The decode attack saturates the gateway in short episodes.** It held all 8 slots about 4× as often (11.2% of the
  time, against 2.7%), in episodes averaging 0.38 s and lasting at most 1.4 s. About 10% of victims arrived during
  one, against about 3% in the short control.

### R2 sweeps (attack arms, means over 3 seeds; descriptive)

| Point | Slot-s per 1k tokens | Slot demand | Time at 8/8 | Victims during saturation | Victim queue P95 (ms) | FCFS estimate of victim queue P95 at cap 16 / cap 32 (ms) |
|---|---|---|---|---|---|---|
| F s96 | 8.4 | 1.22 | 97.9% | 96% | 25,636 | 162 / 0 |
| F s128 | 6.5 | 0.99 | 90.4% | 91% | 3,119 | 62 / 0 |
| F s192 | 4.8 | 0.78 | 46.9% | 52% | 1,028 | 0 / 0 |
| F s256 | 3.6 | 0.64 | 22.6% | 25% | 728 | 0 / 0 |
| F s512 | 2.2 | 0.48 | 10.1% | 11% | 330 | 0 / 0 |
| F s1024 | 1.1 | 0.33 | 2.1% | 3.6% | 173 | 0 / 0 |
| F s3584 | 0.55 | 0.27 | 2.5% | 3.6% | 28 | 0 / 0 |
| B s64 | 11.5 | 0.73 | 30.7% | 34% | 575 | 0 / 0 |
| B s1024 | 11.0 | 0.71 | 30.8% | 32% | 3,396 | 0 / 0 |
| B s2048 | 11.0 | 0.70 | 16.9% | 17% | 2,649 | 0 / 0 |

- **Fixed-output sweep (R2-F).** Slot-time per authorized token falls with request size, because the 32-token decode
  cost is paid once per request. Saturation follows: about 98% of the time at 8/8 at s96, about 2% from s1024 upward.
- **Balanced sweep (R2-B).** Slot-time per authorized token is constant at about 11 slot-s, so saturation stays near
  31%. Queue delay still grows with request size, because each saturation episode lasts longer: mean 0.11 s at s64,
  0.59 s at s1024, 0.91 s at s2048, with maxima of 0.4 s, 2.6 s and 7.1 s. Episode length, not only saturation
  frequency, sets the victim's wait.
- **Across all 114 gateway runs**, the Spearman correlation of victim queue P95 with each candidate predictor is:

  | Predictor | Spearman ρ |
  |---|---|
  | Victims arriving during saturation | **0.92** |
  | Time at 8/8 | 0.88 |
  | Slot demand fraction | 0.83 |
  | Longest saturation episode | 0.73 |
  | Slot-seconds per 1k tokens | 0.28 |

  Slot-seconds per token alone explains little, because the competitor's arrival rate also changes with request size.
- **Direct path (R3).**
  - The same traces reach backend concurrency of up to 30 (R2-F s96), with no queueing anywhere, since engine waiting
    is 0.
  - Hold times are slightly longer than through the gateway: s96 0.90 vs 0.81 s.
  - The cap-16/32 FCFS estimates should therefore be read as lower bounds.

## 2. Statistical audit of the R1 decode result (post-hoc exploratory)

All 5 seeds are reported; none was selected or removed.

| Seed | Victims | Attack: user TTFT P50 / P95 / P99 (ms) | Victims queued > 500 ms (attack) | Attack time at 8/8 | Victims during saturation | Longest episode (s) | P95 ratio | Mean ratio | P50 ratio | Within-seed bootstrap 95% interval of attack P95 (ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| 42 | 99 | 94 / 178 / 243 | 1 | 6% | 3% | 1.01 | 1.04 | 1.08 | 1.03 | 155–214 |
| 43 | 110 | 99 / 1,324 / 3,478 | 9 | 15% | 14% | 2.45 | 6.33 | 2.46 | 1.05 | 439–3,080 |
| 44 | 111 | 94 / 1,183 / 1,638 | 11 | 10% | 14% | 1.02 | 6.39 | 2.00 | 1.05 | 374–1,370 |
| 45 | 106 | 88 / 1,022 / 2,348 | 7 | 11% | 13% | 1.04 | 6.28 | 2.11 | 1.04 | 241–1,690 |
| 46 | 115 | 97 / 300 / 877 | 2 | 14% | 7% | 1.35 | 1.77 | 1.34 | 1.11 | 177–558 |

The control arms (short 64/64) had P95 of 163–209 ms, at most 2 victims queued over 500 ms per seed, and spent 1–4%
of the time at 8/8.

- **Slot demand is not what varies between seeds.** Every attack seed used 0.56–0.58 of capacity, with mean occupancy
  4.4–4.6.
- **Chance overlap is what varies.** Victim arrivals coincided with saturation episodes for 3% (seed 42) to 14% (seeds
  43, 44) of victims.
- **P95 is a threshold statistic here.** With 99–115 victims, P95 sits at roughly the 6th-largest value.
  - When at least about 7 victims are queued more than 500 ms (seeds 43–45), P95 falls in the queued tail at about
    1.0–1.3 s, giving a ratio of about 6.3.
  - With 1–2 such victims (seeds 42, 46), P95 stays in the unqueued body, giving 1.0–1.8.
  - That threshold, not two physical regimes, is what splits the seeds.
- **The within-seed bootstrap shows P95 is unstable.** Seed 43's attack P95 ranges over 439–3,080 ms when victims are
  resampled.
- **More stable statistics show a consistent but smaller effect:**
  - mean user TTFT ratio 1.80 (1.08–2.46), with log SD across seeds 0.34 against 0.87 for the P95 ratio;
  - victims over 500 ms: 6.2% in the attack arm against 0.5% in the control;
  - median ratio about 1.06: the effect is entirely in the tail.
- **On the direct path the same traces give** a mean ratio of 1.07, a P95 ratio of 1.00 (log SD 0.045), and 0.7% of
  victims over 500 ms.
- **The A/A noise floor depends on the trace.** In seed 44, both A/A arms have 7–8% of victims over 500 ms, because
  the A/A pair replays the same trace and a bursty trace affects both arms equally. The A/A pair therefore does not
  sample variation between traces.

## 3. Interpretation, for review only

- **Mechanism.** Concurrency-slot occupancy explains the observed victim TTFT amplification under the 8-slot FCFS
  gateway, within the limits of this exploratory analysis:
  - a token budget does not bound slot-time;
  - workloads that hold slots longer saturate the cap in short episodes;
  - victims arriving inside an episode wait for a free slot.
- **Fragility.** The P95 primary endpoint magnifies this into a near-binary per-seed outcome. Any confirmatory
  follow-up should use a tail-mass or mean endpoint, more victims per run, and independently sampled traces. This
  motivates Protocol v5 (`docs/PROTOCOL_V5_DRAFT.md`).

## Erratum (2026-11-23; this analysis stays POST-HOC EXPLORATORY, with no numbers changed)

- **Engine queue.** The "Unavailable" row is correct only *per request*. v4 did record the engine-global mean engine
  queue: the per-arm sum/count deltas of vLLM `request_queue_time_seconds` in each run's `metrics_summary.json`.
  - That mean is ≤ 0.012 ms in every R1/R3 arm (measured, engine-global).
  - Bucket deltas were not recorded.
  - Semantics: `docs/PROTOCOL_V5_DRAFT.md` §5.2.
- **Cap 16/32 estimates.** They used gateway C = 8 runs only. The "3–11% longer direct-path holds" remark is a
  qualitative bias direction from R3 direct runs, which are de-facto C ≥ 16 data. It was not used numerically, and
  v5's frozen predictions exclude it (`docs/PROTOCOL_V5_DRAFT.md` §3.4).
