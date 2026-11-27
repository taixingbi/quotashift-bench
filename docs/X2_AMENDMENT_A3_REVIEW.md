# X2 Amendment A3: review package (DRAFT, offline only)

**For:** owner review of `docs/PROTOCOL_X2_AMENDMENT_A3.md`.

**Status (updated 2026-11-27, 08:58 EST):** the owner approved the A3 freeze and the runner dispatch change.
- Both are done: `experiments/x2_a3/AMENDMENT_A3_SHA256.json`, created 13:58:45Z.
- The pinned A3 code is byte-identical to the code validated in run 2 (`ef095ba`).
- Nothing has been deployed or measured, and the runner image has not been rebuilt.

**Contents:**

| § | Section |
|---|---|
| 1 | Scientific validity review |
| 2 | Frozen-diff report |
| 3 | Offline token-counting validation matrix |
| 4 | Concurrency: proven offline vs unverified live |
| 5 | Performance overhead |
| 6 | Reproducibility and provenance |
| 7 | GO / NO-GO |

## 1. Scientific validity review

| Question | Finding |
|---|---|
| Does A3 change what is measured? | **No.** Generation requests are unchanged. The gate's reference quantity (the prompt tokens the engine prefills) equals sequential `/tokenize` for 212/212 prompts at concurrency 1/16/32 (diagnostic boot 2). A3 makes the counter report that quantity. |
| Does A3 change any prompt, schedule or budget? | **No.** The calA traces from the A3 counter hash identically (`a5095c7c…`) to those from a correct 16-worker counter, the in-process SentencePiece count, and a second A3 run. Schedules are identical across counters. Request counts, authorized tokens and `tokenized == planned` are conserved for 36/36 scenario-seeds. |
| Is any gate relaxed? | **No.** `calibrate_trace`, exact `verify_trace`, the context, budget and coverage gates, frozen-trace equality and all stage stops run unchanged. A3 adds two fail-closed checks and never corrects a count. |
| Does A3 touch other platforms or results? | **No.** Non-Mistral models get the frozen class itself (tested). The driver refuses g0m0/g1m0. g1m0 results and records are untouched, and every earlier manifest verifies. |
| Is the selection of A3 outcome-driven? | **No.** It responds to a measured tooling failure before any g1m1 calA or main data existed. It was chosen before seeing any outcome, its trigger is recorded, and the rate grid, the rule, the threshold (1.25) and the Holm family are fixed. |
| Is the mechanism proven? | **No.** The trailing-EOS race in vLLM's `/tokenize` path is a hypothesis. A3 does not depend on it: it relies only on the observed facts that sequential counts are exact and that generation usage equals them. |
| Is a requalification needed? | **No.** Serving configuration, model, weights and flags are unchanged, and qualification never used `/tokenize` counts. |
| Residual scientific risk | If sequential `/tokenize` were also affected by concurrent generation traffic (untested live, §4), A3 refuses the freeze or block. The cost is lost time, never biased data. |

## 2. Frozen-diff report

The draft commits change these paths relative to `990774e` (the generation-path diagnostic):

| Path | Change | Pinned by any manifest? |
|---|---|---|
| `src/quotashift/workload/tokenize_a3.py` | new | no (A3 candidate) |
| `src/quotashift/workload/__init__.py` | empty → env-gated hook (6 lines) | no (A3 candidate) |
| `scripts/x2_a3.py`, `scripts/pin_x2_a3.py`, `scripts/x2_a3_validate.py` | new | no (A3 candidate) |
| `docs/PROTOCOL_X2_AMENDMENT_A3.md`, `docs/X2_AMENDMENT_A3_REVIEW.md` | new | protocol: A3 candidate |
| `tests/unit/test_x2_a3.py` | new | no |
| `tests/unit/test_x2_aws_orchestration.py` | one stale sub-case removed. It assumed `experiments/x2/g1m1/` did not exist, which has been false since `147879c` and failed on HEAD before A3. | no |
| `.gitignore` | ignore `reports/x2_a3/ref/`, the local copy of the gated tokenizer model | no |
| `docs/DECISIONS.md`, `docs/KNOWN_LIMITATIONS.md` | appended entries | no |

