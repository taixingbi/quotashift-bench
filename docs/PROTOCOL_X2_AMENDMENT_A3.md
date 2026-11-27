# Protocol X2: Amendment A3, sequential token counting for Mistral (DRAFT)

**Status:** DRAFT for owner review (2026-11-27). It authorizes nothing.
- The A3 freeze (`x2_amend_a3`, `experiments/x2_a3/AMENDMENT_A3_SHA256.json`) has not been made.
- No A3 trace has been frozen against a live tokenizer.
- No A3 calibration-A or main measurement has been made.
- No AWS resource was started for this draft.

**Identifier:** `X2-A3`. Activation value: `QUOTASHIFT_TOKEN_COUNTER=X2-A3`.

**Owner decision (2026-11-27):** draft and validate offline a Mistral-specific sequential token-counting correction
that leaves generation behaviour and the X2 estimand unchanged.

**Review and evidence:**
- Validity review, frozen-diff report, validation matrix, provenance and GO/NO-GO: `docs/X2_AMENDMENT_A3_REVIEW.md`.
- Offline matrix: `reports/x2_a3/A3_OFFLINE_VALIDATION.json`.
- Diagnostic evidence: `reports/x2/g1m1/diagnostic/` (private, git-ignored, checksummed). Summarised in
  `docs/KNOWN_LIMITATIONS.md` (three g1m1 entries).

## 1. Why: the recorded failure

1. g1m1 (Mistral-7B-Instruct-v0.3 @ `c170c708`, vLLM 0.17.1, `--tokenizer-mode mistral`, L4) **passed qualification**.
2. The in-VPC calibration-A freeze (`freeze_x2_traces.py --live --phase calA`, 2026-11-27 00:04Z) was **refused by the
   frozen exact-tokenization gate**: `6 request(s) did not calibrate to their planned token count`. Nothing was frozen,
   pinned or sent.
3. Diagnostic boot 1 (2026-11-27 02:17–02:37Z), on byte-identical inputs:
   - sequential `/tokenize` equals the pinned offline tokenizer (BOS + SentencePiece) for all 464 texts;
   - the frozen 16-worker counter returned +1 for 445 of 486 counts;
   - 32-way concurrent repeats of one text return {n, n+1}, while 20 sequential repeats are always n.
4. Diagnostic boot 2, the generation path (2026-11-27 03:14–03:34Z), over the 212 unique prompts:
   - `/v1/completions` `usage.prompt_tokens` equals the sequential count for **212/212**, at concurrency 1, 16 and
     32, and mixed 32-way with `/tokenize`;
   - the returned prompt token ids are byte-identical to the sequential `/tokenize` ids;
   - concurrent `/tokenize` was +1 for 203/212 (16-way) and 183/212 (32-way); the extra id is **always a trailing
     `</s>` (EOS, id 2)**, with every other id identical.
5. **Mechanism: hypothesis, not established.** The consistent explanation is that vLLM 0.17.1's `/tokenize` path
   (transformers Mistral tokenizer adds EOS, followed by a post-hoc trailing-EOS removal) does not always remove the
   EOS under concurrency, while generation encodes with `eos=False`. vLLM internals were not instrumented, so A3 does
   not rely on this mechanism.
6. **Consequence.** Every frozen count site resolves the 16-worker `VllmTokenizer`, so under concurrency each one
   miscounts Mistral prompts:
   - the X2 freeze `scripts/freeze_x2_traces.py:149`;
   - the A2 freeze `scripts/freeze_x2_a2_traces.py:87`;
   - the runtime pre-send recalibration and exact `verify_trace` in `src/quotashift/local.py:153`, which runs inside
     every `quotashift experiment` block.

   A corrected freeze alone would therefore still fail at runtime. **Qwen (HF tokenizer) is unaffected**: the g1m0
   freezes and runtime token gates all passed.

## 2. What changes

