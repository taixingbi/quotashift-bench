# X2 G0 offline readiness package (g0m0, g0m1)

**Prepared:** 2026-11-27, 17:58–19:00 EST. Offline only.
- No AWS GPU was started, AWS was not modified, and Cost Explorer was not called.
- gpu-node-2 was not contacted.
- No frozen artifact changed: pins v5, X2, A2, A3 and X1/A1 all match.
- The no-interim-looks rule holds: the cross-platform X2 analysis was **not** run.

**Companion documents:**

| Document | Contents |
|---|---|
| `docs/X2_G0_RUNBOOK.md` | exact g0m0 and g0m1 commands |
| `docs/X2_AWS_EVIDENCE_AND_CLEANUP.md` | AWS evidence integrity and the cleanup proposal |
| `reports/x2_g0/G0_OFFLINE_MATRIX.json` (+ `.log`, `SHA256SUMS`) | the offline matrix |

## 1. Readiness summary

| Area | Status | Evidence |
|---|---|---|
| Repository + pins | clean; v5, X2, A2, A3, X1/A1 match | `pin_*.py --check` |
| Tests | **664 passed, 1 skipped** (the opt-in real-GPU test); ruff and mypy clean | full suite, 2026-11-27 |
| G0 launch template | `scripts/x1_g0_server.sh` uses the vLLM 0.17.1 env `vllm0171`, the pinned revisions (Qwen `a09a3545…`, Mistral `c170c708…`), and exactly the G1 task-definition flags (fp16, max-model-len 4096, gpu-mem 0.80, prefix caching, prompt-tokens-details, max-num-seqs 256, max-num-batched-tokens 2048). g0m1 adds `--tokenizer-mode/--config-format/--load-format mistral`, the same as the G1 Mistral overlay. Target profiles `x2-g0-qwen` / `x2-g0-mistral` agree | `tests/unit/test_x2_g0_readiness.py` (parity tests) |
| Network (B-X2-1) | **blocked**: wired Ethernet at both ends is required. The pre-Ethernet Wi-Fi baseline is recorded | `scripts/x2_network_readiness.py` (read-only), runbook §1 |
| Host hygiene (B-X2-2) | owner actions listed (k3s agent, unattended-upgrades/apt timers, desktop session); exact read-only verification commands are in the runbook | runbook §1 |
| Qualification path | mock g0m0 and g0m1 **pass** (synthetic, plumbing only). Live refusals verified: no token; no TTY confirmation; existing record (no retry); pins not matching; dirty tree; mock output inside the repository | `x2_qualify.py --mock`; tests |
| Calibration A / main path | frozen drivers, with the G0 snapshot transport over ssh (`QUOTASHIFT_X2_SSH_HOST` required, refused otherwise). The offline freezes pass every frozen gate for every hypothetical hold and rate except 5 tok/s main (§3) | matrix; `test_x2_pipeline.py` |
| A3 for g0m1 | routed through `scripts/x2_a3.py` (verified); Qwen keeps the frozen counter. **New non-frozen guard** `scripts/x2_counter_check.py` before every phase pin | §4 |

## 2. Qualification startup and failure handling (G0, frozen behaviour)

- **Server start** (`x1_g0_server.sh start <p>`):
  - refuses if a `vllm serve` is already running;
  - exits 4 if the server dies during startup, printing the log tail;
  - exits 5 if it is not healthy within 1,800 s;
  - writes `~/x1/launch_<p>.json` with the startup time;
  - uses `HF_HUB_OFFLINE=1`, so the model snapshot must already be cached on the host.
- **Qualification** (`x2_qualify.py --live`):
  - needs `QUOTASHIFT_APPROVED=x2_qual_<p>`, a passing `pin_x2 --check`, no existing `QUALIFICATION.json`, a clean
    tree and an interactive "yes" on a TTY. The owner runs it from a terminal;
  - checks the active target's model and name;
  - writes the raw segments first, then `QUALIFICATION.json`;
  - exits 0 on pass and 4 on fail. A fail makes the platform inadmissible, and it is never re-run.
- **Gap, procedural.** If qualification crashes before writing `QUALIFICATION.json`, the code guard does not stop a
  second attempt. The rule is still "once". A crashed run needs an owner decision, as on X1, and a crash must never
  be re-run silently.

