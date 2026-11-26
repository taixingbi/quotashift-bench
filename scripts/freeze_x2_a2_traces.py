"""X2 Amendment A2 (DRAFT) main trace freeze: the frozen X2 freeze, unchanged, on the A2 scenario root.

    uv run python scripts/freeze_x2_a2_traces.py --platform g1m0 --offline --out-dir /tmp/a2   # validation only
    python scripts/freeze_x2_a2_traces.py --platform g1m0 --live     # in-VPC, owner token x2a2_freeze_main_<p>

docs/PROTOCOL_X2_AMENDMENT_A2.md. Calls scripts/freeze_x2_traces.freeze(plat, "main", ..., root=experiments/x2_a2),
which runs every frozen gate unchanged (freeze_v4: exact tokenization, context fit, matched budget, competitor arrival
coverage first <= 0.25 / last >= 0.75; freeze_x2: schedule independent of tokenizer calibration, independent A/A).
The only substitution is the scenario loader, for the duration of the freeze (quotashift.x2.arrivals_a2.a2_loader), so A2 files get the A2
arrival law; non-A2 files would still load through the frozen loader. Ordering is the frozen main ordering with the
generator check pointed at the A2 generator. Outputs carry an `amendment` provenance block; nothing under
experiments/x2/ is written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_x2  # noqa: E402  (frozen)
import build_x2_a2  # noqa: E402
import freeze_x2_traces as fx  # noqa: E402  (frozen)

A2 = build_x2_a2.A2
REPORTS = REPO / "reports" / "x2"
PHASE = "main"


def ordering_problems(plat: str, *, root: Path = A2, reports_root: Path = REPORTS,
                      results_root: Path = REPO / "results", src: Path = build_x2_a2.X2) -> list[str]:
    """Frozen main ordering (calA completed, rates feasible, no main log or results, qualification passed) with the
    generator equality checked against the A2 generator instead of the frozen one."""
    p = [x for x in fx.ordering_problems(plat, PHASE, root=root, reports_root=reports_root, results_root=results_root)
         if not x.startswith("main files do not match the generator")]
    p += build_x2_a2.check(plat, src=src, root=root)
    return p


def provenance(plat: str, root: Path = A2) -> dict:
    from quotashift.x2 import arrivals_a2 as a2

    files = {str(f.relative_to(root)): f.read_text() for f in fx.phase_files(plat, PHASE, root)}
    return {"protocol": a2.PROTOCOL_ID, "arrival_law": a2.ARRIVAL_LAW, "stream_tag": a2.STREAM_TAG,
            "generator": "scripts/build_x2_a2.py", "law_module": "src/quotashift/x2/arrivals_a2.py",
            "law_module_sha256": hashlib.sha256(Path(a2.__file__).read_bytes()).hexdigest(),
            "a2_files_digest": build_x2.digest(files),
            "original_x2_main_digest": build_x2.digest(build_x2.with_reruns(
                build_x2.build_main(plat, build_x2_a2.rates_of(plat))))}


def freeze(plat: str, count, identity: dict, *, root: Path = A2) -> tuple[dict, dict]:  # noqa: ANN001
    from quotashift.x2.arrivals_a2 import a2_loader

    with a2_loader():
        sched, traces = fx.freeze(plat, PHASE, count, identity, root=root)
    prov = provenance(plat, root)
    return sched | {"amendment": prov}, traces | {"amendment": prov}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", choices=tuple(build_x2.PLATFORMS), required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--live", action="store_true")
    g.add_argument("--offline", action="store_true", help="whitespace stand-in; validation only, never canonical")
    ap.add_argument("--out-dir")
    a = ap.parse_args()
    probs = ordering_problems(a.platform)
    if probs:
        print("REFUSED:\n  " + "\n  ".join(probs), file=sys.stderr)
        return 3
    out = Path(a.out_dir) if a.out_dir else A2 / a.platform
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
        if out.resolve() == (A2 / a.platform).resolve():
            print("refusing to write canonical trace files with the offline stand-in", file=sys.stderr)
            return 3
        from quotashift.workload.tokenize import WhitespaceTokenizer

        count = WhitespaceTokenizer()
        identity = count.identity
    for name in (fx.SCHED_FILE[PHASE], fx.TRACE_FILE[PHASE]):
        if (out / name).exists():
            print(f"refusing to overwrite {out / name} (freezes are written once)", file=sys.stderr)
            return 3
    sched, traces = freeze(a.platform, count, identity)
    out.mkdir(parents=True, exist_ok=True)
    (out / fx.SCHED_FILE[PHASE]).write_text(json.dumps(sched, indent=1, sort_keys=True) + "\n")
    (out / fx.TRACE_FILE[PHASE]).write_text(json.dumps(traces, indent=1) + "\n")
    print(f"wrote A2 {fx.SCHED_FILE[PHASE]} and {fx.TRACE_FILE[PHASE]} ({len(traces['scenarios'])} scenarios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