1. **New module `src/quotashift/workload/tokenize_a3.py`.**
   - `SequentialMistralTokenizer` subclasses the frozen `VllmTokenizer`. It keeps the same `POST /tokenize` body
     (`{"model", "prompt"}`, default `add_special_tokens`), the same text-hash cache and the same
     raise-on-HTTP-error behaviour.
   - It has **exactly one request in flight**: no executor at all, and `workers` is forced to 1 and cannot be
     configured.
   - It adds two fail-closed response checks, `count == len(tokens)` and *no trailing EOS id*. A failed check raises
     `TokenizedContextInvalid`. It never corrects or retries a count.
   - Its identity, recorded in every frozen-trace manifest and run manifest, adds
     `amendment: X2-A3, counting: sequential, workers: 1, guards`.
2. **Factory `a3_counter(base_url, model)`.**
   - It returns `SequentialMistralTokenizer` only for models in `A3_MODELS`. Today that is only
     `mistralai/Mistral-7B-Instruct-v0.3`, with bos 1 and eos 2, verified against the pinned `tokenizer.model.v3`.
   - Every other model gets the **frozen class itself**: 16 workers, identical identity. Qwen is bit-for-bit
     unchanged.
3. **Activation.** `install()` rebinds the module attribute `quotashift.workload.tokenize.VllmTokenizer` to
   `a3_counter`. The frozen callers import that name inside their functions at call time
   (`local.py:151`, `freeze_x2_traces.py:142`, `freeze_x2_a2_traces.py:80`), so they pick it up without a byte of
   their source changing.
4. **Env hook in `src/quotashift/workload/__init__.py`.** This file was empty and is not pinned by any manifest.
   - If `QUOTASHIFT_TOKEN_COUNTER` is set, the hook imports `tokenize_a3` and calls `activate_from_env()`. That
     installs A3 for `X2-A3` and **raises for any other value**.
   - If the variable is unset, the A3 module is never imported.
5. **Driver `scripts/x2_a3.py {freeze,stage} --platform P --phase {calA,main} …`.**
   - It sets the variable, installs A3 in-process and runs the frozen driver for that phase unchanged with the
     remaining arguments:

     | Phase | freeze | stage |
     |---|---|---|
     | calA | `freeze_x2_traces.py` | `x2_stage.py` |
     | main | `freeze_x2_a2_traces.py` | `x2_a2_stage.py` |

   - The block subprocesses (`python -m quotashift.cli experiment`, run by the frozen `v5_stage.run_block` with the
     parent environment) inherit the variable. So both the trace freeze and the runtime pre-send verification count
     sequentially.
   - It refuses non-Mistral platforms (g0m0, g1m0).
   - With `--live`, it refuses unless `pin_x2_a3.py --check` passes.
6. **Pins `scripts/pin_x2_a3.py`.**
   - It provides `--candidate`, `--write` (owner token `x2_amend_a3`, write-once) and `--check`.
   - The manifest pins the six A3 files and records the SHA-256 of the v5, X2 Freeze 1, A2, X1 and A1 manifests.
   - `--check` and `--write` both require `pin_v5.check()` and `pin_x2_a2.check()` to pass. The latter re-verifies
     X2 Freeze 1, the v5 dependencies, X1 and A1.
7. **Offline validation `scripts/x2_a3_validate.py`** (section 6).

## 3. What does not change

1. Not a byte of any v5, X2 Freeze 1, X2-A2, X1 or A1 artifact or manifest. This includes the frozen counter
   `tokenize.py`, `local.py`, every freeze and stage driver, every YAML and `QUALIFICATION.json`.
   `git diff --stat` touches no pinned path (frozen-diff report in the review).
2. Mistral revision, vLLM version and flags, gateway configuration, KV and context limits.
3. The generation path: `/v1/completions` requests are byte-identical, with raw text and no chat template.
4. Prompts and their construction:
   - the generator, nonce and salt, and the whole-word calibration (`calibrate_trace`, `PROTECTED_WORDS=6`,
     `MAX_CALIBRATION_ROUNDS=6`);
   - the calibrated prompt texts. Offline, the A3 traces hash identically to those of a correct concurrent counter.
5. Request shapes, `input_token_count`, `max_output_tokens`, seeds, repetitions, arrival laws (X2 and A2), the
   calibration-A grid (5, 10, 25, 55, 95, 140 tok/s), the rate-selection rule, SLOs and the 1.25 threshold.
6. Every gate:
   - exact `planned == tokenized`, the context fit, the matched budget and arrival coverage;
   - the schedule's independence from calibration, and independent A/A;
   - frozen-trace equality at runtime, the warm-cache guard, the server-identity, budget and snapshot stops, and the
     single-rerun rule.
