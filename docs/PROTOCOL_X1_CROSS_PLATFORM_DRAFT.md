# Protocol X1: independent cross-model and cross-GPU validation (DRAFT rev 3, not frozen, not run)

**Status:** draft rev 3 for owner review, 2026-11-24.
- **Supersedes:** rev 2 (commit `32f8994`).
- **Incorporates the owner's decision of 2026-11-24:**
  - G1 runs on **AWS EC2 g6.xlarge**, in us-east-1, with 4 vCPU, 16 GiB system RAM and 1 × NVIDIA L4. This **replaces** the earlier preference for g6.2xlarge.
  - **No 8-vCPU quota increase** will be requested.
  - Kept: the full 2 × 2 design, fp16, the existing model revisions, **n = 24 for X-a and X-d**, and the **primary 1.25× threshold**.
- **Not yet done:** no hardware provisioned, no model downloaded, no restart, nothing frozen. Every host, GPU or AWS step follows §10, and each stage needs its own approval.
- **Unchanged by X1:** the v4/v5 results and every frozen v5 artifact.

Companion documents:
- `docs/X1_P0_REPORT.md` (P0 research, with an addendum for this decision);
- `docs/X1_M1_COMPATIBILITY_AUDIT.md`;
- `reports/x1/P0_POWER.md`.

## 1. Purpose (unchanged)

Test whether the four v5 claims transfer to a second model and a second GPU:
- **K1:** decode-heavy amplification at a binding FCFS cap;
- **K2:** the amplification disappears when the cap stops binding;
- **K3:** the harm is gateway queueing, not engine contention;
- **K4:** the FCFS replay predicts victim queueing.

X1 is attack-side only: no defense and no scheduler variation.

## 2. Platforms: full 2 × 2, run in separately approved stages

| | **G0: RTX 3090 24 GB** (owned LAN host gpu-node-2) | **G1: NVIDIA L4 24 GB** (AWS EC2 **g6.xlarge**, us-east-1) |
|---|---|---|
| **M0: Qwen/Qwen2.5-7B-Instruct** @ `a09a35458c702b33eeacc393d103063234e8bc28` | **P0-anchor** | **P-G** (cross-GPU) |
| **M1: mistralai/Mistral-7B-Instruct-v0.3** @ `c170c708c41dac9275d15a8fff4eca08d52bab71` (Apache-2.0) | **P-M** (cross-model) | **P-MG** (cross-both) |

- **Same host within each GPU column.** Both models on G0 run one after the other on gpu-node-2, from one environment. Both models on G1 run on **one** g6.xlarge instance. Each model contrast is therefore within-host.
- **The GPU contrast includes the host.** G1 vs G0 changes the GPU together with CPU, RAM, driver, OS and network path (§2.2).
- **gpu-node-1 stays untouched**, as the v5 server.

### 2.1 Serving stack (identical on all four platforms)
- vLLM **0.17.1**.
  - G0: a conda environment reproducing gpu-node-1 (torch 2.10.0, transformers 4.57.6, mistral_common 1.10.0, Python 3.11).
  - G1: `vllm/vllm-openai:v0.17.1@sha256:0dc46f74eb0e630675d83101dc66c6441c4475cceedcf9235ee42b87c3affd23` on the AL2023 ECS GPU AMI `ami-0b8f7c7154f9e8f8b`, re-resolved and pinned at X1-E.
  - At P1, the SHA-256 values of `engine/arg_utils.py`, `config/vllm.py` and `entrypoints/cli/serve.py` must equal the v5 pins (846fe5ad…, 40507472…, 64b4427d…).
- **One launch template**, with no shell wrapper:

  ```
  VLLM_SERVER_DEV_MODE=1 CUDA_VISIBLE_DEVICES=0 vllm serve <model> --revision <sha> --dtype float16 \
    --max-model-len 4096 --gpu-memory-utilization 0.80 --enable-prefix-caching --enable-prompt-tokens-details \
    --max-num-seqs 256 --max-num-batched-tokens 2048 [M1 only: --tokenizer-mode mistral --config-format mistral --load-format mistral]
  ```

