"""Figures rebuilt automatically from saved raw results (never hand-edited).

Each PNG gets a sibling `<name>.caption.json` stating backend, model,
hardware, trials and the interval definition. Mock-backend figures carry a
visible watermark.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

WATERMARK = "MOCK BACKEND - SYNTHETIC TIMINGS - NOT GPU DATA"


def _ctx(run_dir: Path) -> dict:
    m = json.loads((run_dir / "manifest.json").read_text())
    gpu = m.get("gpu", {})
    return {
        "backend_kind": m.get("backend_kind"),
        "synthetic": m.get("synthetic_backend"),
        "model": (m.get("backend_info") or {}).get("model") or (m.get("backend_info") or {}).get("/v1/models"),
        "hardware": gpu.get("gpus") if gpu.get("available") else f"no NVIDIA GPU detected ({m.get('machine')})",
        "run_id": m.get("run_id"),
        "seed": m.get("seed"),
    }


def _finish(fig, ax_or_axes, path: Path, ctx: dict, caption: str) -> None:
    if ctx.get("synthetic"):
        fig.text(0.5, 0.5, WATERMARK, ha="center", va="center", fontsize=16, color="red", alpha=0.18, rotation=20)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    path.with_suffix(".caption.json").write_text(json.dumps(ctx | {"caption": caption}, indent=2, default=str))


def plot_e0(run_dir: Path) -> list[Path]:
    ctx = _ctx(run_dir)
    figs: list[Path] = []
    cells_p = run_dir / "cells.parquet"
    if cells_p.exists():
        cells = pd.read_parquet(cells_p)
        ok = cells[cells["status"] == "ok"] if "status" in cells else cells.iloc[0:0]
        metrics = [
            ("output_tok_per_s", "output tokens/s"),
            ("ttft_p95_ms", "P95 TTFT (ms)"),
            ("tpot_p50_ms", "P50 TPOT (ms)"),
            ("kv_usage_max", "max KV-cache usage (fraction)"),
            ("engine_waiting_max", "max engine waiting requests"),
            ("preemptions", "preemptions per cell"),
        ]
        prompts = sorted(ok["prompt_tokens"].unique()) if len(ok) else []
        for col, label in metrics:
            if not len(ok) or col not in ok or ok[col].dropna().empty:
                continue
            fig, axes = plt.subplots(1, len(prompts), figsize=(4.2 * len(prompts), 3.4), squeeze=False)
            for ax, p in zip(axes[0], prompts, strict=False):
                sub = ok[ok["prompt_tokens"] == p]
                for o, g in sub.groupby("max_tokens"):
                    a = g.groupby("concurrency")[col].agg(["mean", "min", "max"]).reset_index()
                    ax.plot(a["concurrency"], a["mean"], marker="o", label=f"max_tokens={o}")
                    ax.fill_between(a["concurrency"], a["min"], a["max"], alpha=0.15)
                ax.set_xscale("log", base=2)
                ax.set_title(f"prompt={p} tok")
                ax.set_xlabel("concurrency (closed loop)")
                ax.set_ylabel(label)
                ax.legend(fontsize=7)
            path = run_dir / "figures" / f"e0_{col}_vs_concurrency.png"
            n_tr = int(ok.groupby(["prompt_tokens", "max_tokens", "concurrency"]).size().min())
            _finish(fig, axes, path, ctx, f"E0 {label} vs concurrency; line=mean, band=min-max across {n_tr}+ trials "
                                          "(descriptive range, not a CI). Skipped/failed cells omitted from lines and "
                                          "listed in cells.csv.")
            figs.append(path)
    sweep_p = run_dir / "rate_sweep.parquet"
    if sweep_p.exists():
        sw = pd.read_parquet(sweep_p)
        sw = sw[sw["status"] == "ok"]
        if len(sw):
            num = ["completed_rps", "slo_goodput_rps", "ttft_p95_ms"]
            a = sw.groupby("rate_rps")[num].agg(["mean", "min", "max"])
            fig, ax = plt.subplots(1, 2, figsize=(9, 3.6))
            r = a.index.values
            ax[0].plot(r, r, "k--", lw=0.8, label="offered = served")
            for c, lab in (("completed_rps", "completed in-window req/s"), ("slo_goodput_rps", "SLO goodput req/s")):
                ax[0].plot(r, a[(c, "mean")], marker="o", label=lab)
                ax[0].fill_between(r, a[(c, "min")], a[(c, "max")], alpha=0.15)
            ax[0].set_xlabel("offered rate (req/s, Poisson)")
            ax[0].set_ylabel("req/s")
            ax[0].legend(fontsize=7)
            ax[1].plot(r, a[("ttft_p95_ms", "mean")], marker="o", label="P95 TTFT")
            ax[1].fill_between(r, a[("ttft_p95_ms", "min")], a[("ttft_p95_ms", "max")], alpha=0.15)
            ax[1].set_yscale("log")
            ax[1].set_xlabel("offered rate (req/s)")
            ax[1].set_ylabel("ms")
            ax[1].legend(fontsize=7)
            path = run_dir / "figures" / "e0_rate_sweep.png"
            _finish(fig, ax, path, ctx, "E0 open-loop offered-load sweep; mean with min-max band across trials.")
            figs.append(path)
    return figs


def plot_run(run_dir: Path) -> list[Path]:
    """Per-tenant summary figure for a multi-tenant run."""
    ctx = _ctx(run_dir)
    s = json.loads((run_dir / "metrics_summary.json").read_text())
    per = s.get("per_tenant", {})
    if not per:
        return []
    tenants = sorted(per)
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.4))
    ax[0].bar(tenants, [per[t]["slo_attainment"] or 0 for t in tenants])
    ax[0].set_ylim(0, 1.05)
    ax[0].set_ylabel("SLO attainment (of offered)")
    statuses = ["completed", "rejected", "timed_out", "backend_error", "cancelled"]
    bottom = [0] * len(tenants)
    for st in statuses:
        vals = [per[t]["status_counts"].get(st, 0) for t in tenants]
        ax[1].bar(tenants, vals, bottom=bottom, label=st)
        bottom = [b + v for b, v in zip(bottom, vals, strict=False)]
    ax[1].set_ylabel("offered requests by terminal status")
    ax[1].legend(fontsize=7)
    path = run_dir / "figures" / "per_tenant.png"
    _finish(fig, ax, path, ctx, f"Per-tenant SLO attainment and terminal-status accounting; single run (seed {ctx['seed']}), "
                                "no interval.")
    return [path]
