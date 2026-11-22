"""Freeze every protocol-v4 workload: calibrate prompts on the tokenizer, verify, hash, write FROZEN_TRACES.json.

    uv run python scripts/freeze_v4.py --live      # live Qwen2.5 tokenizer via /tokenize (read-only, no generation)
    uv run python scripts/freeze_v4.py --offline --out <tmp.json>   # whitespace stand-in (tests only)

For every v4 YAML and every seed it will run: builds the exact attack/control traces that will be sent (nonce + tokenizer
calibration), fails if any request does not tokenize to its planned length or does not fit the context, checks the
matched-budget gate and the competitor arrival span, and records trace hashes and accounting. `quotashift experiment`
refuses (exit 3, nothing sent) if a trace differs from this manifest.
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
V4 = REPO / "experiments" / "v4"


def _coverage(items: list, runtime: float) -> dict | None:
    arr = sorted(it.request.arrival_time_s for it in items if it.request.workload_class == "competitor")
    return {"first": arr[0] / runtime, "last": arr[-1] / runtime} if arr else None


def freeze(files: list[Path], count, identity: dict) -> dict:  # noqa: ANN001
    from quotashift.budget import budget_report, summarize_trace
    from quotashift.local import budget_view, paired_traces
    from quotashift.scenario import load_scenario
    from quotashift.workload.generator import trace_hash
    from quotashift.workload.tokenize import verify_trace

    out: dict = {"created_utc": datetime.datetime.now(datetime.UTC).isoformat(), "tokenizer": identity,
                 "git_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                                           text=True).stdout.strip(),
                 "scenarios": {}}
    for f in files:
        sc = load_scenario(f)
        reps = sc.comparison.repetitions
        ent: dict = {"file": str(f.relative_to(REPO)), "seeds": list(range(sc.seed, sc.seed + reps))}
        for s in ent["seeds"]:
            atk, ctl, label = paired_traces(sc, s, count)
            rec: dict = {"control_label": label}
            for arm, tr in (("attack", atk), ("control", ctl)):
                v = verify_trace(budget_view(sc, tr, s) if arm == "attack" else tr, count,
                                 max_model_len=sc.model_max_len, exact=True, label=f"{sc.scenario_id} {arm} {s}")
                comp = [it.request for it in tr if it.request.workload_class == "competitor"]
                rec[arm] = {"trace_sha256": trace_hash(tr), "requests": len(tr), "competitor_requests": len(comp),
                            "competitor_authorized_tokens": sum(r.input_token_count + r.max_output_tokens for r in comp),
                            "authorized_tokens": sum(r.request.input_token_count + r.request.max_output_tokens for r in tr),
                            "tokenized_input": sum(c["tokenized_input"] for c in v["by_class"].values()),
                            "max_context_tokens": v["max_context_tokens"],
                            "competitor_arrival_coverage": _coverage(tr, sc.runtime_seconds)}
                cov = rec[arm]["competitor_arrival_coverage"]
                if cov is not None and (cov["first"] > 0.25 or cov["last"] < 0.75):
                    raise SystemExit(f"arrival coverage gate would fail: {sc.scenario_id} {arm} seed {s}: {cov}")
            b = budget_report(summarize_trace(budget_view(sc, atk, s)), summarize_trace(ctl), sc.comparison)
            if not b["matched"]:
                raise SystemExit(f"budget gate failed: {sc.scenario_id} seed {s}: {b['violations']}")
            rec["budget"] = {k: v["rel_delta"] for k, v in b["dimensions"].items()} | {"matched": b["matched"]}
            ent[str(s)] = rec
        out["scenarios"][sc.scenario_id] = ent
        print(f"frozen {sc.scenario_id:40s} seeds {ent['seeds'][0]}..{ent['seeds'][-1]}", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--live", action="store_true")
    g.add_argument("--offline", action="store_true")
    ap.add_argument("--out", default=str(V4 / "FROZEN_TRACES.json"))
    ap.add_argument("--files", nargs="*", default=None)
    a = ap.parse_args()
    files = [Path(x).resolve() for x in a.files] if a.files else sorted(V4.rglob("*.yaml"))
    if a.live:
        from quotashift.targets import active_target, current_server_identity
        from quotashift.workload.tokenize import VllmTokenizer

        t = active_target()
        count = VllmTokenizer(t.backend_url, t.model)
        identity = {**count.identity, **current_server_identity(t)}
    else:
        if Path(a.out).resolve() == (V4 / "FROZEN_TRACES.json").resolve():
            print("refusing to write the canonical manifest with the offline stand-in", file=sys.stderr)
            return 3
        from quotashift.workload.tokenize import WhitespaceTokenizer

        count = WhitespaceTokenizer()
        identity = count.identity
    man = freeze(files, count, identity)
    Path(a.out).write_text(json.dumps(man, indent=1) + "\n")
    print(f"wrote {a.out}: {len(man['scenarios'])} scenarios; tokenizer calls: {getattr(count, 'calls', 'n/a')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