- **dtype: fp16** on all platforms, as in v5 (owner decision). Both models are stored in bf16 and cast.
- **GPU telemetry.** `nvidia_gpu_exporter` v2.0.0 on G0; the stack's DCGM exporter on G1. Energy is compared within a GPU column only.

### 2.2 Host resources as cross-platform confounders (new in rev 3)

| | G0 (gpu-node-2) | G1 (g6.xlarge) |
|---|---|---|
| CPU | AMD Ryzen 7 7800X3D, 16 threads | **4 vCPU** (sustained clock 3.4 GHz per EC2) |
| System RAM | 30 GiB | **16 GiB** |
| GPU memory | 24 GiB (23.56 GiB visible to torch) | 22,888 MiB per EC2 (torch-visible value recorded at P1) |
| Local storage | NVMe (host) | EBS gp3 root plus 250 GB instance NVMe |

**Why these can confound.** The vLLM API server, request tokenization, detokenization and streaming run on the CPU,
in one Python process per server (plus the EngineCore busy loop). With 4 vCPU:
- CPU contention could add latency to user-facing TTFT that is not GPU or gateway queueing;
- it could lengthen slot hold times through streaming overhead, which changes slot demand;
- it could distort the occupancy-reconstruction and timestamp-alignment gates through scraper lag.

With 16 GiB of RAM, loading 13.5 GiB of fp16 weights leaves little page cache. Model loads are slower and more
variable. Memory pressure during runs (logging, Python heap) could cause swapping or OOM kills.

**Treatment (preregistered):**
1. **Preflight** (§9.1) measures CPU, RAM, load success, KV capacity and tokenization throughput on **every** platform, with the same thresholds. A platform that fails a fail-severity preflight check is **not admissible** and is reported as such. It is never silently replaced.
2. **During every arm**, at 1 s resolution, the harness records:
   - host CPU utilisation, total and per core;
   - CPU time of the API server and EngineCore processes;
   - `MemAvailable`, swap-in, and the kernel OOM-kill counter.
   
   These are added as **flag-severity** gates (`host_cpu_headroom`, `host_ram_headroom`; §9.2). Flags never invalidate a block, but they are reported per cell.
3. **Interpretation rule.** If X1-H1, H2 or H4 differs between G1 and G0 **and** the G1 cell carries a host-resource flag, the GPU contrast for that claim is reported as **"GPU+host, host-limited"**, not as a GPU effect.
4. **Host-only diagnostic (descriptive, optional).** If any G1 platform is flagged, the same 2-seed preflight mini-block can be repeated on G0 with the API server pinned to 4 cores (`taskset`) and capped RAM (cgroup). This would be a separately approved, descriptive check of whether a 4-vCPU host alone reproduces the flagged difference.

## 3. Load normalisation: per-platform slot-demand calibration (unchanged)

ρ_ctl = Σ(t_terminal − t_sent) / (8 × 120 s), measured on the short-short control arm at C = 8.

1. **Calibration A.** Seeds 7000–7002, over a 6-rate grid.
2. **Choose two operating points:**
   - **low:** ρ_ctl closest to 0.43;
   - **high:** ρ_ctl closest to 0.72.
   
   Ties go to the lower rate. If no rate reaches ρ_ctl ≥ 0.40 with control SLO ≥ 0.95, the low point is reported as infeasible and is not substituted.
3. Rates are frozen in Freeze Commit 3.

**Effect of host speed.** Calibrating on slot demand absorbs GPU speed. It also absorbs any CPU-induced lengthening of
holds. The §2.2 flags record how much of that came from the host.

## 4. Cells per platform

| Block | Comparison | Load | Cap | **n** | Seeds | Role |
|---|---|---|---|---|---|---|
| X-a | D vs S | low | C = 8 | **24** | 8000–8023 | K1 (primary), K3 |
| X-b | D vs S | low | C = 32 | 10 | 8000–8009 | K2 |
| X-c | D vs S | low | direct | 10 | 8000–8009 | K2, K3 |
| X-d | A/A-ind | low | C = 8 | **24** | 8000–8023 | noise floor for X-a |
| X-e | D vs S | high | C = 8 | 10 | 8000–8009 | K1 at depth; K4 |
| X-f | A/A-ind | high | C = 8 | 10 | 8000–8009 | noise floor for X-e |

