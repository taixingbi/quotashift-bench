# X1 owner batch approval (recorded 2026-11-24)

Granted by the project owner in one message (session record), as separate stage approvals executed together:

| Token | Stage | Scope |
|---|---|---|
| `x1_freeze1` | X1-G | Freeze Commit 1 exactly as in docs/X1_FREEZE1_REQUEST.md (13 reviewed hashes + the protocol status-line change) |
| `x1_local_env` | X1-C | gpu-node-2: pinned vLLM 0.17.1 environment; reuse verified weights where possible (model downloads permitted) |
| `x1_local_restart` | X1-D | restart only the gpu-node-2 inference server; preserve the existing environment for rollback; never touch gpu-node-1 |
| `x1_p2` | X1-H | limited to the Calibration A trace freeze |
| `x1_g0_calibration` | X1-I | limited to the Mistral platform (g0m1): calA, rate selection by the frozen rule, Phase 2, calB trace freeze, calB |

Explicit exclusions: no main-stage experiments, no Qwen calibration, no Freeze Commit 3, no AWS resources, no image
build or push, no credential or IAM change; stop on any hard validity failure, server identity mismatch, failed
preflight or unexpected infrastructure condition; single-rerun rule only.

Operator confirmation: the stage driver's interactive "yes" is answered by Claude through a pseudo-terminal under this
recorded written approval ("run continuously through the approved stages without intermediate approval requests").
Every such confirmation is listed in experiments/x1/g0m1/STAGE_RECORDS.json.
