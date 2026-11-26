# X2 Amendment A2: frozen-diff, offline validation, validity assessment and go/no-go (DRAFT)

**For:** owner review of `docs/PROTOCOL_X2_AMENDMENT_A2.md`, prepared 2026-11-26.
- **Cost:** zero; offline only.
- **Not done:** no GPU, no AWS, no live tokenizer, no measurement.
- **Detail:** the full per-seed matrix is `reports/x2_a2/A2_VALIDATION_g1m0.md`; machine-readable in `.json`.

## 1. Frozen-diff and audit

**Frozen records untouched.** These all verify after the change:
- `pin_x2.py --check`: X2 Freeze 1, plus the v5 dependencies and the X1 manifests;
- `pin_v5.py --check`;
- `pin_x1_amendment.py --check`.

None of the changed or added paths is listed in any freeze manifest (X2 Freeze 1, v5, X1 Freeze 1, A1). A2's own manifest has **not** been written; `pin_x2_a2.py --check` reports "the A2 freeze has not been made".

| Path | Status | Purpose |
|---|---|---|
| `src/quotashift/x2/arrivals_a2.py` | new | A2 law: `ScenarioConfigA2` overrides `_fixed_count_items` only; scoped loader dispatch |
| `src/quotashift/cli.py` | modified (not frozen) | its 5 `load_scenario` imports now use `load_scenario_any`. Non-A2 files go to the frozen loader (tested on every X2 main/calA file and every v3.1 file, which uses the frozen `protocol_amendment: "3.1"` label) |
| `scripts/build_x2_a2.py` | new | A2 files = frozen `build_x2` main output + 2 keys + header; byte copies of `QUALIFICATION.json` and `RATES.json` |
| `scripts/freeze_x2_a2_traces.py` | new | frozen freeze on the A2 root; provenance block |
| `scripts/pin_x2_a2.py` | new | A2 manifest (`x2_amend_a2`), A2 phase pin (`x2a2_freeze_main_<p>`) |
| `scripts/x2_a2_stage.py` | new | frozen stage driver on the A2 root (`x2a2_main_<p>`) |
| `scripts/x2_a2_validate.py` | new | this validation |
| `scripts/x2_runner_entry.py`, `scripts/aws_ops.sh` | modified (not frozen) | A2 routes and inputs; existing routes unchanged (tests) |
| `experiments/x2_a2/g1m0/` | new | 8 A2 YAMLs (digest `d0bda205…`) + 2 byte copies |
| `docs/PROTOCOL_X2_AMENDMENT_A2.md`, this file, `reports/x2_a2/` | new | amendment, review, validation |
| `tests/unit/test_x2_a2.py`, `tests/integration/test_x2_a2_mock_pipeline.py`, `tests/unit/test_x2_aws_orchestration.py` | new / extended | 51 A2 tests (48 unit, 3 integration) + 6 routing tests |

**Defect found and fixed during validation.** The first version of the dispatcher selected A2 whenever a YAML had a `protocol_amendment` key. The frozen schema already uses that key as a free-text label (v3.1 files: "3.1"), so v3.1 files would have been misrouted. The full suite caught it. A2 is now selected only by `protocol_amendment: X2-A2` or a `competitor_arrival_law` key, and the loader substitution used by the A2 freeze is scoped and restored. Regression tests cover both.

## 2. Offline validation (g1m0)

**Scope:** every intended main seed and every rerun seed. That is 4 cells + 4 rerun files: X2a 24, X2b 24, X2c 10, X2d 10 seeds each, so 136 seed-arms per arm type. Results are passing/checked.

| Check | Attack | Control |
|---|---|---|
| Frozen arrival-coverage gate, **original law** | 92/136 | 132/136 |
| Frozen arrival-coverage gate, **A2** | **136/136** | **136/136** |
| Exactly one arrival per stratum (A2) | 136/136 | 136/136 |
| Competitor count = original | 136/136 | 136/136 |
| Authorized competitor tokens = original | 136/136 | 136/136 |
| Request ids, prompts, shapes = original | 136/136 | 136/136 |
| Victims (ids, times, prompts, shapes) = original | 136/136 | 136/136 |
| Deterministic regeneration (schedule hash) | 136/136 | 136/136 |

