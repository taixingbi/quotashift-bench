# Protocol X2: Amendment A2, stratified competitor arrivals (DRAFT)

**Status:** DRAFT for owner review (2026-11-26). It authorizes nothing.
- The A2 freeze (`x2_amend_a2`) has not been made.
- No A2 trace has been frozen against a live tokenizer.
- No A2 measurement has been made.

**Identifier:** `X2-A2`. The arrival law is `stratified_v1`.

**Owner decision (2026-11-26):** use coverage-preserving stratified competitor arrivals for the low-count X2 main
workloads. Drafting and offline validation only.

**Review and evidence:** `docs/X2_AMENDMENT_A2_REVIEW.md`, and the offline matrix
`reports/x2_a2/A2_VALIDATION_g1m0.{md,json}`.

## 1. Why: the recorded failure

1. g1m0 (Qwen2.5-7B on an L4) passed qualification and calibration A (6/6 blocks).
2. `x2_select_rates.py` ran once under the frozen rule. It selected **low = 10 tok/s**: control ρ 0.4234, control SLO 1.000, feasible.
3. The frozen generator turns 10 tok/s into a decode competitor of **N = 4 requests** per 120 s arm (64 in, 256 out).
4. The frozen v4 arrival-coverage gate requires the first competitor arrival ≤ 0.25·T and the last ≥ 0.75·T. Four iid uniform arrivals meet that with probability 1 − 2(0.75)⁴ + 0.5⁴ = 0.43.
5. The in-VPC main freeze (2026-11-26 02:28–02:31Z) was refused at `X2a attack seed 23000: first 0.153, last 0.508`. Nothing was frozen, pinned or sent.
6. The offline scan of all preregistered seeds:
   - X2a fails 12/24 attack seeds;
   - X2c and X2d fail 5/10 each;
   - X2b fails 2/24 control seeds;
   - the `__r2` rerun files fail the same seeds, because a rerun changes only the prompt nonce salt and not the arrival stream.
7. The failure is therefore structural at this rate. It cannot be cleared by the single-rerun allowance.

These records stay exactly as they are:
- the original X2 Freeze 1 files;
- the original g1m0 main files (`experiments/x2/g1m0/main/`, commit `667d422`);
- `RATES.json`;
- the refused-freeze log (`7e31ae59…`, private);
- the audit history (`experiments/x2/approvals/2026-11-25_aws_first_batch.md`).

## 2. What changes

For every fixed-count competitor phase (`request_count` = N over a window of T s, offset t₀), the arrival times are:

```
t_k = t₀ + (k + U_k) · T / N,    k = 0 … N−1,    U_k iid Uniform[0, 1)
U ~ numpy default_rng(SeedSequence(entropy = seed, spawn_key = (crc32("<tenant>|<label>"), 103)))
```

The times are then sorted chronologically (they are already monotone). The k-th request of the phase receives the k-th time.

| Item | Original X2 (frozen) | X2-A2 |
|---|---|---|
| Competitor arrival law (fixed-count phases) | N iid Uniform[0, T), stream 101 | one Uniform draw per stratum of width T/N, **stream 103** (new, predeclared) |
| Applies to | attack, token-matched control (`ctl_tmf`), A/A replicate (`<phase>~ind`) | the same three, same labels, so A/A streams stay independent |
| Victim arrivals (Poisson, `_segment_items`) | unchanged | **unchanged** |
| Request ids, counts, shapes, prompt text (stream 102), SLO fields | frozen code | frozen code, called unchanged; only `arrival_time_s` is replaced |

**Consequence:** with N ≥ 4, the first arrival lies in [0, T/N) ⊆ [0, 0.25·T] and the last in [(N−1)·T/N, T) ⊆ [0.75·T, T).
So the **unchanged** gate passes for every seed. The gate thresholds are not relaxed.

## 3. What does not change

All of the following are byte-identical to the original files:
- **workload:** selected rates (`RATES.json`, low 10 tok/s), request counts, token budgets, shapes;
- **design:** seeds (23000–23023; 23000–23009), repetitions (24/24/10/10), gateway caps (C8, direct, C32), isolation salts and the rerun files;
- **measurement:** measurement definitions, validity gates and thresholds (including arrival coverage 0.25/0.75 and the matched-budget tolerance 0.05);
- **analysis:** the 1.25 effect threshold, hypotheses, statistical tests and analysis code;
- **calibration:** qualification and calibration A.

