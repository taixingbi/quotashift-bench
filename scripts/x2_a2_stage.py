"""X2 Amendment A2 (DRAFT) main stage: the frozen X2 stage driver, unchanged, on the A2 scenario root.

    uv run python scripts/x2_a2_stage.py --platform g1m0 --mock --out-root /tmp/x2a2 --shorten 10
    QUOTASHIFT_APPROVED=x2a2_main_<p> python scripts/x2_a2_stage.py --platform <p> --live    # owner approval only

docs/PROTOCOL_X2_AMENDMENT_A2.md. Calls x2_stage.run_stage(plat, "main", root=experiments/x2_a2) and, live,
x2_stage.live_problems(root=experiments/x2_a2): the frozen block runner, boundary snapshots, block order, single-rerun
rule, server-identity and budget stops, frozen-trace verification and phase-pin checks all apply unchanged. Blocks run
`quotashift experiment` on A2 YAMLs, which the CLI loads with the A2 arrival law. A2 additions only:
  * live approval token x2a2_main_<p> (translated to the frozen driver's x2_main_<p> check for this process only);
  * the A2 manifest (pin_x2_a2 --check) and the A2 generator check must pass;
  * the stage log is opened with "amendment": "X2-A2" before the frozen driver runs.
The prerequisite calibration-A stage log is the platform's real X2 one (reports/x2/<p>/calA).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_x2  # noqa: E402  (frozen)
import build_x2_a2  # noqa: E402
import pin_x2_a2  # noqa: E402
import v5_stage as vs  # noqa: E402  (frozen)
import x2_stage  # noqa: E402  (frozen)

A2 = build_x2_a2.A2
PHASE = "main"
TOKEN = "x2a2_main_{plat}"


def open_log(reports_root: Path, plat: str, mode: str, root: Path = A2) -> None:
    """Create the stage log with the amendment marker if the frozen driver has not created one yet."""
    rep = x2_stage.stage_reports(reports_root, plat, PHASE)
    if vs.read_log(rep) is not None:
        return
    files = x2_stage.block_files(plat, PHASE, root)
    if not files:
        return
    vs.write_log(rep, {"stage": f"{plat}/{PHASE}", "protocol": "X2", "amendment": "X2-A2", "mode": mode,
                       "status": "new", "blocks": {}, "server_start": None,
                       "stage_estimate_min": sum(vs.estimate_min(f) for f in files), "order": [f.stem for f in files]})


def run(plat: str, *, mode: str, reports_root: Path, results_root: Path, root: Path = A2, **kw) -> int:  # noqa: ANN003
    open_log(reports_root, plat, mode, root)
    return x2_stage.run_stage(plat, PHASE, mode=mode, reports_root=reports_root, results_root=results_root, root=root,
                              **kw)


def live_problems(plat: str, *, interactive_ok: bool, reports_root: Path) -> list[str]:
    p: list[str] = []
    if os.environ.get(vs.APPROVAL_ENV) != TOKEN.format(plat=plat):
        return [f"{vs.APPROVAL_ENV} must be {TOKEN.format(plat=plat)} (owner approval for the A2 main stage)"]
    p += [f"A2: {x}" for x in pin_x2_a2.check()]
    p += [f"A2: {x}" for x in build_x2_a2.check(plat)]
    os.environ[vs.APPROVAL_ENV] = x2_stage.TOKEN[PHASE].format(plat=plat)       # frozen driver's own token check
    try:
        p += x2_stage.live_problems(plat, PHASE, interactive_ok=interactive_ok, root=A2, reports_root=reports_root)
    finally:
        os.environ[vs.APPROVAL_ENV] = TOKEN.format(plat=plat)
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", choices=tuple(build_x2.PLATFORMS), required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--mock", action="store_true")
    g.add_argument("--live", action="store_true")
    ap.add_argument("--out-root", default=str(REPO / "reports" / "x2"))
    ap.add_argument("--results-root", default=str(REPO / "results"))
    ap.add_argument("--shorten", type=int)
    ap.add_argument("--rerun")
    ap.add_argument("--reason")
    a = ap.parse_args()
    out = Path(a.out_root).resolve()
    if a.mock:
        if out == REPO or REPO in out.parents:
            print("REFUSED: mock output must live outside the repository", file=sys.stderr)
            return 3
        return run(a.platform, mode="mock", reports_root=out, results_root=out / "_results",
                   work=out / "_work" / a.platform / PHASE, shorten=a.shorten, rerun=a.rerun, reason=a.reason,
                   guard_s=0.0)
    ok = os.environ.get("QUOTASHIFT_IN_VPC_RUNNER") == "1" or (
        sys.stdin.isatty() and input(f"Type 'yes' to run X2-A2 {a.platform}/main live: ").strip() == "yes")
    probs = live_problems(a.platform, interactive_ok=ok, reports_root=out)
    if probs:
        print("REFUSED:\n  " + "\n  ".join(probs), file=sys.stderr)
        return 3
    from quotashift.targets import active_target
    target = active_target()
    if target.model != build_x2.PLATFORMS[a.platform]["model"] or not target.name.startswith("x2-"):
        print(f"REFUSED: active target {target.name} ({target.model}) is not the X2 target of {a.platform}",
              file=sys.stderr)
        return 3
    import httpx

    from quotashift.instrumentation.prom import parse_prometheus_text, resolve

    def start() -> float | None:
        try:
            return resolve(parse_prometheus_text(httpx.get(target.backend_url.rstrip("/") + "/metrics",
                                                           timeout=5).text)).values.get("process_start_time_seconds")
        except httpx.HTTPError:
            return None
    return run(a.platform, mode="live", reports_root=out, results_root=Path(a.results_root), rerun=a.rerun,
               reason=a.reason, server_start_fn=start, target=target)


if __name__ == "__main__":
    raise SystemExit(main())
