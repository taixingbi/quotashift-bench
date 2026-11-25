# X1 Freeze Commit 1: request for owner approval

**Date:** 2026-11-24. **Status: NOT executed.**
- `experiments/x1/FROZEN_SHA256.json` does not exist.
- `scripts/pin_x1.py --write` refuses without `QUOTASHIFT_APPROVED=x1_freeze1`.

**Basis:**
- Owner review of `9727889`: the freeze candidate is conditionally accepted, and the 7 implementation choices in `docs/X1_FREEZE_CANDIDATE.md` §2 are approved, subject to clarifying the trace-freeze ordering (done: §2 below).
- Unchanged: protocol rev 4, hypotheses, thresholds, seeds, families and gates.

## 1. B1: operator policy update (the only AWS change in this batch)

| Step | Result |
|---|---|
| Live policy vs the policy committed when the role was created (`6700309`) | **identical**: no unexpected differences |
| Live vs reviewed (`9727889`) | exactly **two added Allow statements**, both read-only: `ReadProjectIamAndBuckets` (iam Get/List on `role/quotashift-*` and `instance-profile/quotashift-*`) and `ReadsNeededByTerraformAndAwsOps` (`ec2/autoscaling/ecs/ecr/logs/servicediscovery` Describe/Get/List, `budgets:ViewBudget`, route53 list, `ssm:GetParameter(s)`, `pricing:GetProducts`, `sts:GetCallerIdentity`). No existing statement changed |
| Applied | 2026-11-24 21:15:11, `aws iam put-role-policy` with `infra/iam/x1-operator-policy.json` (= `9727889`), the inline policy only |
| Read-only inspection afterwards | live policy == reviewed file; **trust policy, max session, tags and description unchanged**; inline policies still only `quotashift-x1-operator`; no managed policies; readonly role unchanged |
| Policy simulation of the live roles (`scripts/x1_iam_verify.py`) | guard rails **23 of 23** as expected; Terraform and `aws_ops` needs **54 of 54** allowed |

## 2. Trace-freeze audit

Ordering is implemented in `scripts/freeze_x1_traces.py` and `scripts/pin_x1.py --pin-phase`, and re-checked by
`scripts/x1_stage.py` before every live block. Tests: `tests/unit/test_x1_trace_freeze_order.py` (5 of 5), using the
offline tokenizer in a temporary tree.

| Requirement | Mechanism | Verified by |
|---|---|---|
| calA grid traces frozen **before** any calA run | freezing refused if a calA stage log or calA results exist. The pin records the grid files and their reruns, the schedule and the traces | traces cover exactly the calA files and reruns; a calA run that started before its pin is detected; freezing after a run is refused |
| calB traces frozen **after** rates are selected and **before** any calB run | requires calA `completed` and `RATES.json`. The calB files must equal the generator output at those rates. Freezing is refused if calB has started. The pin includes the `RATES.json` checksum | refused before calA completes or without rates; refused when files were generated at other rates |
| main traces frozen **before** any main experiment | requires calB `completed`, `RATES.json` and `FCFS_PREDICTIONS.json` (Freeze Commit 3 pins all of them together). Freezing is refused once any `x1_<plat>_X…` result exists | refused without predictions; tampering with traces after the pin is detected; refused once main results exist |
| Schedule unchanged by tokenization | `FROZEN_SCHEDULE_<PHASE>` written first; the traces are refused if any calibrated trace changes its schedule (v5 rule, frozen `freeze_v5.schedule_sha`) | `freeze()` path |
| Each phase uses its own frozen file | generator: `frozen_traces: ../FROZEN_TRACES_{CALA,CALB,MAIN}.json` | test |

## 3. X1-H5 parameters (preserved exactly; `tests/unit/test_x1_h5_params.py`, 3 of 3)

| Parameter | Value |
|---|---|
| RNG entropy | **81000** |
| Monte-Carlo draws per prediction | **200** (= frozen v5 `MC`) |
| LOSO draws | **50** (= frozen v5 LOSO) |
| τ_abs | max(**5 ms**, q95 \|LOSO err\|) |
| ρ | q95 relative error over LOSO runs with obs ≥ **5 ms**, needing at least **3** such runs; otherwise **ρ = 0.3491564644530319**, the frozen v5 `rho_rel`, checked against `experiments/v5/FCFS_PREDICTIONS.json` |

