"""X2 Amendment A2 (DRAFT) offline validation: coverage matrix, conservation, pairing, independence, determinism,
frozen gates, and the original-vs-stratified arrival comparison. Zero cost: no server, no GPU, no network.

    uv run python scripts/x2_a2_validate.py --platform g1m0     # -> reports/x2_a2/A2_VALIDATION_<p>.{json,md}

For every A2 main file and every rerun file, every intended seed and both arms, against the ORIGINAL X2 file:
  coverage  frozen v4 gate (first competitor arrival <= 0.25 T, last >= 0.75 T), original and A2;
  strata    A2 places exactly one competitor arrival in each of the N equal strata of [0, T);
  conserve  competitor request count, authorized competitor tokens, request ids, shapes and prompt text equal the
            original; victims (ids, arrival times, prompts, shapes) byte-identical to the original;
  pairing   victims identical between the attack and control arms; frozen matched-budget gate passes;
  aa_ind    X2b: attack and control competitor arrival streams differ (independent A/A);
  determin  a fresh load regenerates the same schedule hash.
Then the frozen offline freeze (every frozen gate) is run on the A2 root, and on the original files to reproduce the
refusal. Arrivals do not depend on the tokenizer (frozen check), so the offline stand-in tokenizer is sufficient here.
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_v5  # noqa: E402  (frozen)
import build_x2  # noqa: E402  (frozen)
import build_x2_a2  # noqa: E402
import freeze_v4  # noqa: E402  (frozen)
import freeze_v5  # noqa: E402  (frozen)
import freeze_x2_traces as fx  # noqa: E402  (frozen)

OUT = REPO / "reports" / "x2_a2"
GATE_FIRST, GATE_LAST = 0.25, 0.75            # frozen freeze_v4 thresholds (read-only restatement for the report)


def _comp(tr: list) -> list:
    return sorted((it.request for it in tr if it.request.workload_class == "competitor"),
                  key=lambda r: (r.arrival_time_s, r.request_id))


def _victims(tr: list) -> list:
    return sorted((r.request_id, f"{r.arrival_time_s:.9f}", r.prompt_text, r.input_token_count, r.max_output_tokens)
                   for r in (it.request for it in tr) if r.workload_class != "competitor")


def _victim_schedule(tr: list) -> list:
    """Victim schedule without prompt text (the frozen per-arm salted nonce makes arm prompts differ by design)."""
    return [v[:2] + v[3:] for v in _victims(tr)]


def gate_ok(cov: dict | None) -> bool:
    return cov is None or (cov["first"] <= GATE_FIRST and cov["last"] >= GATE_LAST)


def one_per_stratum(times: list[float], runtime: float) -> bool:
    n = len(times)
    return [min(n - 1, int(t // (runtime / n))) for t in sorted(times)] == list(range(n))


def check_file(orig: Path, a2: Path, count) -> dict:  # noqa: ANN001
    from quotashift.budget import budget_report, summarize_trace
    from quotashift.local import budget_view, paired_traces
    from quotashift.scenario import load_scenario as frozen_load
    from quotashift.x2.arrivals_a2 import ScenarioConfigA2, load_scenario_any

    so, sa = frozen_load(orig), load_scenario_any(a2)
    assert isinstance(sa, ScenarioConfigA2) and not isinstance(so, ScenarioConfigA2)
    T = float(sa.runtime_seconds)
    seeds = list(range(sa.seed, sa.seed + sa.comparison.repetitions))
    rows, arr = [], {"orig": {"attack": [], "control": []}, "a2": {"attack": [], "control": []}}
    for s in seeds:
        ao, co, _ = paired_traces(so, s, count)
        aa, ca, _ = paired_traces(sa, s, count)
        aa2, ca2, _ = paired_traces(load_scenario_any(a2), s, count)
        row: dict = {"seed": s}
        for arm, o, a, again in (("attack", ao, aa, aa2), ("control", co, ca, ca2)):
            ro, ra = _comp(o), _comp(a)
            arr["orig"][arm].append([r.arrival_time_s for r in ro])
            arr["a2"][arm].append([r.arrival_time_s for r in ra])
            cov_o, cov_a = freeze_v4._coverage(o, T), freeze_v4._coverage(a, T)
            row[arm] = {
                "n": len(ra), "cov_orig": cov_o, "cov_a2": cov_a,
                "gate_orig": gate_ok(cov_o), "gate_a2": gate_ok(cov_a),
                "one_per_stratum": one_per_stratum([r.arrival_time_s for r in ra], T),
                "count_equal": len(ro) == len(ra),
                "tokens_equal": sum(r.input_token_count + r.max_output_tokens for r in ro)
                == sum(r.input_token_count + r.max_output_tokens for r in ra),
                "ids_prompts_shapes_equal": sorted((r.request_id, r.prompt_text, r.input_token_count, r.max_output_tokens)
                                                   for r in ro)
                == sorted((r.request_id, r.prompt_text, r.input_token_count, r.max_output_tokens) for r in ra),
                "victims_equal_orig": _victims(o) == _victims(a),
                "deterministic": freeze_v5.schedule_sha(a) == freeze_v5.schedule_sha(again),
            }
        row["victims_paired"] = _victim_schedule(aa) == _victim_schedule(ca)
        row["victims_paired_orig"] = _victim_schedule(ao) == _victim_schedule(co)
        b = budget_report(summarize_trace(budget_view(sa, aa, s)), summarize_trace(ca), sa.comparison)
        row["budget_matched"] = bool(b["matched"])
        row["budget_rel_delta"] = {k: v["rel_delta"] for k, v in b["dimensions"].items()}
        if sa.comparison.primary_control == "independent_replicate":
            row["aa_independent"] = (freeze_v5.schedule_sha(aa, competitor_arrivals_only=True)
                                     != freeze_v5.schedule_sha(ca, competitor_arrivals_only=True))
        rows.append(row)
    return {"file": str(a2.relative_to(REPO)), "scenario_id": sa.scenario_id, "runtime_s": T,
            "control": sa.comparison.primary_control, "seeds": [seeds[0], seeds[-1]], "rows": rows, "_arrivals": arr}


def gap_stats(arrs: list[list[float]], T: float, hold: float) -> dict:
    gaps = [b - a for x in arrs for a, b in zip(x, x[1:], strict=False)]
    firsts = [x[0] / T for x in arrs if x]
    lasts = [x[-1] / T for x in arrs if x]
    overlap = []                     # fraction of requests arriving while an earlier one is still within its hold time
    busy, peak = [], []
    for x in arrs:
        overlap += [any(0 <= t - u < hold for u in x[:i]) for i, t in enumerate(x)][1:]
        grid = np.linspace(0, T, 2401)[:-1]
        conc = np.array([sum(1 for u in x if u <= g < u + hold) for g in grid])
        busy.append(float((conc > 0).mean()))
        peak.append(int(conc.max()))
    q = np.quantile(gaps, [0.1, 0.5, 0.9]).tolist() if gaps else [None] * 3
    return {"n_arrays": len(arrs), "gap_mean_s": st.mean(gaps) if gaps else None,
            "gap_sd_s": st.pstdev(gaps) if gaps else None,
            "gap_cv": (st.pstdev(gaps) / st.mean(gaps)) if gaps else None,
            "gap_min_s": min(gaps) if gaps else None, "gap_p10_s": q[0], "gap_median_s": q[1], "gap_p90_s": q[2],
            "gap_max_s": max(gaps) if gaps else None,
            "first_mean": st.mean(firsts), "first_max": max(firsts), "last_mean": st.mean(lasts), "last_min": min(lasts),
            "isolated_hold_s": hold, "overlap_fraction": st.mean(overlap) if overlap else 0.0,
            "busy_fraction_mean": st.mean(busy), "peak_concurrency_max": max(peak),
            "peak_concurrency_mean": st.mean(peak)}


def p_gate_iid(n: int) -> float:
    """P(min <= 0.25 and max >= 0.75) for n iid Uniform(0,1)."""
    return 1 - 2 * 0.75 ** n + 0.5 ** n


def p_gate_strat(n: int) -> float:
    if n >= 4:
        return 1.0
    w = 1.0 / n                                   # first in [0, w), last in [1 - w, 1)
    pf = min(1.0, GATE_FIRST / w)
    pl = min(1.0, (1 - GATE_LAST) / w)
    return pf * pl if n > 1 else 0.0


def cross_platform() -> list[dict]:
    out = []
    per_d, per_s = sum(build_x2.SHAPES["D"]), sum(build_x2.SHAPES["S"])
    for r in range(5, 140, 5):
        nd, ns = build_x2.count("D", r), build_x2.count("S", r)
        ntmf = max(1, round(nd * per_d / per_s))
        ns_all = {"X2a/c/d attack (D)": nd, "X2a/c/d control (S, token-matched)": ntmf, "X2b both arms (S)": ns}
        out.append({"rate": r, "counts": ns_all, "min_n": min(ns_all.values()),
                    "a2_guarantees_gate": min(ns_all.values()) >= 4,
                    "p_pass_orig_per_arm": {k: round(p_gate_iid(n), 4) for k, n in ns_all.items()},
                    "p_pass_a2_per_arm": {k: round(p_gate_strat(n), 4) for k, n in ns_all.items()}})
    return out


def frozen_freeze(plat: str, root: Path, count, identity: dict, *, a2: bool) -> dict:  # noqa: ANN001
    try:
        if a2:
            import freeze_x2_a2_traces as fa

            _, tr = fa.freeze(plat, count, identity, root=root)
        else:
            _, tr = fx.freeze(plat, "main", count, identity, root=root)
        return {"passed": True, "scenarios": len(tr["scenarios"])}
    except SystemExit as e:
        return {"passed": False, "refusal": str(e)}


def build(plat: str) -> dict:
    from quotashift.workload.tokenize import WhitespaceTokenizer
    from quotashift.x2.arrivals_a2 import ARRIVAL_LAW, PROTOCOL_ID, STREAM_TAG

    p = build_x2_a2.check(plat)
    if p:
        raise SystemExit("A2 files do not match the generator: " + "; ".join(p))
    tok = WhitespaceTokenizer()
    q = json.loads((build_x2_a2.X2 / plat / "QUALIFICATION.json").read_text())["phase1"]
    hold = {"D": float(q["hold_d_mean"]), "S": float(q["hold_s_mean"])}
    files = fx.phase_files(plat, "main", build_x2_a2.A2)
    cells, dist = [], {}
    for f in files:
        orig = build_x2_a2.X2 / f.relative_to(build_x2_a2.A2)
        c = check_file(orig, f, tok)
        arr = c.pop("_arrivals")
        cells.append(c)
        if "__r2" not in f.stem:
            shp = {"attack": "D" if "decode" in f.stem else "S", "control": "S"}
            dist[c["scenario_id"]] = {arm: {law: gap_stats(arr[law][arm], c["runtime_s"], hold[shp[arm]])
                                            for law in ("orig", "a2")} for arm in ("attack", "control")}
    original_freeze = frozen_freeze(plat, build_x2_a2.X2, tok, tok.identity, a2=False)
    a2_freeze = frozen_freeze(plat, build_x2_a2.A2, tok, tok.identity, a2=True)

    def tally(key: str, arm: str | None = None) -> tuple[int, int]:
        vals = [(r[arm][key] if arm else r[key]) for c in cells for r in c["rows"]
                if (arm is None or key in r[arm]) and (arm is not None or key in r)]
        return sum(bool(v) for v in vals), len(vals)

    summary = {k: {arm: tally(k, arm) for arm in ("attack", "control")}
               for k in ("gate_orig", "gate_a2", "one_per_stratum", "count_equal", "tokens_equal",
                         "ids_prompts_shapes_equal", "victims_equal_orig", "deterministic")}
    summary |= {k: tally(k) for k in ("victims_paired", "victims_paired_orig", "budget_matched", "aa_independent")}
    return {"created_utc": datetime.now(UTC).isoformat(), "platform": plat, "protocol": PROTOCOL_ID,
            "arrival_law": ARRIVAL_LAW, "stream_tag": STREAM_TAG, "tokenizer": tok.identity,
            "note": "offline, zero cost; arrivals do not depend on the tokenizer; no measurement",
            "a2_files_digest": build_x2.digest({str(f.relative_to(build_x2_a2.A2)): f.read_text() for f in files}),
            "rates": json.loads((build_x2_a2.X2 / plat / "RATES.json").read_text())["low"],
            "isolated_hold_s": hold, "summary": summary,
            "frozen_offline_freeze": {"original_x2": original_freeze, "a2": a2_freeze},
            "cells": cells, "distribution": dist, "cross_platform": cross_platform(),
            "runtime_s": build_v5.RUNTIME}


def fmt_cov(c: dict | None) -> str:
    return "-" if c is None else f"{c['first']:.3f}/{c['last']:.3f}"


def markdown(r: dict) -> str:
    L = [f"# X2 Amendment A2: offline validation, {r['platform']} (DRAFT)", "",
         f"Generated {r['created_utc']} by `scripts/x2_a2_validate.py`. Offline, zero cost; no measurement. "
         f"Low rate {r['rates']} tok/s (frozen selection). A2 files digest `{r['a2_files_digest'][:12]}`.", "",
         "## Summary (passing / checked)", "", "| Check | Attack arm | Control arm |", "|---|---|---|"]
    for k, v in r["summary"].items():
        if isinstance(v, dict):
            L.append(f"| {k} | {v['attack'][0]}/{v['attack'][1]} | {v['control'][0]}/{v['control'][1]} |")
    for k in ("victims_paired", "victims_paired_orig", "budget_matched", "aa_independent"):
        a, b = r["summary"][k]
        L.append(f"| {k} (per seed) | {a}/{b} | |")
    fo, fa = r["frozen_offline_freeze"]["original_x2"], r["frozen_offline_freeze"]["a2"]
    L += ["", "## Frozen offline freeze (every frozen gate)", "",
          f"- Original X2 main files: **{'pass' if fo['passed'] else 'REFUSED'}**"
          + (f": `{fo.get('refusal')}`" if not fo["passed"] else ""),
          f"- A2 main files: **{'pass' if fa['passed'] else 'REFUSED'}**"
          + (f" ({fa['scenarios']} scenarios)" if fa["passed"] else f": `{fa.get('refusal')}`"), "",
          "## Coverage matrix (first/last competitor arrival as a fraction of T; gate: first <= 0.25, last >= 0.75)",
          ""]
    for c in r["cells"]:
        fails_o = [f"{arm[0]}{row['seed']}" for row in c["rows"] for arm in ("attack", "control") if not row[arm]["gate_orig"]]
        fails_a = [f"{arm[0]}{row['seed']}" for row in c["rows"] for arm in ("attack", "control") if not row[arm]["gate_a2"]]
        n = c["rows"][0]
        L += [f"### {c['scenario_id']} (seeds {c['seeds'][0]}–{c['seeds'][1]}; N attack {n['attack']['n']}, "
              f"N control {n['control']['n']})", "",
              f"Original fails: {len(fails_o)} ({', '.join(fails_o) or 'none'}). A2 fails: {len(fails_a)} "
              f"({', '.join(fails_a) or 'none'}).", "",
              "| Seed | Attack original | Attack A2 | Control original | Control A2 |", "|---|---|---|---|---|"]
        for row in c["rows"]:
            cells = []
            for arm in ("attack", "control"):
                for law in ("orig", "a2"):
                    cov = row[arm][f"cov_{law}"]
                    ok = row[arm][f"gate_{law}"]
                    cells.append(f"{fmt_cov(cov)}{'' if ok else ' **FAIL**'}")
            L.append(f"| {row['seed']} | " + " | ".join(cells) + " |")
        L.append("")
    L += ["## Arrival distribution: original (iid uniform) vs A2 (stratified), intended seeds", "",
          "Gaps are between consecutive competitor arrivals. Overlap = fraction of competitor requests arriving within "
          "one isolated hold time of an earlier competitor request (Phase 1 hold, D or S). Busy = fraction of the "
          "window with >= 1 competitor request inside its isolated hold time. Peak = maximum concurrent competitor "
          "requests on the same basis. These are schedule properties, not measurements.", "",
          "| Cell / arm | Law | Gap mean s | Gap CV | Gap min s | Gap p10 s | Gap max s | First mean | Last mean | "
          "Overlap | Busy | Peak max |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for sid, d in r["distribution"].items():
        for arm in ("attack", "control"):
            for law in ("orig", "a2"):
                g = d[arm][law]
                L.append(f"| {sid.replace('x2_' + r['platform'] + '_', '')} / {arm} | {law} | {g['gap_mean_s']:.1f} | "
                         f"{g['gap_cv']:.2f} | {g['gap_min_s']:.2f} | {g['gap_p10_s']:.1f} | {g['gap_max_s']:.1f} | "
                         f"{g['first_mean']:.3f} | {g['last_mean']:.3f} | {g['overlap_fraction']:.3f} | "
                         f"{g['busy_fraction_mean']:.3f} | {g['peak_concurrency_max']} |")
    L += ["", "## Prospective applicability by low rate (any platform; counts from the frozen generator)", "",
          "Gate pass probability per seed-arm: original = 1 - 2(0.75)^N + 0.5^N; A2 = 1 for N >= 4.", "",
          "| Low rate tok/s | N attack D | N control S (tmf) | N X2b S | A2 guarantees gate | P pass original (D attack) | "
          "P pass A2 (D attack) |", "|---|---|---|---|---|---|---|"]
    for x in r["cross_platform"]:
        c = x["counts"]
        ks = list(c)
        L.append(f"| {x['rate']} | {c[ks[0]]} | {c[ks[1]]} | {c[ks[2]]} | {'yes' if x['a2_guarantees_gate'] else '**no**'} | "
                 f"{x['p_pass_orig_per_arm'][ks[0]]:.3f} | {x['p_pass_a2_per_arm'][ks[0]]:.3f} |")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", choices=tuple(build_x2.PLATFORMS), required=True)
    ap.add_argument("--out-dir", default=str(OUT))
    a = ap.parse_args()
    r = build(a.platform)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"A2_VALIDATION_{a.platform}.json").write_text(json.dumps(r, indent=1) + "\n")
    (out / f"A2_VALIDATION_{a.platform}.md").write_text(markdown(r))
    s = r["summary"]
    print(json.dumps({k: v for k, v in s.items()}, indent=None))
    print("frozen offline freeze:", {k: v["passed"] for k, v in r["frozen_offline_freeze"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
