"""X2 Amendment A3 (DRAFT) driver: the frozen X2 / X2-A2 freeze and stage drivers, unchanged, with the sequential
Mistral token counter (docs/PROTOCOL_X2_AMENDMENT_A3.md).

    uv run python scripts/x2_a3.py freeze --platform g1m1 --phase calA --offline --out-dir /tmp/a3   # validation
    uv run python scripts/x2_a3.py stage  --platform g1m1 --phase calA --mock --out-root /tmp/a3 --shorten 10
    python scripts/x2_a3.py freeze --platform g1m1 --phase calA --live      # in-VPC, after the A3 freeze only
    QUOTASHIFT_APPROVED=x2_calA_g1m1 python scripts/x2_a3.py stage --platform g1m1 --phase calA --live

Phase -> frozen driver: calA freeze = scripts/freeze_x2_traces.py, calA stage = scripts/x2_stage.py, main freeze =
scripts/freeze_x2_a2_traces.py, main stage = scripts/x2_a2_stage.py. Every argument after the A3 options is passed
through; every frozen gate, approval token, ordering rule and pin check of the target driver applies unchanged.
A3 additions only:
  * the platform must serve an A3 model (Mistral: g1m1, g0m1); Qwen platforms are refused, they never use A3;
  * --live requires the A3 manifest (scripts/pin_x2_a3.py --check), which itself re-verifies v5, X2, A2, X1, A1;
  * QUOTASHIFT_TOKEN_COUNTER=X2-A3 is set for this process and inherited by the block subprocesses, so both the trace
    freeze and the runtime pre-send recalibration + exact verify_trace (quotashift.local.run_matched_pairs) count
    sequentially.
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DRIVERS = {("freeze", "calA"): "freeze_x2_traces.py", ("stage", "calA"): "x2_stage.py",
           ("freeze", "main"): "freeze_x2_a2_traces.py", ("stage", "main"): "x2_a2_stage.py"}
USAGE = "usage: x2_a3.py {freeze,stage} --platform P --phase {calA,main} {--live|--offline|--mock} [driver args...]"


def parse(argv: list[str]) -> tuple[str, str, str, list[str]]:
    if not argv or argv[0] not in ("freeze", "stage"):
        raise SystemExit(USAGE)
    kind, rest = argv[0], list(argv[1:])
    try:
        i = rest.index("--phase")
        phase = rest[i + 1]
        del rest[i:i + 2]
        plat = rest[rest.index("--platform") + 1]
    except (ValueError, IndexError):
        raise SystemExit(USAGE) from None
    if phase not in ("calA", "main"):
        raise SystemExit(USAGE)
    if phase == "calA":  # the frozen X2 drivers take --phase; the A2 (main-only) drivers do not
        rest += ["--phase", phase]
    return kind, phase, plat, rest


def problems(plat: str, live: bool) -> list[str]:
    sys.path.insert(0, str(REPO / "scripts"))
    import build_x2  # frozen

    from quotashift.workload.tokenize_a3 import A3_MODELS

    p: list[str] = []
    spec = build_x2.PLATFORMS.get(plat)
    if spec is None:
        return [f"unknown platform {plat}"]
    if spec["model"] not in A3_MODELS:
        p.append(f"{plat} serves {spec['model']}: A3 applies to Mistral platforms only (frozen counting unchanged)")
    if live:
        import pin_x2_a3

        p += [f"A3: {x}" for x in pin_x2_a3.check()]
    return p


def main(argv: list[str] | None = None) -> int:
    kind, phase, plat, rest = parse(list(sys.argv[1:] if argv is None else argv))
    os.environ["QUOTASHIFT_TOKEN_COUNTER"] = "X2-A3"     # inherited by `quotashift experiment` block subprocesses
    from quotashift.workload import tokenize_a3

    tokenize_a3.install()                               # this process (the package may have been imported already)
    probs = problems(plat, "--live" in rest)
    if probs:
        print("REFUSED (A3):\n  " + "\n  ".join(probs), file=sys.stderr)
        return 3
    driver = REPO / "scripts" / DRIVERS[(kind, phase)]
    print(f"X2-A3: {driver.name} {' '.join(rest)} (sequential Mistral token counting)", flush=True)
    sys.argv = [str(driver), *rest]
    try:
        runpy.run_path(str(driver), run_name="__main__")
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else (0 if e.code is None else 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