The predictions record `rho_source` ∈ {`loso`, `v5_fallback`} and the fallback's source file. The pass, seed and cell
rules are the frozen v5 `score_fcfs`.

## 4. Host-telemetry alignment and X1 identity (`tests/unit/test_x1_identity_alignment.py`, 5 of 5)

- **Clock alignment.**
  - Problem: sampler samples carry GPU-host time; arm windows carry runner time.
  - New Phase 1 measurement: `clock_offset_probe` reads the server's HTTP `Date` header on `GET /health` 20 times. It is read-only, bounds the offset to about 1 s, and works on G0 and G1 without SSH.
  - Rule `clock_offset_check`: pass ≤ 2 s, flag ≤ 5 s, fail above.
  - The analysis shifts every arm window by the recorded offset (`HOST_VERIFICATION.json` → `preflight.phase1.clock_offset_s`).
  - Tested: a 60 s skew mis-assigns samples without the shift and is corrected with it. On the local mock the probe gives |offset| < 1.5 s with bound ≤ 1 s.
- **X1 identity** (`platform_identity`, fail severity; any failure makes the platform's hypotheses not evaluable, p = 1 in Holm). Every cell must have:
  - the platform's model;
  - the pinned revision as reported by the server (`/server_info`, dev mode);
  - vLLM **0.17.1**;
  - an `x1_<plat>_` scenario with `protocol_version` 5;
  - **all 14 v5 harness gates** present.
- **Server identity.** One server start per platform's main stage; a restart blocks that platform.
- **v5 gates.** Unchanged and required in full. X1 adds checks and removes none.

## 5. Infrastructure preparation (nothing applied)

| Item | State |
|---|---|
| S3 remote-state bootstrap | plan prepared (readonly role): **7 to add**, namely bucket, versioning, SSE, public-access block, ownership, lifecycle, TLS/deletion-deny policy. **Not applied** |
| Owner and budget email | moved out of the public `envs/research.tfvars` into the **git-ignored** `infra/terraform/owner.auto.tfvars`, from the committed `owner.auto.tfvars.example`. A plan without `owner` refuses. `aws_ops.sh deploy` **refuses a plan without the budget alarm**. Plans: 62 to add without an email, **63** with one |
| Gateway and runner dependencies | `run-stage` refuses without a runner task definition, without exactly one running vLLM task, or without `QUOTASHIFT_STAGE_APPROVAL=x1_<phase>_<g1m0\|g1m1>`. The token is forwarded to the in-VPC driver; G0 platforms can never run on AWS; `assignPublicIp=DISABLED` |
| GPU shutdown | `stop-gpu` (never gated) now stops running runner tasks **first**, then the gateway and vLLM services, then sets the GPU ASG to 0 (order tested). A mock apply then destroy leaves desired = 0 |
| Plans (readonly role) | Qwen 62, Mistral 62, with budget email 63, bootstrap 7. 0 change, 0 destroy |

## 6. Tests and checksums

| Check | Result |
|---|---|
| pytest | **489 passed, 1 skipped** (opt-in real-GPU test) |
| ruff, mypy | clean |
| Terraform | fmt and validate OK; tests **19 of 19**; state bootstrap **2 of 2** |
| IAM | Access Analyzer 0 findings (3 policies); live-role simulation 23 of 23 and 54 of 54 |
| v5 freeze | `pin_v5.py --check`: all match. v5 archives A and B verify; 4,735-file raw inventory matches |
| X1 candidate | `reports/x1/FREEZE_CANDIDATE_SHA256.json`: 13 files. The 6 imported v5 modules are identical to their v5 pins |

## 7. Freeze 1 manifest (exactly what `--write` will pin)

| File | SHA-256 |
|---|---|
| `docs/PROTOCOL_X1_CROSS_PLATFORM_DRAFT.md` | `8d937ba1f563460e58a26a653441ec51f501fd55077245d11d9bf39f1a253cd1` |
| `scripts/build_x1.py` | `51eaefbeab7ca828e1e390cf0364338434904d6cd88a385072ef145e2f10afe2` |
| `scripts/x1_analysis.py` | `158481f8bf041ba220bb2c706ad5c3ceb0e3d1cc0f5f1c670a90ceef1ca326de` |
| `scripts/x1_predictions.py` | `0643e0905311e328d77c23498b1f29e453689e9f945b7b912336907bfbf215ce` |
| `scripts/x1_stage.py` | `71f2548611843b3154b8af362253c2ad51074e4be47c32b254996f2a4b17a95b` |
| `scripts/x1_host_sampler.py` | `23a1698040e5504dc237afa75b168a1a1c709274601f8c50c67ab48ca8fe8b0f` |
| `scripts/pin_x1.py` | `a8a24adcfbe797665f2af4bfaa42dbfc2d1b67da221facef40124fbf609fb2aa` |
| `scripts/freeze_x1_traces.py` | `721c32bb4fd5815ba1e941ab29734b29c5e065ec63799527ee8c727630dcf4f6` |
| `scripts/x1_iam_verify.py` | `608ba21345b4fa874584bab82f64cfd6e5b753cbb368e3fc5cc5a1a313ff0c7c` |
| `src/quotashift/x1/__init__.py` | `e6ea8349d65c7407d50807d3026a0393985d7d2c7b9874bbaa247b198f687302` |
| `src/quotashift/x1/preflight.py` | `7d2da70ba89a5f2b68e456577d9553df3bdc2c90cf328ed9d0eca95126f32002` |
| `src/quotashift/x1/tokenize_probe.py` | `c4c66026afb64fbe6f88700e79b18a976492ec3f6ff1f3d819dbc684ae52fb05` |
| `src/quotashift/x1/export_gate.py` | `18db641d075af1e491f7b207374b2d4e2174a15163b26d8acf8242bbda5bbf31` |

**Verified, not re-pinned** (must equal `experiments/v5/FROZEN_SHA256.json`):

| File | SHA-256 |
|---|---|
| `v5_analysis.py` | `d894baae…` |
| `v5_fcfs_predictions.py` | `b32e10aa…` |
| `build_v5.py` | `fd36b1e1…` |
| `v5_stage.py` | `532dbfca…` |
| `freeze_v5.py` | `f753abaf…` |
| `freeze_v4.py` | `cdc0d268…` |

## 8. Remaining blockers

| # | Blocker | Owner action |
|---|---|---|
| B2 | Budget email and owner handle | fill the git-ignored `infra/terraform/owner.auto.tfvars` |
| B3 | Remote state | approve applying `infra/state-bootstrap`, or local state with `state-backup` |
| B4 | Runner image | approve `build_image`, then after deploy `push_image` |
| **B5** | **Freeze Commit 1** | **this request** |
| B6 | G0 stages X1-C/D/H/I | separate approvals (local environment, downloads, restart, P1 and Phase 1, calA traces) |
| B7 | First-boot checks on G1 | at X1-K: Cloud Map registration from the AMI, DCGM on the L4, driver vs image |

## 9. Exact approval request

> **Approve X1 Freeze Commit 1 (`x1_freeze1`)**, pinning exactly the 13 files and SHA-256 values in §7 (with the 6
> v5 dependencies verified unchanged), and marking `docs/PROTOCOL_X1_CROSS_PLATFORM_DRAFT.md` rev 4 as FROZEN.

On approval I will, and do nothing else:
1. Re-run `uv run python scripts/pin_x1.py --candidate` and confirm that every hash equals §7. Any difference → stop and report.
2. Run `QUOTASHIFT_APPROVED=x1_freeze1 uv run python scripts/pin_x1.py --write`, which writes `experiments/x1/FROZEN_SHA256.json`.
3. Run `uv run python scripts/pin_x1.py --check` and the full offline tests.
4. Commit "X1 Freeze Commit 1" and push.

Marking the protocol status FROZEN is a one-line header edit made **before** `--write`, so the pinned protocol hash will
be the new one. The request therefore covers that single header-line change to the §7 protocol hash: the content is
unchanged and only the status line moves from "NOT frozen" to "FROZEN". The commit will report the new protocol hash.
