"""X2 token-counter identity check for a frozen trace file (read-only; non-frozen operator guard; X2-A3 readiness).

    uv run python scripts/x2_counter_check.py --platform g0m1 --phase calA     # experiments/x2/g0m1/FROZEN_TRACES_CALA.json
    uv run python scripts/x2_counter_check.py --platform g0m1 --phase main     # experiments/x2_a2/g0m1/FROZEN_TRACES_MAIN.json

Why: on G1 the in-VPC runner dispatch forces Mistral freezes and stages through scripts/x2_a3.py. G0 runs locally, so
the operator could call the frozen freeze driver directly; for Mistral that uses the frozen 16-worker /tokenize fan-out,
whose concurrency artifact (a trailing EOS) could make calibration converge one token SHORT in generation if the
artifact were consistent rather than oscillating. The frozen-trace manifest records the counter identity, so this
check runs AFTER a live freeze and BEFORE `pin_x2.py --pin-phase` / `pin_x2_a2.py --pin-phase` (runbook step).

Rule: an A3 model (Mistral) needs identity amendment X2-A3, counting sequential, workers 1; any other model needs the
frozen counter identity (no amendment key), unchanged. Exit 0 ok, 1 mismatch, 3 file missing. Changes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))
FILES = {"calA": ("x2", "FROZEN_TRACES_CALA.json"), "main": ("x2_a2", "FROZEN_TRACES_MAIN.json")}


def problems(identity: dict, model: str) -> list[str]:
    from quotashift.workload.tokenize_a3 import A3_MODELS, AMENDMENT

    p: list[str] = []
    if identity.get("model") != model:
        p.append(f"tokenizer identity model {identity.get('model')!r} != platform model {model!r}")
    if identity.get("kind") != "vllm /tokenize":
        p.append(f"tokenizer kind {identity.get('kind')!r} is not the live vLLM /tokenize counter")
    if model in A3_MODELS:
        want = {"amendment": AMENDMENT, "counting": "sequential", "workers": 1}
        got = {k: identity.get(k) for k in want}
        if got != want:
            p.append(f"{model} must be frozen with the X2-A3 sequential counter (scripts/x2_a3.py); identity has {got}")
    elif "amendment" in identity:
        p.append(f"{model} must use the frozen counter, but the identity carries amendment {identity['amendment']!r}")
    return p


def main(argv: list[str] | None = None) -> int:
    import build_x2  # frozen

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", choices=tuple(build_x2.PLATFORMS), required=True)
    ap.add_argument("--phase", choices=tuple(FILES), required=True)
    ap.add_argument("--file", help="override the trace file path (tests)")
    a = ap.parse_args(argv)
    root, name = FILES[a.phase]
    f = Path(a.file) if a.file else REPO / "experiments" / root / a.platform / name
    if not f.exists():
        print(f"MISSING: {f}", file=sys.stderr)
        return 3
    ident = json.loads(f.read_text()).get("tokenizer") or {}
    p = problems(ident, build_x2.PLATFORMS[a.platform]["model"])
    print(f"{a.platform}/{a.phase}: counter identity OK ({ident.get('amendment') or 'frozen counter'})" if not p
          else "COUNTER MISMATCH (do not pin):\n  " + "\n  ".join(p))
    return 0 if not p else 1


if __name__ == "__main__":
    raise SystemExit(main())
