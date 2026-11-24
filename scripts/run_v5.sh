#!/usr/bin/env bash
# Protocol v5 stage driver wrapper (docs/PROTOCOL_V5.md §10). All logic, gates and refusals live in
# scripts/v5_stage.py; --live refuses unless the stage is owner-approved, the protocol is frozen and P1 passed.
#   scripts/run_v5.sh smoke|A|B --mock --out-root <dir> [--shorten 10]
#   scripts/run_v5.sh smoke|A|B --live [--rerun <block> --reason "<text>"]
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run python scripts/v5_stage.py "$@"