| Per-seed check | Result |
|---|---|
| Victim schedule paired between arms (A2; original also 136/136) | 136/136 |
| Frozen matched-budget gate | 136/136 |
| X2b independent A/A (competitor arrival streams differ) | 48/48 |
| **Frozen offline freeze, every frozen gate, original files** | **refused**: `X2a attack seed 23000: first 0.153, last 0.508` (reproduces the live refusal) |
| **Frozen offline freeze, every frozen gate, A2 files** | **pass**, 8 scenarios |

Tooling results:
- **Tests:** full suite 631 passed, 1 skipped (the opt-in real-GPU test).
- **Static checks:** `ruff` clean; `mypy` clean.
- **Mock smoke** (`tests/integration/test_x2_a2_mock_pipeline.py`): the committed A2 files run through the frozen stage driver, the frozen v5 block runner and a real `quotashift experiment --mock` subprocess, with 2 seeds and full 120 s windows.
  - All 4 blocks pass every frozen runtime validity gate, including the runtime arrival-coverage gate on the planned schedule.
  - Every recorded competitor arrival is one per stratum.
  - The X2 analysis runs.
  - The mock is plumbing only, not a measurement.

The offline tokenizer is enough here: arrivals do not depend on the tokenizer, and the frozen freeze itself verifies that schedules are unchanged by tokenizer calibration. The live freeze will repeat every gate with the G1 tokenizer.

## 3. Original vs stratified arrivals (intended seeds; schedule properties, not measurements)

**Definitions:**
- **Overlap:** the share of competitor requests that arrive within one isolated Phase 1 hold time (D 14.55 s, S 3.67 s) of an earlier competitor request.
- **Peak:** the maximum number of concurrent competitor requests on that basis.

| Cell / arm (N) | Law | Gap CV | Min gap s | Max gap s | First / last (mean) | Overlap | Peak |
|---|---|---|---|---|---|---|---|
| X2a attack, D (4) | original | 0.77 | 0.37 | 93.7 | 0.158 / 0.807 | 0.375 | 3 |
| | A2 | 0.43 | 2.63 | 56.5 | 0.114 / 0.853 | 0.125 | 2 |
| X2a control, S tmf (10) | original | 0.90 | 0.02 | 53.3 | 0.076 / 0.909 | 0.282 | 4 |
| | A2 | 0.44 | 1.00 | 23.8 | 0.058 / 0.947 | 0.046 | 2 |
| X2b attack / control, S (9) | original | 0.97 / 0.98 | 0.07 / 0.16 | 60.5 / 66.6 | ~0.08 / ~0.93 | 0.255 / 0.292 | 4 / 3 |
| | A2 | 0.41 / 0.40 | 1.06 / 1.65 | 25.1 / 25.0 | ~0.05 / ~0.94 | 0.042 / 0.031 | 2 / 2 |
| X2c = X2d attack, D (4) | original | 0.71 | 0.37 | 58.5 | 0.146 / 0.733 | 0.433 | 3 |
| | A2 | 0.46 | 2.63 | 56.5 | 0.111 / 0.867 | 0.100 | 2 |

What stays the same, and what changes:
- **Same:** the number of competitor requests, their tokens, and therefore the mean offered competitor load and slot demand per arm.
- **Changed:** the **clustering**.
  - Under the original law, a seed's 4 decode requests often overlap: 37–43% arrive while another is still in its isolated hold, and up to 3 run at once.
  - Under A2, 10–13% overlap, at most 2 run at once, and gaps are more regular (CV about 0.45 instead of 0.7–1.0).
  - The same holds for the S-shaped controls and A/A arms.
- **Cross-cell pairing:** X2c and X2d share the same seeds and labels, so they share their arrival schedules under both laws.

## 4. Scientific validity and comparability

**Internal validity of the X2 contrasts is preserved.**
- Both arms of every cell use the same law. Victims are identical to the original files and between arms.
- Token budgets match under the frozen gate, and request counts, shapes, caps and seeds are unchanged.
- The H1 contrast (D vs S at matched tokens) therefore still varies only the request shape.
- The X2b noise floor is measured under the same law as the cells it calibrates.
- In the original design the attack and control arms got *different* random clustering per seed; under A2 both arms are spread one per stratum. Whether this changes between-seed variance, and in which direction, is an empirical question; it is not assumed here.

