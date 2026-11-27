# X2 G0 runbook: g0m0 (Qwen) and g0m1 (Mistral) on gpu-node-2

**Status:** prepared offline on 2026-11-27 (readiness package `docs/X2_G0_READINESS.md`). **It authorizes
nothing.** Every live step names the owner approval it needs.

- **Host:** gpu-node-2, an RTX 3090 on a local runner. It is expected to be available around **2026-11-29**.
- **Frozen methodology:**
  - X2 rev 2 (`docs/PROTOCOL_X2_DRAFT.md`) and `docs/X2_INSTRUMENTATION_SPEC.md`;
  - Amendment A2 for main (`docs/PROTOCOL_X2_AMENDMENT_A2.md`);
  - Amendment A3 for **Mistral token counting only** (`docs/PROTOCOL_X2_AMENDMENT_A3.md`).
- **Order:** g0m0, then g0m1, matching G1 (g1m0, then g1m1).

**Stop rules, unchanged:**
- every frozen driver stops on its own gates;
- qualification and trace freezes are run **once** and never repeated;
- a failed qualification makes the platform inadmissible;
- one rerun per failed block, with a documented reason;
- any pin or checksum mismatch stops the step;
- low = 5 tok/s, or an infeasible low point, stops before main (§3 of the readiness report).

**Differences from G1, all procedural; no frozen artifact changes:**

| | g0m0 (Qwen) | g0m1 (Mistral) |
|---|---|---|
| Runner | local operator terminal (live drivers need a TTY and type "yes") | same |
| Snapshot transport | `ssh` (`QUOTASHIFT_X2_SSH_HOST=gpu-node-2`) | same |
| Freeze / stage drivers | frozen drivers **directly** | **always through `scripts/x2_a3.py`** (A3 sequential counter); never call the frozen freeze/stage drivers directly for g0m1 |
| Counter guard before every phase pin | `x2_counter_check.py` must report "frozen counter" | `x2_counter_check.py` must report "X2-A3" |
| Target | `QUOTASHIFT_TARGET=x2-g0-qwen` | `QUOTASHIFT_TARGET=x2-g0-mistral` |

## 0. Before every live step (local, zero cost)

```sh
git status --porcelain                                   # must be empty
for s in pin_v5 pin_x2 pin_x2_a2 pin_x2_a3 pin_x1_amendment; do uv run python scripts/$s.py --check; done
uv run pytest -q tests/unit/test_x2_g0_readiness.py tests/unit/test_x2_a3.py tests/unit/test_x2_pipeline.py
```

## 1. Network and host readiness (after the owner confirms Ethernet; B-X2-1, B-X2-2)

```sh
uv run python scripts/x2_network_readiness.py --host gpu-node-2 --label after-ethernet   # read-only; ssh + ping + /health
git add reports/x2/readiness/ && git commit -m "X2 G0 readiness after Ethernet"         # tracked record; tree clean again
```

- **Required:** `network_ready: true`, meaning both ends are wired. RTT figures are reported, never used as gates.
- **Host hygiene (B-X2-2): owner changes only, recommended before qualification.**
  - Stop the k3s agent.
  - Hold unattended-upgrades and the apt timers.
  - Consider logging out the desktop session.

  The readiness record shows their state. X2 never changes host configuration. Read-only verification, the same
  commands the readiness script runs:

```sh
ssh gpu-node-2 'for u in k3s-agent unattended-upgrades apt-daily.timer apt-daily-upgrade.timer sysstat-collect.timer gdm; do printf "%s=%s/%s\n" $u $(systemctl is-active $u) $(systemctl is-enabled $u); done'
ssh gpu-node-2 'nvidia-smi --query-gpu=name,driver_version,utilization.gpu,memory.used --format=csv,noheader; nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader'
ssh gpu-node-2 'pgrep -af "vllm serv[e]"; awk "/MemAvailable/" /proc/meminfo; cat /proc/loadavg; pgrep -fc "[x][12]_host_s" || true'
ssh gpu-node-2 'ls ~/miniconda3/envs/vllm0171/bin/vllm && ~/miniconda3/envs/vllm0171/bin/python -c "import vllm; print(vllm.__version__)"'
```