- **Seeds.** Never used before. Schedules are regenerated per platform from its frozen rates. Isolation salts include the platform ID.
- **Wall time.** Arms are fixed 120 s windows, so wall time does not depend on GPU speed, at about 5 min per seed pair. That gives 2 × 120 + 4 × 50 = **440 min ≈ 7.3 h** of main stage per platform, and **≈ 29.3 h** for all four.
- **P vs S** is excluded from core X1. It is kept as optional extension **X1-E1**, which needs its own preregistration.

## 5. Hypotheses and verdict (primary threshold 1.25×, owner decision)

ℓ is the per-seed log ratio of victim mean user-facing TTFT, attack/control. The frozen v5 functions are imported
unchanged.

| ID | Claim | Test | Family |
|---|---|---|---|
| **X1-H1** | On platform p, D vs S at (low, C = 8) **exceeds 1.25** | one-sided t of mean ℓ > log 1.25 (`p_superiority`), n = 24 | **F-X1:** Holm over 4 platforms (fixed family; p = 1 if not evaluable) |
| **X1-H2** | (low, C = 32) is equivalent within [0.8, 1.25] | TOST (`p_tost`) | **F-X2:** Holm over 8 = 4 × H2 + 4 × H3 |
| **X1-H3** | The direct path is equivalent within [0.8, 1.25] | TOST | F-X2 |
| **X1-H4** | At (low, C = 8), attack backend TTFT is within [0.9, 1.1] × control **and** the engine queue is negligible (v5 §5.2) | TOST on the log backend ratio, plus `engine_queue_negligible` | own criterion |
| **X1-H5** | FCFS replay predictions (§6) hold at (low, C = 8), (low, C = 32) and (high, C = 8) | v5 `score_fcfs` cell and seed rules; tolerances from calibration LOSO | own criterion; validated envelope by design |
| X1-D1 | (high, C = 8) magnitude, victim SLO collapse, threshold-above-noise using X-f | descriptive | none |
| X1-D2 | Host-resource flags per cell (§2.2) | descriptive | none |

**Verdict** (fixed in advance):
- **GENERALISES** iff X1-H1 is supported on ≥ 3 of 4 platforms, **and** X1-H2 is equivalent on ≥ 3 of 4, **and** X1-H4 holds on ≥ 3 of 4.
- **ANCHOR-ONLY** iff X1-H1 is supported only on P0-anchor.
- **PARTIAL** otherwise.

A platform whose H1 is "not supported" is never reported as evidence that the mechanism is absent. The §2.2
interpretation rule applies to any G1 result that carries a host flag.

## 6. Where X1-H5's service-time distributions come from (unchanged from rev 2)

1. **Calibration B.** Per platform, after the rates are frozen, run D vs S and A/A-ind at (low, C = 8) and (high, C = 8) with calibration seeds **7003–7007**: 4 blocks × 5 seeds.
2. **Hold pools.** These runs alone supply the hold-time pools per (platform, operating point, arm, class). Nothing from v4/v5 or the main stage enters.
3. **Predictions.** The known main-stage schedules are replayed through a global FCFS queue with C slots, using the frozen v5 predictor code path.
4. **Tolerances.** Leave-one-seed-out over the calibration seeds.
5. **Freeze.** Everything is pinned in Freeze Commit 3, before any main-stage run.
6. **No error direction is preregistered.**

## 7. Power (option (a) chosen; `reports/x1/P0_POWER.md`)

**Choice.** n = 24 for X-a and X-d, with the primary 1.25 null kept.

| Scenario | P(GENERALISES) |
|---|---|
| v5 effect (1.565×) and v5 variability | **0.94** (normal noise) – **0.985** (empirical noise) |
| Platform heterogeneity τ = 0.2 | 0.57–0.59 |
| 1.5× variability | 0.40–0.51 |
| True effect 1.8× | ≥ 0.76 in every scenario |
| True effect 1.4× | ≤ 0.25 |
| Effect on only 2 of 4 platforms (false generalisation) | 0.000 |

H2 and H4 never limit the verdict. The protocol states this power profile explicitly. A shortfall is reported as
low power, not as absence of the mechanism.

