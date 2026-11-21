# QuotaShift — Self-hosted GPU results (Phase 5, first live run)

**Status:** real GPU measurements (`synthetic_backend: false`), 5 matched seeds per scenario.
These are the project's first non-mock attack-effect numbers. Reported per ADR-Q08/Q11, negatives included.

## Locked configuration (identical across every scenario and its control)

- **Target:** self-hosted vLLM `0.17.1`, serving `Qwen/Qwen2.5-7B-Instruct`
  (revision `a09a35458c702b33eeacc393d103063234e8bc28`), `max_model_len = 4096`,
  private endpoint `192.168.86.173:8000` (RFC1918).
- **Gateway / serving config:** fixed FCFS, fixed hard caps, token-ledger isolation — not varied.
  The only variable is the workload scenario.
- **Metric:** victim `ttft_p95`, attack ÷ matched control, computed **per matched seed**; warm-up excluded;
  completed vs timed-out victim requests separated.
- **Pre-registered threshold:** 1.5× (fixed before runs). **Budget tolerance:** 0.05.
- **Seeds / reps:** A2–A5 seeds 42–46 (5 reps); A1 seeds 42–61 (20 reps, re-run to resolve a marginal result).
- **Code commit:** `4a829d7`.
- **Run dates:** 2026-11-20 — initial 5-rep sweep 12:22:55Z–13:36:31Z (1h13m36s);
  A1 20-rep re-run 23:35:19Z–00:17:07Z (41m48s). Total GPU wall-clock ≈ 1h55m.

## Headline results

| Scenario | Control | Mean ratio | Median | 95% bootstrap CI | Attack success | Verdict |
|---|---|---|---|---|---|---|
| A1 burst_arrivals | uniform_arrivals | **1.59×** | 1.58× | [1.53, 1.65] | 70% (14/20) | crosses threshold |
| A2 prefill_heavy | matched_total_short | **3.16×** | 3.14× | [2.37, 3.94] | 100% (5/5) | **crosses — strongest** |
| A3 decode_heavy | matched_total_short | **1.06×** | 1.11× | [0.87, 1.26] | 0% (0/5) | negative |
| A4 mixed_shapes | homogeneous_mixture | **1.35×** | 1.26× | [1.23, 1.47] | 20% (1/5) | negative |
| A5 stateful_sequence | shuffled_phase_order | **1.28×** | 1.39× | [1.08, 1.46] | 20% (1/5) | negative |

All metrics are victim `ttft_p95`. Ratios are per-seed attack/control; mean/median/CI are over the seeds.

**A1 was re-run at 20 seeds (42–61)** to resolve the marginal 5-seed result. The effect held and tightened:
mean 1.59×, median 1.58×, 95% CI **[1.53, 1.65]** — now entirely above the 1.5× threshold — success 70% (14/20).
All 20 budgets matched exactly (rel_delta 0.0), zero attack-arm timeouts. A1 is a real, consistent ~1.6× effect,
not noise. Report in `reports/live/a1_burst_arrivals_r20/`. The other four scenarios remain at 5 seeds.

## Integrity checks (all pass)

- **Matched budgets:** every seed matched within tolerance on all required dimensions.
  Max `total_tokens` relative delta — A1 0.000, A2 0.0011, A3 0.0038, A4 0.0010, A5 0.000.
  A2/A3 trade input-length for request-count while holding total tokens (gated dimension), as designed (ADR-Q10).
- **No GPU errors / exit 0** for all 5 scenarios.
- **Victim timeouts in every attack arm: 0.** (See the A2 note below for control-arm timeouts.)
- Figures per scenario: `reports/live/<scenario>/figure_victim_latency.png`, `figure_degradation_ratio.png`.

## Per-scenario durations (wall-clock)

| Scenario | Start (Z) | Done (Z) | Duration |
|---|---|---|---|
| A1 | 12:22:55 | 12:33:09 | 10m14s |
| A2 | 12:33:09 | 12:45:43 | 12m34s |
| A3 | 12:45:43 | 12:56:14 | 10m31s |
| A4 | 12:56:14 | 13:06:32 | 10m18s |
| A5 | 13:06:32 | 13:36:31 | 29m59s |
| **Total** | 12:22:55 | 13:36:31 | **1h13m36s** |

## Interpretation

- **A2 prefill-heavy is the clear, robust effect** (3.16×, 100%, CI well clear of 1.5×): concentrating the
  matched token budget into few long-prefill requests degrades victim TTFT far more than spreading the *same
  total tokens* across many short requests. Note the matched control (`matched_total_short`) instead blows up
  victim **e2e** (control-arm victim timeouts 0–3/seed, e2e_p95 ≈ 60s) because it floods the queue with ~228
  tiny requests — i.e. the two shapes hurt *different* victim metrics at equal token budget. The TTFT finding
  stands; the e2e asymmetry is worth reporting alongside it, not hiding.
- **A1 burst arrivals (1.59×, 70%)** — at 20 seeds this is a real, consistent effect: CI [1.53, 1.65] clears
  the threshold with room to spare. (At 5 seeds it looked marginal, 1.58× with CI [1.45, 1.79]; the re-run
  confirmed it rather than dissolving it.)
- **A3 / A4 / A5 are negatives** under matched budgets: decode-heavy, mixed-shape, and stateful-sequence timing
  do not degrade victim TTFT beyond their matched controls at these budgets. A3's control (many short requests)
  actually inflates victim e2e more than the attack. Reported as negatives per the pre-registration.

## Reproduce

```
uv run quotashift target use selfhost    # vLLM 0.17.1 @ 192.168.86.173:8000
uv run quotashift experiment experiments/<scenario>.yaml --reps 5 --live --out reports/live/<scenario>
```

Schedule hashes (`schedule_sha256`, deterministic, wall-clock-independent):

| Scenario | schedule_sha256 |
|---|---|
| a1_burst_arrivals | `a0f2380a189fecd7d9256d4ff37280b14ccc4f518a0535740be369a344736798` |
| a2_prefill_heavy | `2f84df2ce943b2bc7aa6335bb7f11caab88d7ff23fdaa67650eaf35a6c848b5a` |
| a3_decode_heavy | `9c2645961cf004bfcc63ee810f6bc86c27ff37285fb51645617d5467025c9ad4` |
| a4_mixed_shapes | `0d9bb522873974baeb456a93307b32bef764a277055c398e69ce08b1d470d8ad` |
| stateful_sequences | `d5f2ab6f07799a4cc42a2057955cecbf98931f49c6d344da8738c0fd3534f9e4` |

## Caveats

- **Seed counts: A1 n=20, A2–A5 n=5.** A1 is now well-resolved. A4/A5 means sit below 1.5× at 5 seeds with
  non-trivial spread; more reps would tighten the negatives but that is additional GPU time — not run without
  owner approval.
- Single target, single model, single hardware instance. No cross-target pooling (ADR-Q09).
- `ttft_p95` is the pre-registered metric; the e2e asymmetry noted for A2/A3 is a secondary observation.