**Intersection of the changed paths with every pinned file list:** v5 (73 files), X2 Freeze 1 (29 + v5 dependencies),
A2 (8), X1 (19) and A1 (9) all give **∅**.

| Earlier manifest | sha256, first 16 hex characters |
|---|---|
| v5 `FROZEN_SHA256.json` | `e8aa80835c2f99a5` |
| X2 `FROZEN_SHA256.json` | `b50334681adf26b6` |
| A2 `AMENDMENT_A2_SHA256.json` | `def1e467f9a7f8b7` |
| X1 `FROZEN_SHA256.json` | `39ae158cb36389fb` |
| A1 `AMENDMENT_A1_SHA256.json` | `d99bdbae58b24a3e` |
| g1m0 phase pins, X2 | `6f13238f1402ee7c` |
| g1m0 phase pins, A2 | `b92a82b231e9eb6b` |

None is rewritten. The `--check` result of each pin script is:

| Script | Result |
|---|---|
| `pin_v5.py` | all frozen artifacts match |
| `pin_x2.py` | X2 frozen artifacts match |
| `pin_x2_a2.py` | A2 artifacts match |
| `pin_x1_amendment.py` | A1, X1 Freeze 1 and v5 pins all match |

The behavioural change, rather than a byte change, is the call-time rebinding of
`quotashift.workload.tokenize.VllmTokenizer`. It happens only in processes started with
`QUOTASHIFT_TOKEN_COUNTER=X2-A3`, and only for Mistral. A2's `a2_loader` uses the same pattern for
`quotashift.scenario.load_scenario`.

## 3. Offline token-counting validation matrix

**Run 2 (authoritative):** `reports/x2_a3/A3_OFFLINE_VALIDATION.json` (+ `.log`), at commit `ef095ba`.

**Run 1:** kept unchanged as `A3_OFFLINE_VALIDATION_run1.json` / `.log`, at commit `e2cd491`. Run 1 gave the same
result on every row except one expectation that I had specified wrongly (see the note under the table).

**Mock server:** `/tokenize` returns BOS + SentencePiece encode from the pinned `tokenizer.model.v3` (sha256
`37f00374…`). In the g1m1 diagnostics, live sequential `/tokenize` matched these ids for 464 + 212 texts. Artifact
injection modes:

- `tokenize`: a trailing id 2 whenever another `/tokenize` is in flight;
- `any`: a trailing id 2 whenever any other request is in flight.

The scope is all **36 g1m1 calibration-A scenario-seeds**: 6 grid files and 6 rerun files × seeds 22000–22002, the
committed YAMLs, digest `5b350fbb`.

| Row | Counter | Mock | Expected | Result |
|---|---|---|---|---|
| F16-fault | frozen, 16 workers | `tokenize` artifact | refused (reproduces live) | **refused** after 241 calls: `3 request(s) did not calibrate … ('v02-benign-22000-000009', 47, 48)`; 218 injections, max in flight 7 |
| F16-clean | frozen, 16 workers | clean | pass | **pass**, 36/36; 21,528 calls; digest `a5095c7c…` |
| A3-fault | A3 sequential | `tokenize` artifact | pass, 0 trips | **pass**, 36/36; 21,528 calls; 0 injections; 0 guard trips; max in flight 1; digest `a5095c7c…` |
| A3-clean, A3-clean-2 | A3 sequential | clean | pass, identical | **pass** ×2; digest `a5095c7c…` both times |
| SP-direct | in-process SentencePiece | none (no HTTP) | identical traces | **pass**; digest `a5095c7c…` |
| Schedules | all of the above | — | identical | **identical** schedule digest across counters; the frozen freeze also refuses any calibration-induced schedule change |
| CONSERVATION | A3-fault traces vs raw plan | — | conserved | **36/36**: request counts, authorized tokens (in + max out), tokenized input == planned input, seeds == YAML range |
| RT-presend | fresh A3 counter resolved as at `local.py:153` | `tokenize` artifact | 36/36 | **36/36** frozen-trace match + exact `verify_trace` (attack budget view and control); 21,528 calls; 0 trips; class `SequentialMistralTokenizer` |
| A3-ext | A3 sequential, with 4 threads of concurrent `/v1/completions` | `any` artifact | fail closed | **refused at call 1**: `A3: /tokenize returned a trailing EOS …`; 1 guard trip; no count accepted |
| A3-quiet | A3 sequential | `any` artifact, no other traffic | pass | **pass**, 36/36; 0 injections |
| MAIN-hyp 10, 25, 55, 95, 140 tok/s | A3 sequential | `tokenize` artifact | tokenization exact | **pass**: full frozen A2 main freeze, 136 scenario-seeds each; 0 trips; 0 injections; conservation 136/136 |
| MAIN-hyp 5 tok/s | A3 sequential | `tokenize` artifact | tokenization exact | freeze **refused by the A2 coverage gate** (see note); tokenization-only 136/136 exact; 0 trips; 0 injections |

