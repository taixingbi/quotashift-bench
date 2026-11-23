"""Freeze protocol-v5 workloads in two steps.

    uv run python scripts/freeze_v5.py --schedule          # offline, now: experiments/v5/FROZEN_SCHEDULE.json
    uv run python scripts/freeze_v5.py --schedule --check  # exit 1 if the schedule on disk differs
    uv run python scripts/freeze_v5.py --live              # pre-stage P (owner-approved): FROZEN_TRACES.json on the
                                                           # live Qwen2.5 tokenizer (/tokenize, read-only, no generation)
    uv run python scripts/freeze_v5.py --offline --out <tmp.json>   # whitespace stand-in (tests only)

1. FROZEN_SCHEDULE.json (tokenizer-independent; part of the freeze commit): per scenario x seed x arm, the SHA-256 of
   (request_id, tenant, class, arrival_time_s, input_token_count, max_output_tokens) for every request, the competitor
   arrival-only hash, counts and authorized tokens. It pins arrivals and token plans before the tokenizer is touched and
   is what the frozen FCFS predictions (scripts/v5_fcfs_predictions.py) were computed on.
2. FROZEN_TRACES.json (same format as v4, scripts/freeze_v4.py): exact prompt text after nonce + tokenizer calibration.
   `--live` refuses to write it unless every trace's schedule hash equals FROZEN_SCHEDULE.json, and fails the
   `independent_aa` gate if an A/A-ind pair shares its competitor arrivals.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
V5 = REPO / "experiments" / "v5"
SCHEDULE = V5 / "FROZEN_SCHEDULE.json"
sys.path.insert(0, str(REPO / "scripts"))


def schedule_sha(trace: list, *, competitor_arrivals_only: bool = False) -> str:
    h = hashlib.sha256()
    for it in sorted(trace, key=lambda x: (x.request.arrival_time_s, x.request.request_id)):
        r = it.request
        if competitor_arrivals_only:
            if r.workload_class == "competitor":
                h.update(f"{r.arrival_time_s:.9f}\n".encode())
            continue
        h.update(f"{r.request_id}|{r.tenant_id}|{r.workload_class}|{r.arrival_time_s:.9f}|{r.input_token_count}|"
                 f"{r.max_output_tokens}\n".encode())
    return h.hexdigest()


def build_schedule() -> dict:
    import build_v5

    from quotashift.local import _paired_traces_raw
    from quotashift.scenario import load_scenario

    out: dict = {"protocol": "v5 (draft until the freeze commit)", "hash_fields":
                 "request_id|tenant|class|arrival_time_s(.9f)|input_token_count|max_output_tokens", "scenarios": {}}
    for p in sorted(build_v5.build()):
        sc = load_scenario(p)
        ent: dict = {"file": str(p.relative_to(REPO)), "C": sc.safety.max_global_inflight, "path": build_v5.path_of(p),
                     "control": sc.comparison.primary_control, "seeds": {}}
        for s in range(sc.seed, sc.seed + sc.comparison.repetitions):
            atk, ctl, _ = _paired_traces_raw(sc, s)
            rec = {}
            for arm, tr in (("attack", atk), ("control", ctl)):
                comp = [it.request for it in tr if it.request.workload_class == "competitor"]
                rec[arm] = {"schedule_sha256": schedule_sha(tr),
                            "competitor_arrivals_sha256": schedule_sha(tr, competitor_arrivals_only=True),
                            "victim_requests": len(tr) - len(comp), "competitor_requests": len(comp),
                            "competitor_authorized_tokens": sum(r.input_token_count + r.max_output_tokens for r in comp)}
            if sc.comparison.primary_control == "independent_replicate" and (
                    rec["attack"]["competitor_arrivals_sha256"] == rec["control"]["competitor_arrivals_sha256"]):
                raise SystemExit(f"independent_aa gate: {sc.scenario_id} seed {s} shares competitor arrivals")
            ent["seeds"][str(s)] = rec
        out["scenarios"][sc.scenario_id] = ent
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--schedule", action="store_true")
    g.add_argument("--live", action="store_true")
    g.add_argument("--offline", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.schedule:
        text = json.dumps(build_schedule(), indent=1, sort_keys=True) + "\n"
        if a.check:
            same = SCHEDULE.exists() and SCHEDULE.read_text() == text
            print("schedule reproduces exactly" if same else "schedule DIFFERS from FROZEN_SCHEDULE.json")
            return 0 if same else 1
        if SCHEDULE.exists():
            print(f"refusing to overwrite {SCHEDULE}", file=sys.stderr)
            return 3
        SCHEDULE.write_text(text)
        print(f"wrote {SCHEDULE.relative_to(REPO)}")
        return 0
    import freeze_v4

    from quotashift.local import paired_traces
    from quotashift.scenario import load_scenario

    out = Path(a.out) if a.out else V5 / "FROZEN_TRACES.json"
    if a.live:
        from quotashift.targets import active_target, current_server_identity
        from quotashift.workload.tokenize import VllmTokenizer

        t = active_target()
        count = VllmTokenizer(t.backend_url, t.model)
        identity = {**count.identity, **current_server_identity(t)}
    else:
        if out.resolve() == (V5 / "FROZEN_TRACES.json").resolve():
            print("refusing to write the canonical manifest with the offline stand-in", file=sys.stderr)
            return 3
        from quotashift.workload.tokenize import WhitespaceTokenizer

        count = WhitespaceTokenizer()
        identity = count.identity
    sched = json.loads(SCHEDULE.read_text())["scenarios"]
    files = sorted(V5.rglob("*.yaml"))
    for f in files:  # calibrated traces must keep the frozen schedule (calibration may only change prompt text)
        sc = load_scenario(f)
        for s in range(sc.seed, sc.seed + sc.comparison.repetitions):
            atk, ctl, _ = paired_traces(sc, s, count)
            for arm, tr in (("attack", atk), ("control", ctl)):
                if schedule_sha(tr) != sched[sc.scenario_id]["seeds"][str(s)][arm]["schedule_sha256"]:
                    raise SystemExit(f"schedule mismatch after calibration: {sc.scenario_id} {arm} seed {s}")
    man = freeze_v4.freeze(files, count, identity)
    out.write_text(json.dumps(man, indent=1) + "\n")
    print(f"wrote {out}: {len(man['scenarios'])} scenarios")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
