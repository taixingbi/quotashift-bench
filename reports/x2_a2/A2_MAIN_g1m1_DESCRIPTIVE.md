# X2-A2 g1m1 main: descriptive per-cell summary

**Descriptive only.** No hypothesis test, Holm family or verdict is computed here. The frozen X2 analysis
(`scripts/x2_analysis.py`) is not run: X2 §6 allows a real analysis only when every expected cell of every admissible
platform exists, and g0m0 and g0m1 have not been qualified, so running it now would be an interim look.

**Source:** `reports/x2/g1m1/main/x2_*/summary.csv`. This is git-ignored raw evidence; checksums are in
`reports/x2/g1m1/main/SHA256SUMS` (49 files) and `RUNS_SHA256SUMS` (1,088 files).

**Stage:**
- `g1m1/main`, amendment X2-A2, run with token counting under **X2-A3** (sequential Mistral `/tokenize`).
- Ran 2026-11-27 16:55:38Z–22:12:26Z: 4/4 blocks, no reruns.
- Every cell: 14/14 frozen v5 gates passed, not synthetic, Mistral-7B-Instruct-v0.3 @ c170c708, vLLM 0.17.1.
- One server start (1795797654.47), the same as at the main freeze. Runner image built from `2defa84`, dirty = false.
- Pre-send token verification was exact for every seed, under the A3 identity (sequential, workers 1).

**Definitions.** Ratio = exp(mean over seeds of log(attack / control victim mean user TTFT)). Times are means over
seeds of per-arm means, in ms.

| Cell | n | ratio (range) | sd log | user TTFT att / ctl | backend TTFT att / ctl | gateway queue att / ctl | user p95 att / ctl | SLO att / ctl (min) | ctl ρ mean (range) | host snapshots |
|---|---|---|---|---|---|---|---|---|---|---|
| X2a D vs S, C8 | 24 | 1.079 (0.980–1.426) | 0.096 | 202.4 / 186.0 | 160.3 / 158.6 | 42.1 / 27.4 | 468 / 333 | 0.9973 / 0.9984 (0.970) | 0.472 (0.390–0.569) | 48 pass |
| X2b A/A-ind, C8 | 24 | 0.996 (0.856–1.211) | 0.068 | 189.5 / 190.1 | 159.1 / 158.7 | 30.4 / 31.4 | 375 / 374 | 0.9973 / 0.9984 (0.981) | 0.468 (0.386–0.565) | 48 pass |
| X2c D vs S, direct | 10 | 1.006 (0.978–1.035) | 0.016 | 159.3 / 158.4 | 159.3 / 158.4 | 0.0 / 0.0 | 188 / 187 | 1.0000 / 1.0000 (1.000) | 0.462 (0.391–0.529) | 20 pass |
| X2d D vs S, C32 | 10 | 1.007 (0.989–1.030) | 0.012 | 159.0 / 157.9 | 159.0 / 157.9 | 0.0 / 0.0 | 188 / 188 | 1.0000 / 1.0000 (1.000) | 0.462 (0.390–0.528) | 20 pass |

**Other observations** (all cells, both arms):
- 0 victim backend errors, 0 timeouts, 0 censoring.
- Competitor completion 1.0. Engine waiting mean 0.
- Planned competitor arrivals: attack first ≤ 0.231·T and last ≥ 0.751·T; control first ≤ 0.110·T and last ≥ 0.891·T.
  The gate is 0.25 / 0.75.

**Control slot demand ρ.** In calibration A at 10 tok/s (A/A-ind S–S, seeds 22000–22002, original iid law), ρ was
0.4259. In A2 main it is 0.462–0.472 (stratified law, seeds 23000+). The two are not the same estimand; the
difference is reported, not adjusted.

**Gateway queueing.**
- In X2c (direct) and X2d (C32), gateway queueing is 0, so user TTFT equals backend TTFT.
- In X2a (C8), the attack–control user-TTFT difference (+16.4 ms) is almost entirely gateway queueing (+14.7 ms).
  Backend TTFT differs by +1.7 ms.