- **Expected:**
  - no other GPU compute process;
  - the `vllm0171` env reports **0.17.1**;
  - the model snapshot is cached, because the server starts with `HF_HUB_OFFLINE=1`.
- **Before g0m1:** confirm the Mistral snapshot `c170c708…` is in the HF cache.

## 2. g0m0: Qwen2.5-7B-Instruct @ `a09a3545…`

| # | Step | Command | Owner token |
|---|---|---|---|
| 2.1 | server start (template = G1 flags) | `ssh gpu-node-2 'bash -s' -- start g0m0 < scripts/x1_g0_server.sh` | part of `x2_qual_g0m0` |
| 2.2 | **qualification, once** (owner terminal, types "yes") | `QUOTASHIFT_TARGET=x2-g0-qwen QUOTASHIFT_X2_SSH_HOST=gpu-node-2 QUOTASHIFT_APPROVED=x2_qual_g0m0 uv run python scripts/x2_qualify.py --platform g0m0 --live` | `x2_qual_g0m0` |
| 2.3 | commit | `experiments/x2/g0m0/QUALIFICATION.json` as produced; `sha256sum` of `reports/x2/g0m0/qualification/segments.json` into `reports/x2/g0m0/SHA256SUMS`. A **fail** ends g0m0 | — |
| 2.4 | calA files | `uv run python scripts/build_x2.py calA --platform g0m0 --hold-s <phase1.hold_s_mean>`; commit | — |
| 2.5 | calA freeze | `QUOTASHIFT_TARGET=x2-g0-qwen uv run python scripts/freeze_x2_traces.py --platform g0m0 --phase calA --live` | `x2_freeze_calA_g0m0` |
| 2.6 | **counter guard**, then pin | `uv run python scripts/x2_counter_check.py --platform g0m0 --phase calA` (must say "frozen counter"); commit; `QUOTASHIFT_APPROVED=x2_freeze_calA_g0m0 uv run python scripts/pin_x2.py --pin-phase g0m0 calA`; commit | same |
| 2.7 | calA stage (~85 min) | `QUOTASHIFT_TARGET=x2-g0-qwen QUOTASHIFT_X2_SSH_HOST=gpu-node-2 QUOTASHIFT_APPROVED=x2_cal_g0m0 uv run python scripts/x2_stage.py --platform g0m0 --phase calA --live` | `x2_cal_g0m0` |
| 2.8 | evidence | `SHA256SUMS` of `reports/x2/g0m0/calA/` and `RUNS_SHA256SUMS` of `results/x2_g0m0_calA_*` | — |
| 2.9 | rate selection, once | `uv run python scripts/x2_select_rates.py --platform g0m0`; commit `RATES.json`. **low = 5 or infeasible: STOP** | conditional on the main approval |
| 2.10 | main files | `uv run python scripts/build_x2.py main --platform g0m0 --rates experiments/x2/g0m0/RATES.json`; commit; `uv run python scripts/build_x2_a2.py --platform g0m0` and `--check`; commit; `uv run python scripts/x2_a2_validate.py --platform g0m0` (all checks pass); commit | — |
| 2.11 | A2 main freeze | `QUOTASHIFT_TARGET=x2-g0-qwen uv run python scripts/freeze_x2_a2_traces.py --platform g0m0 --live` | `x2a2_freeze_main_g0m0` |
| 2.12 | **counter guard**, then pin | `uv run python scripts/x2_counter_check.py --platform g0m0 --phase main`; commit; `QUOTASHIFT_APPROVED=x2a2_freeze_main_g0m0 uv run python scripts/pin_x2_a2.py --pin-phase g0m0 main`; commit | same |
| 2.13 | A2 main stage (~5.3 h) | `QUOTASHIFT_TARGET=x2-g0-qwen QUOTASHIFT_X2_SSH_HOST=gpu-node-2 QUOTASHIFT_APPROVED=x2a2_main_g0m0 uv run python scripts/x2_a2_stage.py --platform g0m0 --live` | `x2a2_main_g0m0` |
| 2.14 | evidence + stop | checksums of `reports/x2/g0m0/main/` and `results/x2_g0m0_X2*`; `ssh gpu-node-2 'bash -s' -- stop < scripts/x1_g0_server.sh` | — |