7. Hypotheses, the Holm family, the analysis and "no interim looks".
8. g1m0 (Qwen): its results, counter, records and every future Qwen platform (g0m0) are untouched.

## 4. Estimand argument

1. The quantity the exact-token gate protects is the prompt-token count the engine actually prefills, which is
   `usage.prompt_tokens` on the generation path.
2. The diagnostic shows that this equals the sequential `/tokenize` count for 212/212 prompts at every concurrency
   tested.
3. A3 makes the gate measure exactly that quantity, instead of a count inflated by a counting-endpoint artifact.
4. Since prompts, schedules and budgets are unchanged, a trace frozen under A3 is byte-identical to the trace a
   correct counter would have produced (validated offline). The estimand and every pre-registered quantity are
   unchanged.

## 5. Concurrency boundary (what A3 does and does not guarantee)

- **Proven offline.** The A3 counter never has more than one `/tokenize` in flight. Against a mock that injects the
  trailing-EOS artifact whenever another `/tokenize` is in flight, all 36 calibration-A scenario-seeds freeze exactly,
  with zero injected artifacts and zero guard trips.
- **Not proven: external concurrent generation traffic.** If the artifact were also triggered by concurrent
  generation requests (mock mode `any`), A3 would **fail closed** through the trailing-EOS guard rather than count
  wrongly. This is shown offline.
- **Live behaviour of sequential `/tokenize` alongside concurrent `/v1/completions` is untested.** Diagnostic boot 2
  mixed concurrent `/tokenize` with completions, which does not isolate the question.
- **Operational exposure is low.**
  - Freezes run on an idle server.
  - The runtime pre-send verification runs before a block sends any request, in an isolated VPC with no other
    tenants.
  - Per-seed recalibration inside the block loop is served from the counter's cache and makes no HTTP call.

  The residual risk is a refused freeze or block with no data. A silent miscount is not a possible outcome.

## 6. Offline validation (summary; full matrix in the review)

`uv run --with sentencepiece python scripts/x2_a3_validate.py --sp-model <tokenizer.model.v3> --out
reports/x2_a3/A3_OFFLINE_VALIDATION.json`

- The mock is backed by the pinned SentencePiece model (sha256 `37f00374…`).
- It covers all 36 g1m1 calibration-A scenario-seeds, the runtime pre-send path, and hypothetical A2 main files at
  every grid rate (in a temporary directory; not a rate selection).
- It exits non-zero if any expectation fails.

## 7. Scope and prospective applicability

- A3 applies to **g1m1** and **g0m1** (Mistral) only, and only to phases that have not been frozen: g1m1 calA and
  main, and g0m1 throughout.
- It is applied prospectively: no completed result is reinterpreted.
- g0m1 is a different GPU on the same serving stack. A3 is applied there for the same reason and must pass the same
  freeze gates.

## 8. Procedure after review (each step needs its own owner approval)

1. **Owner review of this draft.**
2. **Runner dispatch (non-frozen).**
   - Change `scripts/x2_runner_entry.py` so that `overrides` emits `python scripts/x2_a3.py {freeze,stage} …` for
     Mistral platforms, and so that its allowed-command list includes `x2_a3.py`.
   - Rebuild and push the runner image.
   - Not part of this draft.
3. **A3 freeze:** `QUOTASHIFT_APPROVED=x2_amend_a3 uv run python scripts/pin_x2_a3.py --write`, then commit.
4. **g1m1 calibration-A freeze, in-VPC:**
   - run `x2_a3.py freeze --platform g1m1 --phase calA --live`;
   - pin the phase with the existing token `x2_freeze_calA_g1m1`;
   - run the calA stage `x2_a3.py stage --platform g1m1 --phase calA --live` (`x2_cal_g1m1`);
   - select rates under the frozen rule;
   - build the A2 main files;
   - freeze main through `x2_a3.py freeze --phase main` (`x2a2_freeze_main_g1m1`);
   - run the A2 main stage through `x2_a3.py stage --phase main` (`x2a2_main_g1m1`).

The stages and approval tokens are those already approved. A3 adds only the counter and the A3 freeze token.