## 8. Gates, governance and artifacts

- **Gates.** Every v5 gate, unchanged:
  - cap_configured;
  - occupancy reconstruction;
  - timestamp alignment;
  - server identity before and after every block;
  - budget;
  - private-endpoint fail-closed checks;
  - the verified pre-block prefix-cache reset.
  
  Plus the two new flag-severity host gates (§9.2).
- **P1 per platform and model.** A read-only X1 collector that matches the server by Python executable and follows Hugging Face content-store symlinks. Evidence needed:
  - version and source SHA-256 values equal the pins;
  - argv carries the template;
  - snapshot hash-verified;
  - `cache_config_info` shows block size 16 and memory utilisation 0.80.
- **Analysis.** `scripts/x1_analysis.py` imports the v5 pure rules unmodified, and is frozen in Freeze Commit 1.
- **Export.** The existing sanitizer, with AWS identifiers (account, instance, VPC IDs and private addresses) added to the regex gate before any AWS stage.
- **Isolation.** Owned and private only. AWS endpoints stay inside the isolated VPC under `*.quotashift.internal`.

## 9. Preflight and smoke (per platform and model, before calibration)

### 9.1 Preflight checks (new in rev 3; thresholds preregistered, identical on all platforms)

| Check | How measured | Fail (platform not admissible) | Flag |
|---|---|---|---|
| **Model-loading success** | Server reaches "Application startup complete" with no ERROR/Traceback lines; `/v1/models` lists the pinned revision; the snapshot weight hash equals the pinned SHA-256; load wall-time recorded | any ERROR or Traceback, hash mismatch, or no startup within 30 min | load time > 2× G0's for the same model |
| **GPU KV capacity** | `vllm:cache_config_info` (num_gpu_blocks × block_size) and the "GPU KV cache size" log line | KV tokens < **20,480**, i.e. 2 × (C = 32 × largest X1 request of 320 tokens) | KV tokens < 4 × the observed direct-path peak demand in calibration A |
| **Available system RAM** | `/proc/meminfo` `MemAvailable` after model load, and its minimum during the smoke mini-block; `/proc/vmstat` `oom_kill` and `pswpin` deltas | any OOM kill; MemAvailable < 1.0 GiB at any sample | MemAvailable < 2.0 GiB; any swap-in |
| **CPU utilisation** | 1 s samples during the smoke mini-block at the **high** operating point: host total from `/proc/stat`; API-server and EngineCore CPU time from `/proc/<pid>/stat` | host total ≥ 95% for ≥ 10% of samples | API server ≥ 85% of one core for ≥ 5% of samples; host total ≥ 80% for ≥ 10% |
| **Tokenization throughput** | `POST /tokenize` burst (CPU only): the frozen prompt templates of every shape, 1,000 requests at concurrency 8; p50/p99 latency and requests/s | throughput < 10 × the platform's peak offered request rate at the high operating point, or p99 > 50 ms | p99 > 20 ms |
| **Idle TTFT floor** (descriptive) | One request per shape on an idle server, repeated 20 times | — | recorded for the cross-platform comparison |

- **Where results go.** Preflight results go in the platform's P1 record (`HOST_VERIFICATION_<platform>.json`) and are frozen with it.
- **Tokenization throughput is a request to the server.** It is CPU-only and generates no tokens, but it still runs only within an approved stage.

### 9.2 Per-arm host telemetry and flag gates (during calibration and the main stage)
- **`host_cpu_headroom` (flag):** API server ≥ 85% of one core for ≥ 5% of the arm's samples, **or** host total ≥ 80% for ≥ 10%.
- **`host_ram_headroom` (flag):** MemAvailable < 2.0 GiB at any sample, or any swap-in during the arm.
- **Fail severity:** an OOM kill during an arm → that block fails (v5 rerun rule applies).
- **Sampler cost.** The sampler runs on the GPU host at 1 Hz, standard library only, and its own CPU use is recorded.

### 9.3 Smoke (unchanged)
1. Verified prefix-cache reset probe.
2. `/tokenize` parity with offline tokenizer counts (mistral_common 1.10.0 for M1).
3. One fixed-length request per shape: output tokens equal `max_tokens`, finite logprobs, non-empty text.
4. Every v5 gate on a 2-seed mini block. Smokes are never analysed.

