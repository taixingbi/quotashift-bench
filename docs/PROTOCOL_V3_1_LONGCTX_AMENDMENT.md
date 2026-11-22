# Protocol v3.1 amendment — A9 long-context family sized in real tokens

Version 3.1, pre-registered **2026-11-21, before any v3.1 run**. This amends `docs/A7_A9_EXPERIMENT_DESIGN.md` (A9)
for the long-context family only. Decision record: ADR-Q16/Q17, `docs/ADR_TTFT_METRIC_CORRECTION.md`.

## Why

The v3 blocks `a9_tok_longctx` and `a9_rate_longctx` are **invalid** (`reports/v3/SUITE_S_FORENSIC_AUDIT.md` §0.3–0.4).
In their attack arms, 112 of 116 competitor requests got HTTP 400 ("maximum input length of 3840 tokens"). The cause is
that planned prompt lengths count whitespace words of pseudo-syllable filler. Each of those words is about 2.03–2.14
Qwen2.5 tokens, so the planned 1,136–3,584 words became about 2,300–7,300 tokens. The schema safety check compared
words with `model_max_len`, and no long-context smoke test was run. The original data is kept unchanged and is labelled
invalid. It is excluded from every confirmatory conclusion.

## What changes (and nothing else)

| | v3 (invalid) | v3.1 |
|---|---|---|
| Files | `experiments/v3/a9_{tok,rate}_longctx.yaml` (unchanged, kept) | `experiments/v3_1/a9_{tok,rate}_longctx_v31.yaml` |
| `scenario_id` | `a9_{tok,rate}_longctx` | `a9_{tok,rate}_longctx_v31` |
| `isolation_salt` | `""` | `v31-longctx-{tok,rate}-r1` |
| Prompt unit | whitespace words (`prompt_token_unit: whitespace`) | **real Qwen2.5 tokens** (`prompt_token_unit: tokenizer`) |
| Filler | pseudo-syllable words (~2.1 tokens each) | `workload.isolation.NONCE_VOCAB`, all 174 words verified on the live tokenizer as exactly 1 token with and without a leading space (2026-11-21 21:00 EST) |
| Sizing | none | per-request calibration (`workload/tokenize.calibrate_trace`): filler words are appended or removed at the end until `/tokenize` gives exactly `input_token_count`. The `[req <id>]` tag (16+ tokens) and the 4 nonce words are kept and counted. `input_token_count` and the matched budgets are never changed |
| Prompt floor | 1 | 32 tokens (tag + nonce + ≥ 8 filler) |
| Pre-run check | none | every request of both arms and all seeds is tokenized by the live `/tokenize`. The run is refused before anything is sent unless prompt tokens + `max_output_tokens` ≤ 4096 and tokenized = planned, exactly (`verify_trace`) |
| Validity gates | none | ADR-Q17 gates, fail closed (HTTP 400 ≤ 1%, admission ≥ 95%, competitor completion ≥ 95%, planned = engine-reported prompt tokens, clean provenance, primary metric present) |

These stay **unchanged**: model and `max_model_len` 4096, shapes (long context: lognormal median 3,584-token input, cap
3,584, `max_tokens` 256; victims short 64/64; control short 64/64), rates (victims 3 × 0.3 rps, competitor 0.2 rps),
runtime 120 s, 5 paired seeds (42–46), counterbalanced arm order, `cache_reset: none` with a new salt, gateway
config, primary metric **GPU dynamic energy per 1,000 authorized tokens (arm window)**, direction two-sided,
**threshold 1.25×**, and the 95% percentile bootstrap CI classification. Authorized tokens remain planned
`input_token_count + max_output_tokens`, now in real tokens.

`/v1/completions` sends the prompt text as-is, so there is no chat template to add. The tokenized count covers
everything that is sent (tag + nonce + filler) and equals the `usage.prompt_tokens` the engine reports. The
`planned_vs_reported_tokens` gate verifies this per completed request.

## Order of operations (pre-registered)

1. Unit tests pass, and both amended scenario files validate offline.
2. Live pre-check: tokenize every request of both scenarios for all 5 seeds. Result on 2026-11-21 21:08 EST: 11,310
   tokenize calls; every request tokenized to exactly its plan; max context 3,840 ≤ 4096; token-matched budgets
   matched within 0.09%.
3. Code and this amendment are committed (the provenance gate requires a clean tree).
4. **Smoke** (`experiments/v3_1/smoke/*`, 1 seed, 40 s, new salt): it must pass every validity gate (exit 0), with
   competitor completion ≥ 95% and HTTP 400 ≤ 1%. Its classification is not a result.
5. Only then, the full runs: `a9_tok_longctx_v31` and `a9_rate_longctx_v31`, 5 paired seeds each. Any gate failure
   stops the run, and the failure is reported; there is no retry loop.
6. v3.1 results are a **new series**. They are never pooled with v3, and they are reported beside the invalid v3 blocks.

## Not changed by this amendment

A7, A8 and the six valid A9 blocks are not rerun. Their pre-registered results stand as reported, with the
corrections in `reports/v3/SUITE_S_CORRECTED_ANALYSIS.md`.
