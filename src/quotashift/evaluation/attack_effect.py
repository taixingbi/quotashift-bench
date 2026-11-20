"""Phase 5 — attack-effect validation analysis (plan §5).

Characterizes whether a workload *scenario* degrades the victim tenant more than its
matched control, under identical, authorized budgets. This is measurement and
reporting only: no defense, no optimization objective, no scheduler contribution.

Primary outputs (per matched attack/control pair, over repeated seeds):
- Victim degradation: victim TTFT / end-to-end median and P95, and the attack-vs-control
  ratio, with successful and timed-out requests separated.
- Attack success rate: fraction of repeated runs whose ratio crosses the scenario's
  *pre-registered* threshold (chosen before any run; never after seeing results).
- Budget-normalized effect: victim slowdown per measured competing workload (tokens and
  requests), so the effect is reported per unit of offered competition, not in the
  abstract.
- Reproducibility: bootstrap confidence interval across seeds, plus a manifest of
  schedule hashes, per-run directories and the exact commands.

Everything here reads the per-request records written by the runner; mock runs are
simulator outputs (`synthetic_backend: true`) and are labelled as such, never reported
as GPU measurements.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# Metric key -> the per-request column it is computed from.
_METRIC_COL = {"ttft_p95": "ttft_ms", "e2e_p95": "e2e_ms"}


@dataclass(frozen=True)
class RunMetrics:
    """Victim-focused metrics for one run directory (one arm, one seed)."""

    run_dir: str
    scenario: str
    arm: str                      # "attack" | "control"
    seed: int
    synthetic_backend: bool
    victim_completed: int
    victim_timed_out: int
    victim_ttft_p50_ms: float
    victim_ttft_p95_ms: float
    victim_e2e_p50_ms: float
    victim_e2e_p95_ms: float
    competitor_requests: int      # measured (completed) competing requests
    competitor_tokens: int        # measured competing input+output tokens

    def as_row(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _pctl(series: pd.Series, q: float) -> float:
    s = series.dropna()
    return float(np.percentile(s, q)) if len(s) else float("nan")


def run_metrics(run_dir: Path, scenario: str, arm: str, seed: int) -> RunMetrics:
    """Compute victim degradation inputs for one run, excluding the warm-up window."""
    summary = json.loads((run_dir / "metrics_summary.json").read_text())
    warmup_s = float(summary.get("warmup_s") or 0.0)
    df = pd.read_parquet(run_dir / "requests.parquet")
    df = df[df["trace_arrival_s"] >= warmup_s]  # cold-start / warm-up separation
    df = df.assign(
        ttft_ms=(df["t_first_token"] - df["t_sent"]) * 1000.0,
        e2e_ms=(df["t_terminal"] - df["t_offered"]) * 1000.0,
    )
    vic = df[df["workload_class"] == "victim"]
    vic_ok = vic[vic["terminal_status"] == "completed"]
    comp_ok = df[(df["workload_class"] == "competitor") & (df["terminal_status"] == "completed")]
    comp_tokens = int((comp_ok["input_token_count"].fillna(0) + comp_ok["output_tokens"].fillna(0)).sum())
    return RunMetrics(
        run_dir=str(run_dir), scenario=scenario, arm=arm, seed=seed,
        synthetic_backend=bool(summary.get("synthetic_backend")),
        victim_completed=int((vic["terminal_status"] == "completed").sum()),
        victim_timed_out=int((vic["terminal_status"] == "timed_out").sum()),
        victim_ttft_p50_ms=_pctl(vic_ok["ttft_ms"], 50), victim_ttft_p95_ms=_pctl(vic_ok["ttft_ms"], 95),
        victim_e2e_p50_ms=_pctl(vic_ok["e2e_ms"], 50), victim_e2e_p95_ms=_pctl(vic_ok["e2e_ms"], 95),
        competitor_requests=int(len(comp_ok)),
        competitor_tokens=comp_tokens,
    )


def bootstrap_ci(values: list[float], *, n: int = 10000, seed: int = 0, alpha: float = 0.05) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean of `values` (deterministic given seed)."""
    arr = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if len(arr) == 0:
        return (float("nan"), float("nan"))
    if len(arr) == 1:
        return (float(arr[0]), float(arr[0]))
    rng = np.random.default_rng(seed)
    means = rng.choice(arr, size=(n, len(arr)), replace=True).mean(axis=1)
    return (float(np.percentile(means, 100 * alpha / 2)), float(np.percentile(means, 100 * (1 - alpha / 2))))