## 3. A2 / A3 compatibility and known-risk matrix

**How the matrix was built.** Twelve hypothetical isolated hold times (0.8–5.0 s) give **40 distinct grid rates**
(5–1035 tok/s). Each was evaluated as a hypothetical low rate on **both** G0 platforms, with the frozen generators and
the frozen offline gates; whitespace stand-in counter for Phases B and C. No hold time or rate is chosen here.

| Check (per platform, over 40 rates × 136 seed-arms) | g0m0 | g0m1 |
|---|---|---|
| calA frozen offline freeze at 12 holds | 12 / 12 pass | 12 / 12 pass |
| A2 main frozen offline freeze (all frozen gates) | **39 / 40** (refused only at **5 tok/s**) | **39 / 40** (only 5 tok/s) |
| original-law main freeze | refused at 5, 10, 15 tok/s | refused at 5, 10, 15 tok/s |
| A2 coverage, attack | 5,382 / 5,440 (all 58 misses at 5 tok/s) | same |
| A2 coverage, control; one-per-stratum; count, token, id/prompt/shape conservation vs original; victims equal and paired; budget matched; deterministic | 5,440 / 5,440 each | same |
| A/A independent (X2b) | 1,920 / 1,920 | 1,920 / 1,920 |

**Decode requests below four.**
- At the grid rates, **only 5 tok/s** gives fewer than four decode requests (N_D = 2), and only 5 tok/s leaves A2
  unable to guarantee the coverage gate. 10 tok/s gives N_D = 4, which is guaranteed.
- Analytic check over every rate 5–1000: min(N) ≥ 4 everywhere except 5 tok/s.
- The predicted-ρ rule would select 5 tok/s only for hold ≳ 3.59 s. G1 (L4) measured 3.64–3.67 s and still
  selected 10, because the measured ρ was lower than predicted.
- An RTX 3090 is expected to have a shorter hold, giving higher grid rates. That is an expectation, not a measurement.

**A3 (g0m1).** The sequential counter was run against the pinned-tokenizer mock, with the trailing-EOS artifact
injected on concurrency:

| Run | Result | /tokenize calls | Guard trips / injections / max in flight |
|---|---|---|---|
| calA, hold 1.35 s | 36/36 exact | 57,432 | 0 / 0 / 1 |
| calA, hold 2.0 s | 36/36 exact | 38,280 | 0 / 0 / 1 |
| calA, hold 3.0 s | 36/36 exact | 25,368 | 0 / 0 / 1 |
| A2 main, 10 tok/s | 136/136 exact | 62,736 | 0 / 0 / 1 |
| A2 main, 50 tok/s | 136/136 exact | 79,360 | 0 / 0 / 1 |
| A2 main, 140 tok/s | 136/136 exact | 115,728 | 0 / 0 / 1 |
| A2 main, 295 tok/s | 136/136 exact | 180,192 | 0 / 0 / 1 |
| frozen 16-worker counter, calA hold 1.35 s | **refused**, as on g1m1 | — | 406 injections |

- Counter class under A3: g0m1 → `SequentialMistralTokenizer`; g0m0 → the frozen `VllmTokenizer`, 16 workers.
- **Live overhead.** On g1m1, the live sequential freeze of 21,528 calls took about 77 s, roughly 3.6 ms per call.
  At G0 rates of 50–300 tok/s, a freeze or a pre-send pass would take about 5–11 min. The trace is larger at higher
  rates.

**Known risks**