These are HYPOTHETICAL main files, written to a git-ignored temp dir. This is not a rate selection; g1m1 RATES.json
does not exist.

**Note on the run-1 expectation.** Run 1 required the whole frozen A2 main freeze to pass at every hypothetical grid
rate. At **5 tok/s** the freeze was refused by the **A2 arrival-coverage gate**:

`x2_g1m1_X2a_decode_vs_short_low_C8 attack seed 23002: first 0.160, last 0.613`

It had 0 guard trips and 0 injected artifacts. This is the documented A2 property: N_D = 2 at 5 tok/s, so the gate
passes with p = 0.25 per seed-arm (`docs/PROTOCOL_X2_AMENDMENT_A2.md` §5; `docs/X2_AMENDMENT_A2_REVIEW.md`, table at
line 122). It has nothing to do with A3.

Run 2 therefore judges MAIN-hyp on tokenization. Where the freeze refuses on another gate, it calibrates and exactly
verifies every scenario-seed directly with the A3 counter, and it separately requires that any refusal is the
coverage gate. **The A2 risk at 5 tok/s still stands for g1m1.** Rate selection follows the frozen rule after calA.
If it selects 5 tok/s, the A2 main freeze will refuse on coverage, and A3 does not change that.

## 4. Concurrency: proven offline vs unverified live

| Claim | Status |
|---|---|
| The A3 counter never has more than one `/tokenize` in flight | **Proven** by construction (no executor) and measured in the mock: max in flight = 1 in every A3 row |
| Under the observed artifact (`/tokenize`-to-`/tokenize` concurrency), A3 counts exactly | **Proven offline**: A3-fault, RT-presend and MAIN-hyp all show 0 injections |
| If concurrent generation also triggered the artifact, A3 would refuse rather than miscount | **Proven offline**: A3-ext stops at the first trailing EOS with `TokenizedContextInvalid` |
| Live sequential `/tokenize` is exact on an idle server | **Observed live**: 464 + 212 texts, diagnostic boots 1 and 2 |
| Live sequential `/tokenize` stays exact while other clients generate | **Unverified.** Boot 2 mixed *concurrent* `/tokenize` with completions, which does not isolate the case |
| The server-side mechanism | **Hypothesis only** |

**Operational exposure.**
- Freezes run on an idle server.
- In each block, the pre-send verification runs before any request is sent, and the VPC has no other tenants.
- The per-seed recalibration inside the block loop hits the counter's cache and makes no HTTP call.
- The only other traffic is the Prometheus `/metrics` scrape, which does no tokenization.

## 5. Performance overhead

`/tokenize` call counts are the unique texts per fresh counter, measured offline. The live per-call latency is
bounded from diagnostic boot 2:
- 212 sequential calls plus the other untimed steps took at most 3.16 s, so a sequential call costs **≤ 14.9 ms**;
- 16-way concurrency took 0.21 s for 212 calls, about 1 ms per call.

| Where | `/tokenize` calls | Live upper bound, sequential (A3) | Frozen 16-way, for reference |
|---|---|---|---|
| g1m1 calA freeze (36 scenario-seeds) | 21,528 | ≤ 5.3 min | ~0.4 min |
| calA runtime pre-send, all 12 files (≈ per block × 12) | 21,528 | ≤ 5.3 min in total; per block ≤ 27 s | — |
| A2 main freeze at a hypothetical 10 tok/s (136 scenario-seeds incl. reruns) | 62,736 | ≤ 15.6 min | ~1 min |

Main pre-send verification is of the same order as the main freeze, split across its blocks. At the 14.9 ms bound, the
**worst-case added wall time for g1m1** (calA freeze + calA pre-send + main freeze + main pre-send) is:

| Selected low rate | Added time | GPU-h | Cost at the realised ~$1.86 per GPU-h |
|---|---|---|---|
| 10 tok/s | ≈ 5.3 + 2.7 + 15.6 + 7.8 ≈ 31 min | ≈ 0.5 | ≤ ~$1 |
| 140 tok/s (115,728 main calls, the extreme) | ≈ 51 min | ≈ 0.85 | ≤ ~$1.6 |

Either fits inside the $60 cap (about $34 left). The estimate is an upper bound; the actual sequential latency is
likely lower.

The mock's offline wall times (0.5 ms injected delay) are in the JSON and are not live estimates.

## 6. Reproducibility and provenance

- **Code.** A3 draft commit `e2cd491`; validator correction `ef095ba`. Every live A3 process records its
  identity `{amendment: X2-A3, counting: sequential, workers: 1, guards}` in the frozen-trace and run manifests.
- **Reference tokenizer.**
  - The model is `mistralai/Mistral-7B-Instruct-v0.3` at revision `c170c708c41dac9275d15a8fff4eca08d52bab71`, file
    `tokenizer.model.v3`, sha256 `37f00374dea48658ee8f5d0f21895b9bc55cb0103939607c8185bfd1c6ca1f89`.
  - The validator refuses any other file.
  - It is not committed (gated model); the local copy is in `reports/x2_a3/ref/`.
- **Environment.** Python 3.12.13, sentencepiece 0.2.3 (`uv run --with sentencepiece`), and the repo lockfile for
  everything else.
- **Inputs.** The committed `experiments/x2/g1m1/calA/` (12 YAMLs, digest `5b350fbb`) and the A2 generator for the
  hypothetical main files, which are written to a git-ignored temp dir and deleted.
- **Determinism.** Two A3 runs, the clean mock, the fault mock and the in-process SentencePiece count all give traces
  digest `a5095c7c…`.
- **Diagnostic evidence.** `reports/x2/g1m1/diagnostic/` (private; `SHA256SUMS` verifies).
- **Candidate pins.** `reports/x2_a3/A3_CANDIDATE_SHA256.json` is non-binding; it comes from
  `pin_x2_a3.py --candidate`.
- **Checks at the final commit:** the following all hold.
  - `ruff` and `mypy` are clean.
  - pytest: 644 passed, 1 skipped (the opt-in real-GPU test). This includes the 13 A3 tests.
  - `pin_v5`, `pin_x2`, `pin_x2_a2` and `pin_x1_amendment` `--check` all match.
  - `pin_x2_a3 --check` reports only "A3 freeze has not been made", as expected for a draft.
  - No tracked change exists under `experiments/`, in `tokenize.py` or in `local.py`.

## 7. GO / NO-GO

**Recommendation (draft):** GO for owner review and the A3 freeze; NO-GO for any live use until the steps below are
done.

**Update, 2026-11-27:**
- Steps 1–3 are done: owner approval, runner dispatch, A3 freeze.
- `x2_a3.problems("g1m1", live=True)` now returns no problems.
- Remaining before live use: a runner-image rebuild and push from a commit containing the A3 manifest (its own
  approval), then the g1m1 stage approvals already defined.

- **GO because:**
  - the correction is additive and Mistral-only;
  - no pinned byte changes;
  - the estimand is unchanged by argument and by trace-hash equality;
  - every exact-token gate is intact;
  - the offline matrix meets every corrected expectation;
  - the residual live uncertainty fails closed.
- **Before any live A3 run, each step needs its own approval:**
  1. owner sign-off on this draft;
  2. the non-frozen runner dispatch change (`x2_runner_entry.py` emits `x2_a3.py` for Mistral platforms and
     allow-lists it), plus a runner-image rebuild;
  3. `pin_x2_a3.py --write` with `x2_amend_a3`;
  4. then the already-defined g1m1 sequence through `x2_a3.py`.
- **Recommended at the first live A3 freeze (no extra boot):** the freeze log already records `count.calls` and the
  identity. A trailing-EOS guard trip there would itself be the live answer to §4's open question.
- **Known risk outside A3:** if the frozen rate rule selects 5 tok/s for g1m1, the A2 coverage gate is expected to
  refuse main (§3 note).
