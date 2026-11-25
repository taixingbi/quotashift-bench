"""X2 per-phase trace freeze (docs/PROTOCOL_X2_DRAFT.md rev 2 section 5.3). NOT frozen.

    uv run python scripts/freeze_x2_traces.py --platform g0m0 --phase calA --live      # the platform's own tokenizer
    QUOTASHIFT_APPROVED=x2_freeze_calA_g0m0 uv run python scripts/pin_x2.py --pin-phase g0m0 calA

Ordering (enforced here AND re-checked by scripts/x2_stage.py before every live block):
  calA  frozen after the platform's qualification PASSED and its calA files equal the generator at the recorded hold
        time, and BEFORE any calA run
  main  frozen AFTER calA completed and RATES.json exists, with the main files equal to the generator at those rates,
        and BEFORE any main run
Each phase writes FROZEN_SCHEDULE_<PHASE>.json (tokenizer-independent) first and then FROZEN_TRACES_<PHASE>.json; the
traces are refused unless every calibrated trace keeps its frozen schedule. Reuses the frozen v4/v5 freeze code
unchanged (freeze_v4.freeze, freeze_v5.schedule_sha).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_x2  # noqa: E402

X2 = REPO / "experiments" / "x2"
REPORTS = REPO / "reports" / "x2"
TRACE_FILE = {"calA": "FROZEN_TRACES_CALA.json", "main": "FROZEN_TRACES_MAIN.json"}
SCHED_FILE = {"calA": "FROZEN_SCHEDULE_CALA.json", "main": "FROZEN_SCHEDULE_MAIN.json"}


def phase_files(plat: str, phase: str, root: Path = X2) -> list[Path]:
    d = root / plat / phase
    return sorted(d.glob("x2_*.yaml")) + sorted((d / "reruns").glob("x2_*.yaml"))


def _log(reports_root: Path, plat: str, phase: str) -> dict | None:
    f = reports_root / plat / phase / "STAGE_LOG.json"
    return json.loads(f.read_text()) if f.exists() else None


def qualification(plat: str, root: Path = X2) -> dict | None:
    f = root / plat / "QUALIFICATION.json"
    return json.loads(f.read_text()) if f.exists() else None


def ordering_problems(plat: str, phase: str, *, root: Path = X2, reports_root: Path = REPORTS,
                      results_root: Path = REPO / "results") -> list[str]:
    p: list[str] = []
    if not phase_files(plat, phase, root):
        p.append(f"no generated {phase} files for {plat}")
    if _log(reports_root, plat, phase) is not None:
        p.append(f"{plat}/{phase} already has a stage log: traces must be frozen BEFORE any {phase} run")
    pref = f"x2_{plat}_{'calA' if phase == 'calA' else 'X2'}"
    if results_root.exists() and any(q.name.startswith(pref) for q in results_root.iterdir()):
        p.append(f"{phase} results for {plat} exist: traces must be frozen BEFORE any {phase} run")
    q = qualification(plat, root)
    if not q or q.get("status") != "pass":
        p.append(f"{plat}: qualification (Phase 1 + Q1) has not passed")
    if phase == "calA" and q and q.get("status") == "pass":
        gen = build_x2.with_reruns(build_x2.build_cal_a(plat, float(q["phase1"]["hold_s_mean"])))
        if any(not (root / rel).exists() or (root / rel).read_text() != text for rel, text in gen.items()):
            p.append("calA files do not match the generator at the qualified hold time (regenerate before freezing)")
    if phase == "main":
        lg = _log(reports_root, plat, "calA")
        if not lg or lg.get("status") != "completed":
            p.append(f"{plat}/calA has not completed (status {lg.get('status') if lg else None})")
        rates = root / plat / "RATES.json"
        if not rates.exists():
            p.append("RATES.json missing: the low point must be selected before main traces are frozen")
        else:
            r = json.loads(rates.read_text())
            if not r.get("low_feasible", False):
                p.append("low point infeasible: no main stage (reported, never substituted)")
            else:
                gen = build_x2.with_reruns(build_x2.build_main(plat, r))
                if any(not (root / rel).exists() or (root / rel).read_text() != text for rel, text in gen.items()):
                    p.append("main files do not match the generator at RATES.json (regenerate before freezing)")
    return p


def build_schedule(files: list[Path]) -> dict:
    import freeze_v5

    from quotashift.local import _paired_traces_raw
    from quotashift.scenario import load_scenario

    out: dict = {"hash_fields": "request_id|tenant|class|arrival_time_s(.9f)|input_token_count|max_output_tokens",
                 "scenarios": {}}
    for f in files:
        sc = load_scenario(f)
        ent: dict = {"file": f.name, "seeds": {}}
        for s in range(sc.seed, sc.seed + sc.comparison.repetitions):
            atk, ctl, _ = _paired_traces_raw(sc, s)
            rec = {arm: {"schedule_sha256": freeze_v5.schedule_sha(tr),
                         "competitor_arrivals_sha256": freeze_v5.schedule_sha(tr, competitor_arrivals_only=True)}
                   for arm, tr in (("attack", atk), ("control", ctl))}
            if sc.comparison.primary_control == "independent_replicate" and (
                    rec["attack"]["competitor_arrivals_sha256"] == rec["control"]["competitor_arrivals_sha256"]):
                raise SystemExit(f"independent_aa gate: {sc.scenario_id} seed {s} shares competitor arrivals")
            ent["seeds"][str(s)] = rec
        out["scenarios"][sc.scenario_id] = ent
    return out


def freeze(plat: str, phase: str, count, identity: dict, *, root: Path = X2) -> tuple[dict, dict]:  # noqa: ANN001
    import freeze_v4
    import freeze_v5

    from quotashift.local import paired_traces
    from quotashift.scenario import load_scenario

    files = phase_files(plat, phase, root)
    sched = build_schedule(files)
    for f in files:
        sc = load_scenario(f)
        for s in range(sc.seed, sc.seed + sc.comparison.repetitions):
            atk, ctl, _ = paired_traces(sc, s, count)
            for arm, tr in (("attack", atk), ("control", ctl)):
                if freeze_v5.schedule_sha(tr) != sched["scenarios"][sc.scenario_id]["seeds"][str(s)][arm]["schedule_sha256"]:
                    raise SystemExit(f"schedule changed by tokenizer calibration: {sc.scenario_id} {arm} seed {s}")
    return sched, freeze_v4.freeze(files, count, identity)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", choices=tuple(build_x2.PLATFORMS), required=True)
    ap.add_argument("--phase", choices=tuple(TRACE_FILE), required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--live", action="store_true")
    g.add_argument("--offline", action="store_true", help="whitespace stand-in; tests only, never the canonical files")
    ap.add_argument("--out-dir")
    a = ap.parse_args()
    probs = ordering_problems(a.platform, a.phase)
    if probs:
        print("REFUSED:\n  " + "\n  ".join(probs), file=sys.stderr)
        return 3
    out = Path(a.out_dir) if a.out_dir else X2 / a.platform
    if a.live:
        from quotashift.targets import active_target, current_server_identity
        from quotashift.workload.tokenize import VllmTokenizer

        t = active_target()
        if t.model != build_x2.PLATFORMS[a.platform]["model"]:
            print(f"REFUSED: active target serves {t.model}, platform {a.platform} needs "
                  f"{build_x2.PLATFORMS[a.platform]['model']}", file=sys.stderr)
            return 3
        count = VllmTokenizer(t.backend_url, t.model)
        identity = {**count.identity, **current_server_identity(t)}
    else:
        if out.resolve() == (X2 / a.platform).resolve():
            print("refusing to write canonical trace files with the offline stand-in", file=sys.stderr)
            return 3
        from quotashift.workload.tokenize import WhitespaceTokenizer

        count = WhitespaceTokenizer()
        identity = count.identity
    for name in (SCHED_FILE[a.phase], TRACE_FILE[a.phase]):
        if (out / name).exists():
            print(f"refusing to overwrite {out / name} (freezes are written once)", file=sys.stderr)
            return 3
    sched, traces = freeze(a.platform, a.phase, count, identity)
    out.mkdir(parents=True, exist_ok=True)
    (out / SCHED_FILE[a.phase]).write_text(json.dumps(sched, indent=1, sort_keys=True) + "\n")
    (out / TRACE_FILE[a.phase]).write_text(json.dumps(traces, indent=1) + "\n")
    print(f"wrote {SCHED_FILE[a.phase]} and {TRACE_FILE[a.phase]} ({len(traces['scenarios'])} scenarios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