| # | Risk | Likelihood | Consequence | Mitigation / decision |
|---|---|---|---|---|
| R1 | G0 selects **low = 5 tok/s** | low (needs hold ≳ 3.6 s) | A2 main freeze refused (X2a/c/d N_D = 2) | stop before main; a separate owner decision (A2 §5); never substitute a rate |
| R2 | g0m1 frozen **without** A3 (direct frozen driver) | operator error | refusal, or (if the artifact is consistent) prompts 1 token short in generation | runbook uses `x2_a3.py` only; `x2_counter_check.py` before every pin; a stage without A3 on an A3 freeze fails closed (`FrozenTraceMismatch`) |
| R3 | Sequential `/tokenize` alongside generation (untested live) | unknown | refused freeze or block (A3 guard), never a miscount | freezes run on an idle server; pre-send runs before the block's traffic |
| R4 | Network still wireless, or noisy host | — | Q0/Q1 fail → platform inadmissible | B-X2-1 required; B-X2-2 recommended; qualification decides |
| R5 | Qualification crash without a record | low | the "once" rule is only procedural | owner decision; never silently re-run |
| R6 | Model snapshot not cached (`HF_HUB_OFFLINE=1`) | — | server exit 4 at start | pre-check in runbook §1 |
| R7 | Main uses the original law vs A2 | decision | original law refused at ≤ 15 tok/s; A2 is platform-agnostic | **decision needed:** use A2 for G0 main, as on g1m0/g1m1 (recommended, for comparability) |

## 4. Local execution path (checked offline)

- **Operator terminal.** Each step uses the frozen driver, or `x2_a3.py` for g0m1, with
  `QUOTASHIFT_TARGET=x2-g0-*` and `QUOTASHIFT_X2_SSH_HOST=gpu-node-2`. Live drivers confirm on a TTY.
- **Block execution.** `v5_stage.run_block` launches `python -m quotashift.cli experiment … --live` with the parent
  environment. Under `x2_a3.py`, that subprocess inherits `QUOTASHIFT_TOKEN_COUNTER=X2-A3`, the same path that ran
  live on g1m1.
- **Outputs.**
  - Raw outputs go to git-ignored `reports/x2/g0m*/` and `results/x2_g0m*`, so the tree stays clean mid-stage.
  - The readiness JSON under `reports/x2/readiness/` is tracked and is committed before qualification.
- **Mock paths** refuse output inside the repository. The offline matrix writes only to a git-ignored temp dir that
  is then deleted; no canonical `experiments/x2/g0m*` file exists.

## 5. Estimated time and cost per remaining platform

Durations are from the G1 actuals: qualification 73 min; calA 84 min; main 315–317 min; freezes ≤ 5 min.

| Platform | Steps | Wall clock | GPU-h (owned 3090) | AWS cost |
|---|---|---|---|---|
| g0m0 | readiness + hygiene 0.3 h, server start, qualification 1.2 h, calA freeze/pin 0.2 h, calA 1.4 h, rates + A2 files/validation 0.2 h, main freeze/pin 0.2 h, main 5.3 h, evidence 0.2 h | **≈ 9.0 h** | ≈ 8.5 | $0 |
| g0m1 | as g0m0, plus server restart and A3 sequential counting (≈ +0.2–0.4 h) | **≈ 9.3 h** | ≈ 8.8 | $0 |
| Both, sequential | | **≈ 18–19 h**, from ~2026-11-29 after Ethernet | ≈ 17 | AWS idle ≈ $1.5/day unless the cost-bearing stack is removed |

**Critical path:** gpu-node-2 available (~11-29) → Ethernet (B-X2-1) → g0m0 → g0m1 → the cross-platform analysis
(own approval).

## 6. Operations that need owner approval when Ethernet is ready

1. **Owner actions:** wired Ethernet at both ends (B-X2-1); host hygiene (B-X2-2); confirm the cached model
   snapshots.
2. Run the read-only readiness check and commit its record. No token; it is the owner's go to contact gpu-node-2.
3. **g0m0:** server start plus `x2_qual_g0m0`; `x2_freeze_calA_g0m0`; `x2_cal_g0m0`; then, conditionally
   (low ≥ 10, every offline A2 check passes), `x2a2_freeze_main_g0m0` and `x2a2_main_g0m0`.
4. **g0m1:** server restart to Mistral plus `x2_qual_g0m1`; `x2_freeze_calA_g0m1`; `x2_cal_g0m1`; then
   conditionally `x2a2_freeze_main_g0m1` and `x2a2_main_g0m1`. Every freeze and stage goes through `x2_a3.py`.
5. **Decision (R7):** confirm A2 for G0 main.
6. **Decision (R1), if it arises:** a platform that selects 5 tok/s.
7. **Separately:** the AWS cleanup (`destroy`, targeted or full) after the off-machine backup; the frozen
   cross-platform analysis once all admissible platforms are complete.