def _metric_value(m: RunMetrics, metric: str) -> float:
    return {"ttft_p95": m.victim_ttft_p95_ms, "e2e_p95": m.victim_e2e_p95_ms}[metric]


def analyze_pair(
    attack: list[RunMetrics], control: list[RunMetrics], *, metric: str, threshold: float,
) -> dict:
    """Victim degradation ratios, attack-success rate and a bootstrap CI for one pair.

    Ratios are computed per matched seed (attack / control); runs are paired on seed so
    each ratio holds the schedule's random draw fixed between arms.
    """
    a_by_seed = {m.seed: m for m in attack}
    c_by_seed = {m.seed: m for m in control}
    seeds = sorted(set(a_by_seed) & set(c_by_seed))
    per_seed = []
    for s in seeds:
        a, c = a_by_seed[s], c_by_seed[s]
        cv, av = _metric_value(c, metric), _metric_value(a, metric)
        ratio = av / cv if cv and np.isfinite(cv) and cv > 0 else float("nan")
        per_seed.append({
            "seed": s, "attack_ms": av, "control_ms": cv, "ratio": ratio,
            "crosses_threshold": bool(np.isfinite(ratio) and ratio >= threshold),
            "attack_victim_timed_out": a.victim_timed_out, "control_victim_timed_out": c.victim_timed_out,
            "competitor_tokens": a.competitor_tokens, "competitor_requests": a.competitor_requests,
        })
    ratios = [r["ratio"] for r in per_seed if np.isfinite(r["ratio"])]
    crossings = [r for r in per_seed if r["crosses_threshold"]]
    lo, hi = bootstrap_ci(ratios)
    # Budget-normalized: victim slowdown (ratio-1) per measured competing load.
    mean_comp_tokens = float(np.mean([r["competitor_tokens"] for r in per_seed])) if per_seed else float("nan")
    mean_comp_reqs = float(np.mean([r["competitor_requests"] for r in per_seed])) if per_seed else float("nan")
    mean_ratio = float(np.mean(ratios)) if ratios else float("nan")
    slowdown = mean_ratio - 1.0 if np.isfinite(mean_ratio) else float("nan")
    return {
        "metric": metric,
        "preregistered_threshold": threshold,
        "n_seeds": len(per_seed),
        "per_seed": per_seed,
        "mean_ratio": mean_ratio,
        "median_ratio": float(np.median(ratios)) if ratios else float("nan"),
        "ratio_ci95": [lo, hi],
        "attack_success_rate": (len(crossings) / len(per_seed)) if per_seed else float("nan"),
        "mean_competitor_tokens": mean_comp_tokens,
        "mean_competitor_requests": mean_comp_reqs,
        "slowdown_per_1k_competitor_tokens": (slowdown / (mean_comp_tokens / 1000.0))
        if mean_comp_tokens and np.isfinite(slowdown) else float("nan"),
        "slowdown_per_100_competitor_requests": (slowdown / (mean_comp_reqs / 100.0))
        if mean_comp_reqs and np.isfinite(slowdown) else float("nan"),
    }


def _fmt(x: float, n: int = 2) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{n}f}"