**Changing the arrival law changes the estimand.** Request counts, token budgets, shapes, caps and seeds are fixed, but the competitor's arrival process is part of the workload being characterised. X2-A2 estimates the shape effect for a competitor whose low-rate requests are spread one per stratum over the window. It does not estimate the effect for an iid-uniform (Poisson-conditioned) competitor whose requests may bunch, which is what the original X2 law, v5 and X1 target. The two estimands are related but not the same quantity.

**Impact on SLO, effect magnitude and variance is an empirical question.** The schedule statistics in §3 show less clustering under A2, but they are schedule properties, not measurements. How less clustering translates into victim TTFT, control and attack SLO success, effect magnitude and between-seed variance depends on the serving system: batching, KV-cache use, the gateway cap and their interaction. It could move in either direction. No direction is assumed, and none is used to interpret the H1 test at the unchanged 1.25 threshold.

**Not an attacker model.** The law is a measurement design choice that makes window coverage hold by construction. It does not claim that an adversary spreads load.

**Comparability.**
- **Within X2-A2 (cells, the X2b floor, and later platforms that also use A2):** comparable.
- **With v5, X1 and X2 calibration A (iid uniform conditioned on count):** same request counts and token budgets, but a different estimand (above). Magnitudes and variances are not directly comparable; cross-protocol statements should be qualitative or stated with the arrival law.
- **Calibration A and rate selection** used the original law. `low = 10` and `low_feasible = true` were produced once by the frozen rule and stand unchanged; A2 does not re-select. Measured control slot demand includes time in service, which depends on concurrency, so neither it nor control SLO success at 10 tok/s is assumed to carry over unchanged to A2. Both are measured again in the A2 main control arms and will be reported alongside the calibration-A values.

**The coverage gate stays but no longer screens.** For N ≥ 4 the frozen coverage gate is satisfied by construction under A2. It is retained unchanged as a defensive check, but it is no longer an informative screen for A2 cells. The amendment says so explicitly rather than presenting the gate as a passed test.

**Single-rerun allowance.** Unchanged. Rerun files share their main file's arrival schedule under both laws, because the salt changes only prompt nonces. Arrival-driven failures could never be cleared by a rerun, and under A2 none occur.

## 5. Cross-platform applicability (g1m0, g1m1, g0m0, g0m1)

The A2 generator has no platform parameter: the same code and the same predeclared stream apply to every platform. Whether it satisfies the gate depends only on the counts that the frozen generator derives from each platform's own frozen rate selection:

| Selected low rate | N decode attack | N S controls | A2 gate | Original gate, P(pass) per D seed-arm |
|---|---|---|---|---|
| 5 tok/s | 2 | 5 | **not guaranteed**: P = 0.25 per D seed-arm | 0.125 |
| ≥ 10 tok/s | ≥ 4 | ≥ 9 | **guaranteed** | 0.43 at 10, rising with rate |

Per platform:
- **g1m0:** selected 10 → A2 applies; all gates pass (§2).
- **g1m1, g0m0, g0m1:** not yet qualified; their low rates are unknown.
  - G0 (RTX 3090) is expected to have shorter hold times, so higher low rates and A2 would apply. This is an expectation, not a measurement.
  - A platform with a longer isolated S hold time may select 5 tok/s. Its X2a/X2c/X2d cells would then fail the frozen gate under A2 as well.
  - Resolving that would need a further scientific decision, which A2 does not include and this draft does not propose. Examples: a minimum competitor count, or longer arms.

**Stop condition reported as instructed:** A2 alone cannot guarantee the gate across all four platforms. It does for every platform whose frozen low rate is ≥ 10 tok/s, which includes g1m0.

## 6. Recommendation

**GO for g1m0, subject to this review.**
- Every requirement of the owner decision is met offline: coverage, conservation, pairing, independent A/A, determinism, every frozen gate, tests and the mock smoke.
- No frozen record or threshold changed.

Proposed next approvals, in order:
1. `x2_amend_a2`: A2 freeze;
2. runner image build, push and task-definition update;
3. `x2-inputs`;
4. `x2a2_freeze_main_g1m0`: live tokenizer-exact freeze + phase pin;
5. `x2a2_main_g1m0`.

Estimated GPU use is about 0.3 h for the freeze and about 5.2 h for main (68 rep-pairs at the calibration A pace). That is about $6 more, for a campaign total of about $18 of the $60 budget.

**NO-GO, for now, on applying A2 unchanged to the other platforms.** First decide, before their rate selection, what happens if a platform's frozen low rate yields N < 4.