## 3. g0m1: Mistral-7B-Instruct-v0.3 @ `c170c708…` (A3)

| # | Step | Command | Owner token |
|---|---|---|---|
| 3.1 | server restart to Mistral (never implicit) | `ssh gpu-node-2 'bash -s' -- stop < scripts/x1_g0_server.sh` then `... -- start g0m1 < scripts/x1_g0_server.sh` (adds `--tokenizer-mode/--config-format/--load-format mistral`) | part of `x2_qual_g0m1` |
| 3.2 | **qualification, once** | `QUOTASHIFT_TARGET=x2-g0-mistral QUOTASHIFT_X2_SSH_HOST=gpu-node-2 QUOTASHIFT_APPROVED=x2_qual_g0m1 uv run python scripts/x2_qualify.py --platform g0m1 --live` (qualification does not count tokens; unaffected by A3) | `x2_qual_g0m1` |
| 3.3 | commit + calA files | as 2.3–2.4 with `g0m1` | — |
| 3.4 | calA freeze **via A3** | `QUOTASHIFT_TARGET=x2-g0-mistral uv run python scripts/x2_a3.py freeze --platform g0m1 --phase calA --live` | `x2_freeze_calA_g0m1` |
| 3.5 | **counter guard**, then pin | `uv run python scripts/x2_counter_check.py --platform g0m1 --phase calA` (must say "X2-A3"); commit; `QUOTASHIFT_APPROVED=x2_freeze_calA_g0m1 uv run python scripts/pin_x2.py --pin-phase g0m1 calA`; commit | same |
| 3.6 | calA stage **via A3** | `QUOTASHIFT_TARGET=x2-g0-mistral QUOTASHIFT_X2_SSH_HOST=gpu-node-2 QUOTASHIFT_APPROVED=x2_cal_g0m1 uv run python scripts/x2_a3.py stage --platform g0m1 --phase calA --live` | `x2_cal_g0m1` |
| 3.7 | evidence, rates, main files | as 2.8–2.10 with `g0m1` (same low = 5 stop) | — |
| 3.8 | A2 main freeze **via A3** | `QUOTASHIFT_TARGET=x2-g0-mistral uv run python scripts/x2_a3.py freeze --platform g0m1 --phase main --live` | `x2a2_freeze_main_g0m1` |
| 3.9 | **counter guard**, then pin | `uv run python scripts/x2_counter_check.py --platform g0m1 --phase main`; commit; `QUOTASHIFT_APPROVED=x2a2_freeze_main_g0m1 uv run python scripts/pin_x2_a2.py --pin-phase g0m1 main`; commit | same |
| 3.10 | A2 main stage **via A3** | `QUOTASHIFT_TARGET=x2-g0-mistral QUOTASHIFT_X2_SSH_HOST=gpu-node-2 QUOTASHIFT_APPROVED=x2a2_main_g0m1 uv run python scripts/x2_a3.py stage --platform g0m1 --phase main --live` | `x2a2_main_g0m1` |
| 3.11 | evidence + stop | as 2.14 | — |

**Why the guard exists.** If a g0m1 freeze were run directly with the frozen 16-worker counter, the result depends on
the artifact:
- an oscillating artifact gives a refusal, as on g1m1;
- an artifact that appeared on *every* concurrent call could make calibration converge to prompts **one token short**
  in generation, without a refusal.

A stage run without A3 on an A3-frozen trace fails closed (`FrozenTraceMismatch`), so the unguarded risk is the
freeze alone. `x2_counter_check.py` reads the identity that the frozen freeze records and refuses before the pin.

## 4. After both platforms

- The frozen cross-platform analysis (`scripts/x2_analysis.py`) runs only when every admissible platform has every
  cell. That analysis needs its own approval.
- No interim look happens before then.