The only per-file difference is:
- one header comment line;
- `protocol_amendment: X2-A2`;
- `competitor_arrival_law: stratified_v1`.

## 4. Separation and provenance

| Artifact | Location |
|---|---|
| A2 scenario root | `experiments/x2_a2/<p>/`: `main/` (4 cells + 4 rerun files), byte copies of `QUALIFICATION.json` and `RATES.json` (verified equal to the originals) |
| Arrival law | `src/quotashift/x2/arrivals_a2.py`: `ScenarioConfigA2`, a subclass of the frozen `ScenarioConfig` that overrides only `_fixed_count_items` |
| Loader dispatch | `load_scenario_any`. It selects A2 only for `protocol_amendment: X2-A2` or a `competitor_arrival_law` key; every other file goes to the frozen loader. The `quotashift` CLI uses it, so `quotashift experiment` on an A2 file applies the A2 law |
| Generator | `scripts/build_x2_a2.py`: frozen `build_x2` main output plus the two keys; `--check` |
| Trace freeze | `scripts/freeze_x2_a2_traces.py`: frozen `freeze_x2_traces.freeze(..., root=experiments/x2_a2)`, so every frozen gate runs unchanged. The loader substitution is scoped to the call. Outputs carry an `amendment` block: law, stream, module SHA-256, A2 and original file digests |
| Pins | `scripts/pin_x2_a2.py`: manifest `experiments/x2_a2/AMENDMENT_A2_SHA256.json` (written only with `x2_amend_a2`); phase pins in the frozen X2 record format at `experiments/x2_a2/<p>/PHASE_PINS.json` (`x2a2_freeze_main_<p>`) |
| Stage | `scripts/x2_a2_stage.py`: frozen `x2_stage.run_stage(..., root=experiments/x2_a2)`. Token `x2a2_main_<p>`; the stage log is marked `"amendment": "X2-A2"` |
| In-VPC routing | `x2_runner_entry.py` / `aws_ops.sh`: stage kinds `a2_freeze_main` and `a2_main` with tokens `x2a2_freeze_main_<p>` and `x2a2_main_<p>`; the inputs tarball adds `experiments/x2_a2/<p>/` |
| Validation | `scripts/x2_a2_validate.py` → `reports/x2_a2/A2_VALIDATION_<p>.{json,md}` |

No file under X2 Freeze 1, the v5 freeze, X1 Freeze 1 or Amendment A1 is modified. `pin_x2`, `pin_v5` and `pin_x1_amendment` all verify.

## 5. Scope and prospective applicability

A2 is platform-agnostic: there is no platform parameter or tuning. It **guarantees** the frozen gate only when every fixed-count competitor phase has N ≥ 4. For the X2 cells:
- the decode attack has N_D = round(0.375 · low);
- the controls have N ≥ 5 at every grid rate;
- so the condition is **low ≥ 10 tok/s**.

At low = 5 tok/s, N_D = 2. A2 then passes the gate with probability 0.25 per seed-arm (original law: 0.125), and a 24-seed cell would be refused.

Whether a platform selects 5 depends on its own calibration A:
- On g1m0, 10 was chosen over 5 by |0.4234 − 0.43| = 0.007 against |0.4076 − 0.43| = 0.022.
- Slower platforms, with a longer isolated S hold time, are more likely to select 5.

A platform whose frozen selection yields N < 4 in any cell needs a further, separately approved scientific decision before its main freeze. A2 does not cover it.

## 6. Procedure after review (each step needs its own owner approval)

1. **A2 freeze** (`x2_amend_a2`): `pin_x2_a2.py --write`, after the reviewed files are committed.
2. **Runner image:** the code changed, so the runner needs a new image. This needs `build_image`, `push_image` and a runner task-definition update. Then `x2-inputs`.
3. **Live main freeze** (`x2a2_freeze_main_g1m0`): `run-stage` → `freeze_x2_a2_traces.py --live` (live G1 tokenizer), then the local `pin_x2_a2.py --pin-phase g1m0 main`.
4. **Main** (`x2a2_main_g1m0`): `run-stage` → `x2_a2_stage.py --live`, with the frozen order, single-rerun allowance and stops.

The original `x2_freeze_main_g1m0` and `x2_main_g1m0` tokens do not run A2 files. The A2 stage driver, the A2 phase pin and the in-VPC A2 routes all refuse them, and the original routes never reach the A2 drivers.
