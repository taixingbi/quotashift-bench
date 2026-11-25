# X2 campaign runbook: readiness → qualification → calibration A → main

**Status:** prepared 2026-11-25, after X2 Freeze Commit 1 (`4704eb3`; manifest `b5033468…`).
- **Nothing here is authorized by this document.** Every live step names the owner token it needs.
- **Frozen methodology:** `docs/PROTOCOL_X2_DRAFT.md` rev 2 and `docs/X2_INSTRUMENTATION_SPEC.md`.
- **Stop rules:**
  - every frozen driver stops on its own gates;
  - one rerun per failed block, with a documented reason;
  - qualification and trace freezes are never repeated;
  - any pin or checksum mismatch stops the stage.

## 0. Before every live step (local)

```sh
uv run python scripts/pin_x2.py --check          # X2 Freeze 1 + v5 dependencies + X1 manifests (Freeze 1, A1)
uv run python scripts/pin_v5.py --check
git status --porcelain                           # must be empty: live drivers refuse a dirty tree
```

## Phase B — network and host readiness (after the owner confirms Ethernet)

```sh
uv run python scripts/x2_network_readiness.py --host gpu-node-2 --label after-ethernet
```

- **Required (B-X2-1, unchanged):** `network_ready: true`, i.e. the runner interface is wired **and** the host interface is not wireless.
- **Reported:** RTT median, p95, sd and loss against the pre-Ethernet baseline (`reports/x2/readiness/2026-11-25T154606_baseline-wifi-pre-ethernet.json`: ICMP median 12.9 ms, p95 108.6 ms, sd 33.2 ms; HTTP `/health` median 25.5 ms, sd 4.7 ms).
- **Never used as gates:** no RTT threshold is pre-registered. Q0 and Q1 decide.
- **B-X2-2 (owner, host admin),** recommended before qualification: stop the k3s agent; hold unattended-upgrades and the apt timers; consider logging out the desktop session. The readiness record shows their state; X2 never changes host configuration itself.

## Phase C — per platform. G0: g0m0, then g0m1, local. G1: g1m0, then g1m1, in-VPC.

### G0 (local runner, gpu-node-2)

| Step | Command (from the repo root) | Token |
|---|---|---|
| Q | `QUOTASHIFT_TARGET=x2-g0-qwen QUOTASHIFT_X2_SSH_HOST=gpu-node-2 QUOTASHIFT_APPROVED=x2_qual_g0m0 uv run python scripts/x2_qualify.py --platform g0m0 --live` (interactive "yes") | `x2_qual_g0m0` |
| commit | commit `experiments/x2/g0m0/QUALIFICATION.json` as produced. A **fail** makes g0m0 not admissible: stop the platform | — |
| calA files | `uv run python scripts/build_x2.py calA --platform g0m0 --hold-s <QUALIFICATION.json phase1.hold_s_mean>`; commit | — |
| calA freeze | `QUOTASHIFT_TARGET=x2-g0-qwen uv run python scripts/freeze_x2_traces.py --platform g0m0 --phase calA --live`; commit; `QUOTASHIFT_APPROVED=x2_freeze_calA_g0m0 uv run python scripts/pin_x2.py --pin-phase g0m0 calA`; commit | `x2_freeze_calA_g0m0` |
| calA | `QUOTASHIFT_TARGET=x2-g0-qwen QUOTASHIFT_X2_SSH_HOST=gpu-node-2 QUOTASHIFT_APPROVED=x2_cal_g0m0 uv run python scripts/x2_stage.py --platform g0m0 --phase calA --live` | `x2_cal_g0m0` |
| rates | `uv run python scripts/x2_select_rates.py --platform g0m0` (control arms only). An **infeasible** low point ends the platform | — |
| main files + freeze | `build_x2.py main --rates experiments/x2/g0m0/RATES.json`; `freeze_x2_traces.py --phase main --live`; `pin_x2.py --pin-phase g0m0 main`; commit each | `x2_freeze_main_g0m0` |
| main | as for calA, with `--phase main` | `x2_main_g0m0` |

**g0m1 needs a server restart to Mistral first.** It is part of the `x2_qual_g0m1` approval, uses `scripts/x1_g0_server.sh` (the same vLLM template), and is never done implicitly.

### G1 (in-VPC runner; needs deploy, image and IAM approvals first; see §B)

Each in-VPC step is: commit inputs → upload → run, then afterwards `aws_ops.sh collect`. The outputs arrive under
`results/aws/x2_outputs/`; copy the non-raw records into `experiments/x2/<p>/` and commit them.

```sh
QUOTASHIFT_APPROVED=x2-inputs scripts/aws_ops.sh x2-inputs research g1m0          # prints QUOTASHIFT_X2_INPUTS_SHA256
QUOTASHIFT_APPROVED=run-stage QUOTASHIFT_STAGE_APPROVAL=<token> QUOTASHIFT_X2_INPUTS_SHA256=<sha> \
  scripts/aws_ops.sh run-stage research [--rerun <block> --reason "<text>"]
```

| Token | What runs in the runner (frozen driver) |
|---|---|
| `x2_qual_<p>` | `x2_runner_entry.py qualify`: the runner's main process runs the frozen `x2_qualify.py` under `script` (TTY) and answers the frozen "yes"; log `/app/results/x2_qual_<p>.log` + CloudWatch. (ECS Exec was tried on 2026-11-25 and is unusable: keystrokes are not forwarded and sessions kill their processes on exit.) |
| `x2_freeze_calA_<p>` / `x2_freeze_main_<p>` | `freeze_x2_traces.py --live` (the platform's own tokenizer). The pin is then made locally with the same token |
| `x2_cal_<p>` / `x2_main_<p>` | `x2_stage.py --live --out-root /app/results/reports/x2` (boundary snapshots over HTTP to the G1 daemon) |

**Built into the path:**
- the runner verifies the inputs tarball SHA-256, extracts only `experiments/x2/<p>/` and `reports/x2/<p>/`, and runs only the frozen X2 drivers;
- `stop-gpu` always stops runner tasks first.

## B. Approvals and owner actions outside this runbook

| Item | Status |
|---|---|
| Ethernet for the runner and gpu-node-2 (B-X2-1) | owner, expected 2026-11-27 |
| Host hygiene (B-X2-2) | owner |
| G1: owner tfvars (budget email), state storage, deploy (`plan` → review → `deploy` with the X2 overlay), runner image build and push, operator IAM addition `infra/iam/x2-operator-additions.json` (ecs:ExecuteCommand on the runner container only), Session Manager plugin on the operator machine | owner approvals: `deploy`, `build_image`, `push_image`, IAM change |