## 10. Staged GPU and AWS approval plan (g6.xlarge; $60 cap)

Each stage needs explicit owner approval, recorded in `docs/DECISIONS.md`, and ends with a report and a stop.
**No quota increase is requested:** g6.xlarge uses all 4 vCPU of the current on-demand G/VT quota, so exactly one G1
instance can run at a time. The plan needs only one.

| Stage | What happens | Touches | Cost (g6.xlarge) | Approval token |
|---|---|---|---|---|
| X0 | P0 research | read-only | $0 | done |
| **X1-A** | Owner review of rev 3; ADR-X1 | docs | $0 | review |
| **X1-B** | Replace the root access keys with a least-privilege IAM identity | AWS IAM | $0 | owner action |
| **X1-C** | gpu-node-2: create the 0.17.1 environment; download both models (≈ 30 GB) | local host | $0 | `x1_local_env` |
| **X1-D** | gpu-node-2: restart with the template; P1 and §9.1 preflight per model | local host | $0 | `x1_local_restart` |
| **X1-E** | AWS prep in the repo: Terraform variables (`g6.xlarge`, AMI pinned, image digest 0.17.1, host-telemetry sampler, exporter, private target profile, AWS identifiers in the export gate); `terraform fmt`/`validate`/`test`/read-only `plan` | repo + read-only AWS | $0 | review |
| ~~X1-F~~ | ~~quota increase~~: **not requested** (owner decision) | — | — | — |
| **X1-G** | Freeze Commit 1 (protocol, analysis code, schedule generator, preflight thresholds) | repo | $0 | `x1_freeze1` |
| **X1-H** | P2 tokenizer trace freeze for both models on gpu-node-2 → Freeze Commit 2 | local host | $0 | `x1_p2` |
| **X1-I** | G0 calibration A + B, both models | local GPU | $0 | `x1_g0_calibration` |
| **X1-J** | `aws_ops.sh deploy` (reviewed plan only) | AWS | NAT ≈ $1.08/day plus storage while applied | `deploy` |
| **X1-K** | `start-gpu`: P1 and §9.1 preflight for both models, smoke, calibration A + B → `stop-gpu` | AWS GPU | ≈ 6.5 GPU-h ≈ **$5.23** | `start-gpu` (x1_g1_calibration) |
| **X1-L** | Freeze Commit 3 (rates, pools, predictions, tolerances for all 4 platforms) | repo | $0 | `x1_freeze3` |
| **X1-M** | G0 main: P0-anchor, then P-M (≈ 7.3 h each) | local GPU | $0 | `x1_g0_main` (per platform) |
| **X1-N** | G1 main: P-G, then P-MG (14.7 h of blocks; ≈ 19.1 GPU-h with the 1.3 budget rule) → `stop-gpu` | AWS GPU | ≈ **$15.35** | `start-gpu` (x1_g1_main) |
| **X1-O** | `destroy`; export, verify, frozen analysis; report | AWS + repo | $0 after destroy | `destroy` |

**AWS total**, from `scripts/estimate_cost.py` with `configs/infrastructure/prices.us-east-1.2026-11-24.yaml`, NAT
mode, the stack existing 120 h, 60 GB through the NAT, 120 GB EBS and 2 GB of logs:

| Scenario | GPU-hours | Total |
|---|---|---|
| Plan | ≈ 29 | **$36.24** |
| Pessimistic | 45 | **$50.91** |

**Cost controls (kept):**
- `spending_limit_usd = 60`;
- `max_run_minutes` per stage (X1-K: 480; X1-N: 1,320);
- GPU ASG desired capacity 0 between stages;
- `stop-gpu` is ungated;
- `destroy` at X1-O;
- budget alerts only.

Cost Explorer is not used; its calls are billed and gated.

## 11. Open items for the owner
1. Approve stage X1-A (this revision) and the IAM change X1-B before any AWS stage.
2. Confirm the preflight thresholds in §9.1. They are proposals and are frozen at X1-G.
3. Confirm the host-only diagnostic (§2.2, item 4) stays optional and needs separate approval.