def write_report(
    scenario_id: str, pairs: dict, analysis: dict, attack: list[RunMetrics],
    control: list[RunMetrics], out_dir: Path, *, commands: list[str],
) -> dict:
    """Write summary.csv, summary.md, figures and manifest.json. Returns written paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [m.as_row() for m in (*attack, *control)]
    csv_path = out_dir / "summary.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    synthetic = any(m.synthetic_backend for m in (*attack, *control))
    figs = _figures(scenario_id, analysis, out_dir)

    a = analysis
    md = [
        f"# QuotaShift attack-effect report — `{scenario_id}`", "",
        ("> **Synthetic backend (mock): plumbing evidence only, not a GPU measurement.**"
         if synthetic else "> Live target measurements."), "",
        f"- Control: `{pairs['control_label']}`  ·  seeds: {a['n_seeds']}  ·  "
        f"degradation metric: `{a['metric']}`",
        f"- **Pre-registered threshold: {a['preregistered_threshold']}×** (fixed before runs; ADR-Q08).", "",
        "## Victim degradation (attack vs matched control)", "",
        f"- Mean victim slowdown ratio: **{_fmt(a['mean_ratio'])}×**  "
        f"(median {_fmt(a['median_ratio'])}×, 95% bootstrap CI "
        f"[{_fmt(a['ratio_ci95'][0])}, {_fmt(a['ratio_ci95'][1])}])",
        f"- **Attack success rate: {_fmt(100 * a['attack_success_rate'], 0)}%** "
        f"of {a['n_seeds']} runs crossed the threshold.",
        "",
        "### Budget-normalized effect",
        f"- Mean measured competing load: {_fmt(a['mean_competitor_tokens'], 0)} tokens, "
        f"{_fmt(a['mean_competitor_requests'], 0)} requests per run.",
        f"- Victim slowdown per 1k competing tokens: {_fmt(a['slowdown_per_1k_competitor_tokens'], 4)}",
        f"- Victim slowdown per 100 competing requests: {_fmt(a['slowdown_per_100_competitor_requests'], 4)}",
        "",
        "### Per-seed detail (matched pairs)", "",
        "| seed | attack ms | control ms | ratio | ≥ threshold | victim timeouts (a/c) |",
        "|---|---|---|---|---|---|",
    ]
    for r in a["per_seed"]:
        md.append(
            f"| {r['seed']} | {_fmt(r['attack_ms'])} | {_fmt(r['control_ms'])} | {_fmt(r['ratio'])} | "
            f"{'yes' if r['crosses_threshold'] else 'no'} | "
            f"{r['attack_victim_timed_out']}/{r['control_victim_timed_out']} |")
    verdict = ("effect crosses the pre-registered threshold on a majority of runs"
               if a["attack_success_rate"] >= 0.5 else
               "effect does NOT reach the pre-registered threshold on a majority of runs "
               "(reported as a negative result, per the plan)")
    md += ["", "## Verdict", "", f"Under matched budgets, the {verdict}.", ""]
    md_path = out_dir / "summary.md"
    md_path.write_text("\n".join(md) + "\n")

    manifest = {
        "scenario_id": scenario_id,
        "control_label": pairs["control_label"],
        "seeds": pairs["seeds"],
        "synthetic_backend": synthetic,
        "metric": a["metric"],
        "preregistered_threshold": a["preregistered_threshold"],
        "budget_tolerance": pairs.get("budget_tolerance"),
        "per_seed_budget": {str(s): pairs["budgets"][s] for s in pairs["seeds"]},
        "run_dirs": {
            "attack": {str(s): str(p) for s, p in pairs["attack"].items()},
            "control": {str(s): str(p) for s, p in pairs["control"].items()},
        },
        "analysis": {k: v for k, v in a.items() if k != "per_seed"},
        "commands": commands,
    }
    man_path = out_dir / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2, default=float) + "\n")
    return {"csv": str(csv_path), "md": str(md_path), "manifest": str(man_path), "figures": [str(p) for p in figs]}


def _figures(scenario_id: str, analysis: dict, out_dir: Path) -> list[Path]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # pragma: no cover - matplotlib optional at runtime
        return []
    ps = analysis["per_seed"]
    if not ps:
        return []
    seeds = [str(r["seed"]) for r in ps]
    x = np.arange(len(seeds))
    out: list[Path] = []

    def _save(fig, name: str) -> Path:
        fig.tight_layout()
        p = out_dir / name
        fig.savefig(p, dpi=130)
        plt.close(fig)
        return p

    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(x - 0.2, [r["control_ms"] for r in ps], 0.4, label="control", color="#4c78a8")
    ax.bar(x + 0.2, [r["attack_ms"] for r in ps], 0.4, label="attack", color="#e45756")
    ax.set_xticks(x)
    ax.set_xticklabels(seeds)
    ax.set_xlabel("seed")
    ax.set_ylabel(f"victim {analysis['metric']} (ms)")
    ax.set_title(f"{scenario_id}: victim {analysis['metric']} — attack vs control")
    ax.legend()
    out.append(_save(fig, "figure_victim_latency.png"))

    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(x, [r["ratio"] for r in ps], 0.6, color="#e45756")
    ax.axhline(analysis["preregistered_threshold"], ls="--", color="black",
               label=f"threshold {analysis['preregistered_threshold']}×")
    ax.axhline(1.0, ls=":", color="gray")
    lo, hi = analysis["ratio_ci95"]
    if np.isfinite(lo):
        ax.axhspan(lo, hi, color="#e45756", alpha=0.12, label="mean 95% CI")
    ax.set_xticks(x)
    ax.set_xticklabels(seeds)
    ax.set_xlabel("seed")
    ax.set_ylabel("victim slowdown ratio (attack/control)")
    ax.set_title(f"{scenario_id}: degradation ratio vs pre-registered threshold")
    ax.legend()
    out.append(_save(fig, "figure_degradation_ratio.png"))
    return out
