# Protocol v5 analysis, stage A

Rules: `docs/PROTOCOL_V5.md` §3–§6, implemented in `scripts/v5_analysis.py`. No seed exclusion.

## Hypotheses

| Hypothesis | Verdict | Detail |
|---|---|---|
| H1 (F1) | **supported** | ratio 1.565, p 0.0298, Holm reject True |
| H2a (F1) | **supported** | ratio change per doubling 0.796, p_t 0.0007, p_perm 0.0020, Holm reject True |
| H2b (F1) | **equivalent** | ratio 0.993, p 0.0000, Holm reject True |
| H3 (FCFS predictions) | **supported** | 18 (cell, arm) scores |
| H4 (relocation) | **not_supported** | (a) backend C32/C8 1.005 p 0.2820; (b) queue reduction C8−C32 57.7 ms [24.3, 91.0] p 0.0018 → True; (c) True |
| H5 (explanatory consistency) | **supported** | n 180 arms, ρ(at-cap) 0.888, ρ(victims in saturation) 0.998 |
| H6 P vs S C8 (F2) | **equivalent** | ratio 0.994, p_TOST 0.0000 |
| H6 P vs S C16 (F2) | **equivalent** | ratio 1.048, p_TOST 0.0000 |
| H6 P vs S C32 (F2) | **equivalent** | ratio 1.073, p_TOST 0.0000 |

## Cells (primary: geometric mean over seeds of the per-seed victim mean user-facing TTFT ratio, attack/control; H7 strata)

| Cell | Stratum | n | Geo-mean ratio [95% CI] | Class | P95 ratio | ΔSLO (atk−ctl) | Δ>500 ms | Gw queue mean atk/ctl (ms) | Threshold > noise | Failed gates |
|---|---|---|---|---|---|---|---|---|---|---|
| v5_aa_ind_L200_C16 | E&Vb | 10 | 0.990 [0.974, 1.007] | equivalent | 0.990 | 0.000 | 0.000 | 0.0 / 0.0 | True | — |
| v5_aa_ind_L200_C32 | E&Vb | 10 | 0.998 [0.985, 1.012] | equivalent | 1.029 | 0.000 | 0.000 | 0.0 / 0.0 | True | — |
| v5_aa_ind_L200_C8 | E&Vb | 10 | 1.057 [0.978, 1.143] | equivalent | 1.229 | 0.000 | 0.005 | 8.7 / 3.5 | True | — |
| v5_aa_ind_L200_direct | E&Vb | 10 | 0.997 [0.981, 1.013] | equivalent | 0.995 | 0.000 | 0.000 | 0.0 / 0.0 | True | — |
| v5_decode_vs_short_L200_C16 | E&Vb | 10 | 0.990 [0.977, 1.002] | equivalent | 0.994 | 0.000 | 0.000 | 0.0 / 0.0 | True | — |
| v5_decode_vs_short_L200_C32 | E&Vb | 10 | 0.993 [0.977, 1.009] | equivalent | 1.004 | 0.000 | 0.000 | 0.0 / 0.0 | True | — |
| v5_decode_vs_short_L200_C8 | E&Vb | 10 | 1.565 [1.236, 1.982] | inconclusive | 3.664 | -0.002 | 0.051 | 57.7 / 3.3 | True | — |
| v5_decode_vs_short_L200_direct | E&Vb | 10 | 0.997 [0.982, 1.011] | equivalent | 0.991 | 0.000 | 0.000 | 0.0 / 0.0 | True | — |
| v5_prefill_vs_short_L200_C16 | E&Vb | 10 | 1.048 [1.005, 1.092] | equivalent | 1.440 | 0.000 | 0.001 | 0.0 / 0.0 | True | — |
| v5_prefill_vs_short_L200_C32 | E&Vb | 10 | 1.073 [1.039, 1.107] | equivalent | 1.456 | 0.000 | 0.000 | 0.0 / 0.0 | True | — |
| v5_prefill_vs_short_L200_C8 | E&Vb | 10 | 0.994 [0.924, 1.070] | equivalent | 1.231 | 0.000 | -0.002 | 0.0 / 3.7 | True | — |
| v5_prefill_vs_short_L200_direct | E&Vb | 10 | 1.063 [1.015, 1.114] | equivalent | 1.449 | 0.000 | 0.001 | 0.0 / 0.0 | True | — |

## H3 scores (victim mean gateway queue, ms)

| Cell/arm | Envelope | Pred | Obs | Seeds within | Pass |
|---|---|---|---|---|---|
| v5_aa_ind_L200_C16/attack | validated | 0.0 | 0.0 | 10/10 | True |
| v5_aa_ind_L200_C16/control | validated | 0.0 | 0.0 | 10/10 | True |
| v5_aa_ind_L200_C32/attack | validated | 0.0 | 0.0 | 10/10 | True |
| v5_aa_ind_L200_C32/control | validated | 0.0 | 0.0 | 10/10 | True |
| v5_aa_ind_L200_C8/attack | validated | 7.9 | 8.7 | 10/10 | True |
| v5_aa_ind_L200_C8/control | validated | 3.1 | 3.5 | 10/10 | True |
| v5_decode_vs_short_L200_C16/attack | validated | 0.0 | 0.0 | 10/10 | True |
| v5_decode_vs_short_L200_C16/control | validated | 0.0 | 0.0 | 10/10 | True |
| v5_decode_vs_short_L200_C32/attack | validated | 0.0 | 0.0 | 10/10 | True |
| v5_decode_vs_short_L200_C32/control | validated | 0.0 | 0.0 | 10/10 | True |
| v5_decode_vs_short_L200_C8/attack | validated | 56.8 | 57.7 | 10/10 | True |
| v5_decode_vs_short_L200_C8/control | validated | 3.0 | 3.3 | 10/10 | True |
| v5_prefill_vs_short_L200_C16/attack | validated | 0.0 | 0.0 | 10/10 | True |
| v5_prefill_vs_short_L200_C16/control | validated | 0.0 | 0.0 | 10/10 | True |
| v5_prefill_vs_short_L200_C32/attack | validated | 0.0 | 0.0 | 10/10 | True |
| v5_prefill_vs_short_L200_C32/control | validated | 0.0 | 0.0 | 10/10 | True |
| v5_prefill_vs_short_L200_C8/attack | validated | 0.0 | 0.0 | 10/10 | True |
| v5_prefill_vs_short_L200_C8/control | validated | 3.4 | 3.7 | 10/10 | True |

Engine-queue figures are engine-global, finish-time aggregates (§5.2); they are not per-victim.
