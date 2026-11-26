# X2-A2 g1m0 main: descriptive per-cell summary

**Descriptive only.** No hypothesis test, Holm family or verdict is computed here. The frozen X2 analysis
(`scripts/x2_analysis.py`) is not run: X2 §6 allows a real analysis only when every expected cell of every admissible
platform exists, and g1m1, g0m0 and g0m1 have not been qualified, so running it now would be an interim look.

Source: `reports/x2/g1m0/main/x2_*/summary.csv` (git-ignored raw evidence; checksums in `reports/x2/g1m0/main/SHA256SUMS`
and `RUNS_SHA256SUMS`). Stage `g1m0/main`, amendment X2-A2, completed 2026-11-26 13:32:02Z–18:47:02Z, 4/4 blocks, no reruns.
Every cell: 14/14 frozen v5 gates passed, not synthetic, Qwen2.5-7B-Instruct @ a09a3545…, vLLM 0.17.1, one server start.

Ratio = exp(mean over seeds of log(attack / control victim mean user TTFT)). Times are means over seeds of per-arm means, ms.

| Cell | n | ratio (range) | sd log | user TTFT att / ctl | backend TTFT att / ctl | gateway queue att / ctl | user p95 att / ctl | SLO att / ctl (min) | ctl ρ mean (range) | host snapshots |
|---|---|---|---|---|---|---|---|---|---|---|
| X2a D vs S, C8 | 24 | 1.075 (0.962–1.400) | 0.095 | 200.6 / 185.2 | 159.9 / 158.7 | 40.7 / 26.4 | 455 / 323 | 0.9973 / 0.9984 (0.970) | 0.470 (0.388–0.566) | 48 pass |
| X2b A/A-ind, C8 | 24 | 0.995 (0.865–1.202) | 0.070 | 188.4 / 189.2 | 158.8 / 158.6 | 29.6 / 30.5 | 366 / 362 | 0.9973 / 0.9984 (0.981) | 0.466 (0.384–0.562) | 48 pass |
| X2c D vs S, direct | 10 | 0.999 (0.963–1.034) | 0.022 | 157.5 / 157.6 | 157.5 / 157.6 | 0.0 / 0.0 | 186 / 187 | 1.0000 / 1.0000 (1.000) | 0.460 (0.388–0.525) | 20 pass |
| X2d D vs S, C32 | 10 | 0.998 (0.962–1.036) | 0.021 | 157.6 / 157.9 | 157.6 / 157.9 | 0.0 / 0.0 | 185 / 187 | 1.0000 / 1.0000 (1.000) | 0.460 (0.388–0.526) | 20 pass |

Other observations (all cells, both arms): 0 victim backend errors, 0 timeouts, 0 censoring; competitor completion 1.0;
engine waiting mean 0. Planned competitor arrivals: attack first ≤ 0.231·T and last ≥ 0.751·T; control first ≤ 0.110·T and last ≥ 0.891·T (gate 0.25 / 0.75).

Control slot demand ρ (frozen `x2_select_rates.control_slot_demand`). In calibration A, at 10 tok/s (A/A-ind S–S, seeds 22000–22002, original iid law),
ρ was 0.4234. In A2 main it is 0.460–0.470 (stratified law, seeds 23000+). The two are not the same estimand, and the difference is reported, not adjusted.

In X2c (direct) and X2d (C32), gateway queueing is 0, so user TTFT equals backend TTFT. In X2a (C8) the attack–control user-TTFT difference
(+15.5 ms) is almost entirely gateway queueing (+14.3 ms); backend TTFT differs by +1.2 ms.
