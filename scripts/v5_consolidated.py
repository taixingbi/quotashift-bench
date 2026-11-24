"""POST-HOC, read-only: consolidated v5 tables and paper figures (docs/RESULTS_V4_V5.md).

    uv run python scripts/v5_consolidated.py            # -> reports/v5/consolidated/{*.csv,*.json,fig*.pdf,fig*.png}

Inputs (never modified):
  reports/v5/analysis_B.json          frozen analysis output (contains every Stage A and Stage B cell)
  experiments/v5/FCFS_PREDICTIONS.json  frozen per-seed FCFS predictions + tolerances
  results/v5_*/<run>/requests.parquet raw request logs, only for the post-hoc slot-demand quantity

Nothing here is a preregistered test. The frozen verdicts live in reports/v5/ANALYSIS_{A,B}.md. This script only
re-tabulates frozen outputs (prediction errors, SLO, queueing) and computes one post-hoc descriptive quantity:
offered slot demand = sum over all requests of (t_terminal - t_sent) / (C * runtime_seconds), per arm. It is
undefined on the direct path (no cap) and reported as NaN there.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "reports" / "v5" / "consolidated"
ANALYSIS = REPO / "reports" / "v5" / "analysis_B.json"
PRED = REPO / "experiments" / "v5" / "FCFS_PREDICTIONS.json"
RUNTIME_S = 120.0
NONZERO_MS = 1.0

# Reference categorical palette (dataviz skill, light mode), slots 1-3 only: validated all-pairs.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, MUTED = "#0b0b0b", "#52514e", "#e4e3df", "#9a9993"
CMP_LABEL = {"decode_vs_short": "D vs S", "prefill_vs_short": "P vs S", "aa_ind": "A/A-ind"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8,
    "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7.5, "axes.edgecolor": INK2,
    "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "lines.linewidth": 2, "savefig.dpi": 300, "pdf.fonttype": 42,
})


def cap_key(c: dict) -> str:
    return "direct" if c["C"] is None else f"C{c['C']}"


def load() -> tuple[dict, dict]:
    return json.loads(ANALYSIS.read_text()), json.loads(PRED.read_text())


def per_seed_frame(an: dict) -> pd.DataFrame:
    rows = []
    for cid, c in an["cells"].items():
        for s in c["per_seed"]:
            for arm in ("attack", "control"):
                a = s[arm]
                rows.append({
                    "cell": cid, "comparison": c["comparison"], "L": c["L"], "cap": cap_key(c), "C": c["C"],
                    "seed": s["seed"], "arm": arm, "log_ratio": s["log_ratio"],
                    "user_ttft_mean_ms": a["user_ttft_mean_ms"], "backend_ttft_mean_ms": a["backend_ttft_mean_ms"],
                    "gateway_queue_mean_ms": a["gateway_queue_mean_ms"], "gateway_queue_p95_ms": a["gateway_queue_p95_ms"],
                    "slo_success": a["slo_success"], "frac_user_ttft_gt_500ms": a["frac_user_ttft_gt_500ms"],
                    "frac_user_ttft_gt_2000ms": a["frac_user_ttft_gt_2000ms"],
                    "frac_time_at_cap": a["slot"]["frac_time_at_cap"],
                    "victims_during_saturation": a["slot"]["victim_arrivals_during_saturation"],
                    "h3_obs_ms": a["slot"].get("h3_obs_victim_queue_mean_ms"),
                    "victim_censored": s["victim_censored"][0 if arm == "attack" else 1],
                    "engine_queue_mean_ms": 1000 * a["engine_queue"]["sum_s"] / a["engine_queue"]["count"]
                    if a["engine_queue"]["count"] else math.nan,
                })
    return pd.DataFrame(rows)


def slot_demand(an: dict) -> pd.DataFrame:
    """POST-HOC: offered slot demand per arm from raw requests.parquet."""
    rows = []
    for stage_dir in ("stage_a", "stage_b"):
        for man in sorted((REPO / "reports" / "v5" / stage_dir).glob("*/manifest.json")):
            m = json.loads(man.read_text())
            cid = m["scenario_id"]
            c = an["cells"][cid]
            for arm, seeds in m["run_dirs"].items():
                for seed, rd in seeds.items():
                    df = pd.read_parquet(Path(rd) / "requests.parquet",
                                         columns=["workload_class", "t_sent", "t_terminal"]).dropna()
                    hold = df.t_terminal - df.t_sent
                    comp = hold[df.workload_class == "competitor"].sum()
                    vic = hold[df.workload_class != "competitor"].sum()
                    denom = (c["C"] or math.nan) * RUNTIME_S
                    rows.append({"cell": cid, "comparison": c["comparison"], "L": c["L"], "cap": cap_key(c),
                                 "seed": int(seed), "arm": arm, "competitor_slot_s": comp, "victim_slot_s": vic,
                                 "slot_demand_ratio": (comp + vic) / denom})
    return pd.DataFrame(rows)


def prediction_errors(an: dict, pr: dict, ps: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    h3 = an["hypotheses"]["H3"]["scores"]
    seed_rows, cell_rows = [], []
    for key, sc in h3.items():
        cid, arm = key.split("/")
        pc = pr["cells"][cid]
        for seed, sp in pc["seeds"].items():
            pred = sp[arm]["victim_queue_mean_ms"]
            obs = ps[(ps.cell == cid) & (ps.arm == arm) & (ps.seed == int(seed))].h3_obs_ms.iloc[0]
            seed_rows.append({"cell": cid, "arm": arm, "seed": int(seed), "envelope": "validated" if sc["validated_envelope"] else "extrapolated",
                              "pred_ms": pred, "obs_ms": obs, "err_ms": obs - pred,
                              "rel_err": (obs - pred) / pred if pred > 0 else math.nan})
        cell_rows.append({"cell": cid, "arm": arm, "envelope": "validated" if sc["validated_envelope"] else "extrapolated", "pass": sc.get("pass")})
    sd = pd.DataFrame(seed_rows)
    cm = sd.groupby(["cell", "arm", "envelope"], as_index=False).agg(pred_ms=("pred_ms", "mean"), obs_ms=("obs_ms", "mean"))
    cm["err_ms"] = cm.obs_ms - cm.pred_ms
    # Case is assigned per (cell, arm) from the frozen predicted cell mean, and inherited by its seeds.
    # POST-HOC split: "nonzero" iff predicted cell mean >= NONZERO_MS (1 ms); below that the prediction is
    # "queueing vanishes" (H3's falsifiable content at C >= 16) and a relative error is not meaningful.
    cm["case"] = np.where(cm.pred_ms >= NONZERO_MS, "nonzero", "zero")
    cm["rel_err"] = np.where(cm.case == "nonzero", cm.err_ms / cm.pred_ms, np.nan)
    cm["direction"] = np.where(cm.err_ms > 0, "under-predicted (obs > pred)",
                               np.where(cm.err_ms < 0, "over-predicted (obs < pred)", "exact"))
    cm = cm.merge(pd.DataFrame(cell_rows), on=["cell", "arm", "envelope"])
    sd = sd.merge(cm[["cell", "arm", "case"]], on=["cell", "arm"])
    sd.loc[sd.case == "zero", "rel_err"] = math.nan
    return sd, cm


def error_summary(sd: pd.DataFrame, cm: pd.DataFrame) -> dict:
    out: dict = {}
    for env in ("validated", "extrapolated"):
        for case in ("zero", "nonzero"):
            s = sd[(sd.envelope == env) & (sd.case == case)]
            c = cm[(cm.envelope == env) & (cm.case == case)]
            if s.empty:
                continue
            d = {"n_cell_arms": len(c), "n_seed_scores": len(s),
                 "cell_mae_ms": float(c.err_ms.abs().mean()), "cell_max_abs_err_ms": float(c.err_ms.abs().max()),
                 "seed_mae_ms": float(s.err_ms.abs().mean()), "seed_max_abs_err_ms": float(s.err_ms.abs().max()),
                 "seed_bias_ms": float(s.err_ms.mean())}
            if case == "nonzero":
                d |= {"cell_rel_err": {f"{r.cell}/{r.arm}": round(float(r.rel_err), 4) for r in c.itertuples()},
                      "cell_median_abs_rel_err": float(c.rel_err.abs().median()),
                      "seed_median_abs_rel_err": float(s.rel_err.abs().median()),
                      "seed_frac_obs_gt_pred": float((s.err_ms > 0).mean()),
                      "seed_frac_obs_lt_pred": float((s.err_ms < 0).mean()),
                      "per_cell_seed_err_ms": {
                          f"{r.cell}/{r.arm}": {"min": float(g.err_ms.min()), "max": float(g.err_ms.max()),
                                               "n_obs_lt_pred": int((g.err_ms < 0).sum()),
                                               "rel_min": float(g.rel_err.min()), "rel_max": float(g.rel_err.max())}
                          for r in c.itertuples() for g in [s[(s.cell == r.cell) & (s.arm == r.arm)]]}}
            else:
                d |= {"seed_frac_obs_gt_5ms": float((s.obs_ms > 5).mean()), "seed_max_obs_ms": float(s.obs_ms.max())}
            out[f"{env}/{case}"] = d
    return out


# ---------------------------------------------------------------------------------------------------- figures

def _save(fig, name: str) -> None:
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)


CAPS = ["C8", "C16", "C32", "direct"]


def fig_cap_sensitivity(an: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.6), sharey=True)
    series = {200: [("decode_vs_short", BLUE), ("prefill_vs_short", ORANGE), ("aa_ind", AQUA)],
              400: [("decode_vs_short", BLUE), ("aa_ind", AQUA)]}
    for ax, L in zip(axes, (200, 400), strict=True):
        ax.axhspan(0.8, 1.25, color=GRID, alpha=0.6, lw=0, zorder=0)
        ax.axhline(1.0, color=MUTED, lw=0.8, zorder=1)
        for j, (cmp, col) in enumerate(series[L]):
            xs, ys, lo, hi = [], [], [], []
            for i, cap in enumerate(CAPS):
                cid = f"v5_{cmp}_L{L}_{cap}"
                if cid not in an["cells"]:
                    continue
                p = an["cells"][cid]["summary"]["primary"]
                xs.append(i + (j - 1) * 0.12)
                ys.append(p["ratio"])
                lo.append(p["ci95"][0])
                hi.append(p["ci95"][1])
            ys_a = np.array(ys)
            ax.errorbar(xs, ys_a, yerr=[ys_a - np.array(lo), np.array(hi) - ys_a], fmt="o", ms=5, color=col,
                        ecolor=col, elinewidth=1.4, capsize=0, label=CMP_LABEL[cmp], mec="white", mew=0.8, zorder=3)
        ax.set_yscale("log")
        ax.set_xticks(range(4), ["C=8", "C=16", "C=32", "direct"])
        ax.set_title(f"L = {L} tok/s")
        ax.set_xlim(-0.5, 3.5)
    axes[0].set_ylabel("Victim mean TTFT ratio, attack/control\n(geo-mean of 10 seeds, 95% CI)")
    axes[0].set_yticks([0.8, 1, 1.25, 2, 5, 10, 20], ["0.8", "1", "1.25", "2", "5", "10", "20"])
    for a in axes:
        a.minorticks_off()
    axes[1].annotate("18.1×\nthreshold not\nabove noise", xy=(0.12 * -1 + 0, 18.1), xytext=(0.55, 9),
                     fontsize=7, color=INK2, arrowprops={"arrowstyle": "-", "color": MUTED, "lw": 0.8})
    h, lab = axes[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.07))
    fig.text(0.5, -0.04, "Shaded band: preregistered equivalence band [0.8, 1.25]. No L = 400 P vs S or direct A/A cells "
             "exist in the frozen design.", ha="center", fontsize=6.5, color=INK2)
    _save(fig, "fig1_cap_sensitivity")


def _arm_strip(ax, ps: pd.DataFrame, cells: list[tuple[str, str]], col: str, log: bool) -> None:
    for i, (cid, _) in enumerate(cells):
        for k, (arm, c) in enumerate((("control", ORANGE), ("attack", BLUE))):
            v = ps[(ps.cell == cid) & (ps.arm == arm)][col].to_numpy()
            x = i + (k - 0.5) * 0.32
            jit = np.linspace(-0.07, 0.07, len(v))
            ax.scatter(x + jit, v, s=9, color=c, alpha=0.55, lw=0, zorder=2)
            ax.plot([x - 0.12, x + 0.12], [v.mean()] * 2, color=c, lw=2, solid_capstyle="round", zorder=3,
                    label=arm if i == 0 else None)
    ax.set_xticks(range(len(cells)), [lab for _, lab in cells])
    if log:
        ax.set_yscale("log")


def fig_latency_queue(ps: pd.DataFrame) -> None:
    panels = [("decode_vs_short", 200), ("decode_vs_short", 400), ("prefill_vs_short", 200)]
    fig, axes = plt.subplots(2, 3, figsize=(7.2, 4.4), sharex="col")
    for j, (cmp, L) in enumerate(panels):
        cells = [(f"v5_{cmp}_L{L}_{c}", c.replace("C", "C=")) for c in CAPS]
        _arm_strip(axes[0, j], ps, cells, "user_ttft_mean_ms", True)
        sub = ps.copy()
        sub["gq"] = sub.gateway_queue_mean_ms.clip(lower=0.1)
        _arm_strip(axes[1, j], sub, cells, "gq", True)
        axes[0, j].set_title(f"{CMP_LABEL[cmp]}, L = {L}")
        axes[1, j].set_ylim(0.07, 2e4)
    axes[0, 0].set_ylabel("Victim user-facing TTFT,\nmean per seed (ms)")
    axes[1, 0].set_ylabel("Victim gateway queue,\nmean per seed (ms; 0 → 0.1)")
    for ax in axes[0]:
        ax.set_ylim(60, 8000)
    h, lab = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, lab, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 1.03))
    fig.text(0.5, -0.02, "Dots: 10 seeds per arm; bars: mean over seeds. Backend TTFT (not shown) has cell means 82–89 ms in every arm; "
             "the attack-control difference is gateway queueing.", ha="center", fontsize=6.5, color=INK2)
    fig.tight_layout()
    _save(fig, "fig2_latency_and_gateway_queue")


def fig_slo(ps: pd.DataFrame) -> None:
    panels = [("decode_vs_short", 200), ("decode_vs_short", 400), ("prefill_vs_short", 200), ("aa_ind", 400)]
    fig, axes = plt.subplots(1, 4, figsize=(7.2, 2.3), sharey=True)
    for ax, (cmp, L) in zip(axes, panels, strict=True):
        cells = [(f"v5_{cmp}_L{L}_{c}", c.replace("C", "C=")) for c in CAPS if f"v5_{cmp}_L{L}_{c}" in set(ps.cell)]
        _arm_strip(ax, ps, cells, "slo_success", False)
        ax.axhline(0.95, color=MUTED, lw=0.8, ls=(0, (3, 2)))
        ax.set_title(f"{CMP_LABEL[cmp]}, L = {L}")
        ax.tick_params(axis="x", labelsize=6.5)
    axes[0].set_ylabel("Victim offered-load\nSLO success")
    axes[0].set_ylim(0, 1.04)
    h, lab = axes[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 1.1))
    fig.text(0.5, -0.06, "Dashed line: baseline-feasibility floor 0.95 (applies to the control arm only, §4.2). "
             "Only D vs S at L = 400, C = 8 departs from 1.0.", ha="center", fontsize=6.5, color=INK2)
    fig.tight_layout()
    _save(fig, "fig3_victim_slo_success")


def fig_slot_demand(ps: pd.DataFrame, sd: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.0), gridspec_kw={"wspace": 0.55})
    ax = axes[0]
    g = sd[sd.cap != "direct"].groupby(["cell", "comparison", "L", "cap", "arm"], as_index=False).slot_demand_ratio.mean()
    order = [(cmp, L, cap) for cmp, L in (("decode_vs_short", 200), ("decode_vs_short", 400), ("prefill_vs_short", 200),
                                          ("aa_ind", 200), ("aa_ind", 400)) for cap in ("C8", "C16", "C32")]
    labels = []
    for i, (cmp, L, cap) in enumerate(order):
        for k, (arm, c) in enumerate((("control", ORANGE), ("attack", BLUE))):
            v = g[(g.comparison == cmp) & (g.L == L) & (g.cap == cap) & (g.arm == arm)].slot_demand_ratio
            if v.empty:
                continue
            ax.barh(i + (k - 0.5) * 0.38, v.iloc[0], height=0.34, color=c, label=arm if i == 0 else None)
        labels.append(f"{CMP_LABEL[cmp]} L{L} {cap.replace('C', 'C=')}")
    ax.axvline(1.0, color=MUTED, lw=0.8, ls=(0, (3, 2)))
    ax.set_yticks(range(len(order)), labels, fontsize=6.3)
    ax.invert_yaxis()
    ax.set_xlabel("Offered slot demand / (C × 120 s), mean of 10 seeds")
    ax.set_title("(a) Slot demand / capacity [post-hoc]")
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, loc="lower right")
    ax = axes[1]
    gw = ps[ps.cap != "direct"]
    for arm, c in (("control", ORANGE), ("attack", BLUE)):
        s = gw[gw.arm == arm]
        ax.scatter(s.victims_during_saturation, s.gateway_queue_mean_ms.clip(lower=0.1), s=10, color=c, alpha=0.6,
                   lw=0, label=arm)
    ax.set_yscale("log")
    ax.set_xlabel("Fraction of victims arriving during saturation (k = C)")
    ax.set_ylabel("Victim gateway queue,\nmean per seed (ms; 0 → 0.1)")
    ax.set_title("(b) H5: ρ = 0.998, n = 300 gateway arms")
    ax.legend(frameon=False, loc="lower right")
    _save(fig, "fig4_slot_time_demand")


def fig_predictions(sdp: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.9))
    ax = axes[0]
    nz = sdp[sdp.case == "nonzero"]
    for env, c, mk in (("validated", BLUE, "o"), ("extrapolated", ORANGE, "s")):
        s = nz[nz.envelope == env]
        ax.scatter(s.pred_ms, s.obs_ms, s=12, color=c, marker=mk, alpha=0.7, lw=0, label=f"{env}")
    lim = [1, 2e4]
    ax.plot(lim, lim, color=MUTED, lw=0.8)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_xlabel("Predicted victim gateway queue mean (ms)")
    ax.set_ylabel("Observed (ms)")
    ax.set_title("(a) Nonzero-queue cells (pred ≥ 1 ms), per seed")
    ax.legend(frameon=False, loc="upper left")
    ax = axes[1]
    cm = (nz.groupby(["cell", "arm", "envelope"], as_index=False).agg(pred=("pred_ms", "mean"), obs=("obs_ms", "mean")))
    cm["rel"] = (cm.obs - cm.pred) / cm.pred
    cm["env_order"] = cm.envelope.map({"validated": 0, "extrapolated": 1})
    cm = cm.sort_values(["env_order", "pred"], ascending=[False, False])
    lab = [f"{r.cell.replace('v5_', '').replace('_vs_short', '').replace('aa_ind', 'A/A')}/{r.arm[:3]}"
           for r in cm.itertuples()]
    cols = [BLUE if e == "validated" else ORANGE for e in cm.envelope]
    ax.barh(range(len(cm)), cm.rel * 100, color=cols, height=0.6)
    ax.axvline(0, color=INK2, lw=0.8)
    ax.set_yticks(range(len(cm)), lab, fontsize=6.3)
    ax.set_xlabel("Relative error of the cell mean, (obs − pred)/pred (%)")
    ax.set_title("(b) Cell-mean relative error (> 0: under-predicted)")
    ax.grid(axis="y", visible=False)
    for i, r in enumerate(cm.itertuples()):
        ax.text(r.rel * 100 + (1 if r.rel >= 0 else -1), i, f"{r.rel * 100:+.1f}%", va="center",
                ha="left" if r.rel >= 0 else "right", fontsize=6, color=INK2)
    ax.set_xlim(-45, 65)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=BLUE, label="validated, L=200"), Patch(color=ORANGE, label="extrapolated, L=400")],
              frameon=False, loc="upper left", bbox_to_anchor=(0.68, 0.99), fontsize=6.5, handlelength=1.2)
    fig.tight_layout()
    _save(fig, "fig5_fcfs_prediction_error")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    an, pr = load()
    ps = per_seed_frame(an)
    assert len(ps) == 19 * 10 * 2, len(ps)
    assert (ps.h3_obs_ms.dropna().round(6) == ps.loc[ps.h3_obs_ms.notna(), "gateway_queue_mean_ms"].round(6)).all()
    sd = slot_demand(an)
    sdp, cm = prediction_errors(an, pr, ps)
    summ = error_summary(sdp, cm)
    ps.to_csv(OUT / "per_seed_arm.csv", index=False)
    sd.to_csv(OUT / "slot_demand_posthoc.csv", index=False)
    sdp.to_csv(OUT / "fcfs_prediction_errors_per_seed.csv", index=False)
    cm.to_csv(OUT / "fcfs_prediction_errors_per_cell.csv", index=False)
    (OUT / "fcfs_prediction_error_summary.json").write_text(json.dumps(summ, indent=1) + "\n")
    fig_cap_sensitivity(an)
    fig_latency_queue(ps)
    fig_slo(ps)
    fig_slot_demand(ps, sd)
    fig_predictions(sdp)
    print(json.dumps(summ, indent=1))
    print(cm.to_string())
    g = sd.groupby(["cell", "arm"]).slot_demand_ratio.mean().unstack()
    print(g.round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
