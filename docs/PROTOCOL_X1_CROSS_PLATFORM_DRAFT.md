# Protocol X1: independent cross-model and cross-GPU validation (DRAFT rev 2, not frozen, not run)

**Status:** draft rev 2 for owner review, 2026-11-24.
- **Supersedes:** rev 1, the earlier version of this file (commit `bbb174f`).
- **Incorporates:** the owner's X1 planning decisions of 2026-11-24, the P0 read-only research in `docs/X1_P0_REPORT.md`, and the gpu-node-2 audit in `docs/X1_M1_COMPATIBILITY_AUDIT.md`.
- **Not yet done:** no hardware has been provisioned, no model downloaded, and nothing frozen. Every GPU, AWS or host-modifying step follows the staged approval plan in §10, and each stage needs its own approval.
- **Unchanged by X1:** the v4/v5 results and every frozen v5 artifact.

## 1. Purpose (unchanged from rev 1)

Test whether the four v5 claims transfer to a second model and a second GPU:
- **K1:** decode-heavy amplification at a binding FCFS cap;
- **K2:** the amplification disappears when the cap stops binding;
- **K3:** the harm is gateway queueing, not engine contention;
- **K4:** the FCFS replay predicts victim queueing.

X1 tests transfer of the mechanism, not of effect sizes. It is attack-side only: no defense and no scheduler variation.

## 2. Platforms: full 2 × 2 (owner decision 3), run as separately approved stages

| | **G0: RTX 3090 24 GB** (owned LAN host) | **G1: NVIDIA L4 24 GB** (AWS EC2 g6, us-east-1) |
|---|---|---|
| **M0: Qwen/Qwen2.5-7B-Instruct** @ `a09a35458c702b33eeacc393d103063234e8bc28` | **P0-anchor** | **P-G** (cross-GPU) |
| **M1: mistralai/Mistral-7B-Instruct-v0.3** @ `c170c708c41dac9275d15a8fff4eca08d52bab71` (Apache-2.0) | **P-M** (cross-model) | **P-MG** (cross-both) |

- **Same host within each GPU column.** Both models on G0 are served, one after the other, from **one** host, gpu-node-2, with one software environment. Both models on G1 are served from **one** EC2 instance. Each model contrast is therefore within-host.
- **The GPU contrast includes the host.** Comparing G1 with G0 changes the GPU together with the CPU, driver, OS and network path. This bundle is disclosed, not separated.
- **The anchor's relation to v5.** P0-anchor uses the same model, GPU model and vLLM version as v5, on a different host and with new seeds. It is not a re-run of v5.

### Serving stack (identical on all four platforms; normalisation plan from the audit)
- vLLM **0.17.1**.
  - G0: a conda environment reproducing gpu-node-1 exactly, i.e. torch 2.10.0, transformers 4.57.6, mistral_common 1.10.0, Python 3.11.
  - G1: the official image `vllm/vllm-openai:v0.17.1@sha256:0dc46f74eb0e630675d83101dc66c6441c4475cceedcf9235ee42b87c3affd23`.
  - On every platform, at P1, the SHA-256 values of `engine/arg_utils.py`, `config/vllm.py` and `entrypoints/cli/serve.py` must equal the v5 pins (846fe5ad…, 40507472…, 64b4427d…). Otherwise that platform is not admissible.
- **One launch template**, with no shell wrapper, and the batch limits explicit so they are verified from argv:

  ```
  VLLM_SERVER_DEV_MODE=1 CUDA_VISIBLE_DEVICES=0 vllm serve <model> --revision <sha> --dtype float16 \
    --max-model-len 4096 --gpu-memory-utilization 0.80 --enable-prefix-caching --enable-prompt-tokens-details \
    --max-num-seqs 256 --max-num-batched-tokens 2048 [M1 only: --tokenizer-mode mistral --config-format mistral --load-format mistral]
  ```

- **dtype.** fp16 on all four platforms, matching v5. Both models are stored in bf16 and are cast. The smoke check (§9) verifies that outputs are finite and have the full requested length.
- **GPU exporter.** The same exporter must be present on every platform: `nvidia_gpu_exporter` v2.0.0 on G0, and the stack's DCGM exporter on G1.
  - The DCGM exporter's metric semantics differ from `nvidia_gpu_exporter`, so energy is compared within a GPU column only.

## 3. Load normalisation: per-platform slot-demand calibration (kept)

Token rates do not transfer across GPUs or models. Load is therefore set per platform by the control arm's offered
slot demand at C = 8:

ρ_ctl = Σ (t_terminal − t_sent) / (8 × 120 s)

1. **Calibration A (rates).** Calibration seeds **7000–7002**, never analysed. On each platform, run the short-short control arm at C = 8 over a grid of 6 token rates, chosen per platform from an offline throughput probe.
2. **Choose two operating points per platform:**
   - **low:** ρ_ctl closest to **0.43** (v5 L = 200 equivalent);
   - **high:** ρ_ctl closest to **0.72** (v5 L = 400 equivalent).
   
   Ties go to the lower rate. If no rate reaches ρ_ctl ≥ 0.40 with control victim SLO ≥ 0.95, the low point is reported as infeasible and is not substituted.
3. The rates are frozen in **Freeze Commit 3**, before any main-stage run.

## 4. Cells per platform (owner decisions 4 and 5)

| Block | Comparison | Load | Cap | n | Role |
|---|---|---|---|---|---|
| X-a | D vs S | low | C = 8 | **16** | K1 (primary), K3 |
| X-b | D vs S | low | C = 32 | 10 | K2 |
| X-c | D vs S | low | direct | 10 | K2, K3 |
| X-d | A/A-ind | low | C = 8 | **16** | noise floor for X-a |
| X-e | D vs S | high | C = 8 | 10 | K1 at depth; K4 |
| X-f | A/A-ind | high | C = 8 | 10 | noise floor for X-e |

- **Seeds.**
  - The main stage uses **8000–8015**. X-a and X-d use 8000–8015; the other blocks use 8000–8009.
  - These seeds have never been used before. Each platform's schedules are regenerated from its own frozen rates.
  - Isolation salts include the platform ID, so traces are independent of v4/v5, of calibration, and across platforms.
- **Run length.** About 6.0 h of main-stage wall time per platform: blocks run fixed 120 s arms, so wall time does not depend on GPU speed. That is about 24 h for all four.
- **P vs S** is **excluded** from core X1 (owner decision 5). It is preserved as an optional extension, **X1-E1**, which needs its own preregistration and approval.

## 5. Hypotheses and verdict

Notation: ℓ is the per-seed log ratio of victim mean user-facing TTFT, attack/control. The cell estimate is the
geometric mean with a 95% t CI, using the **frozen v5 functions, imported unchanged**.

| ID | Claim | Test | Family |
|---|---|---|---|
| **X1-H1** | On platform p, D vs S at (low, C = 8) exceeds 1.25 | one-sided t of mean ℓ > log 1.25 (`p_superiority`) | **F-X1:** Holm over the 4 platforms (fixed family; p = 1 if not evaluable) |
| **X1-H2** | (low, C = 32) is equivalent within [0.8, 1.25] | TOST (`p_tost`) | **F-X2:** Holm over 8 tests = 4 × H2 + 4 × H3 |
| **X1-H3** | The direct path is equivalent within [0.8, 1.25] | TOST | F-X2 |
| **X1-H4** | At (low, C = 8), attack-arm victim backend TTFT is within [0.9, 1.1] × control, **and** the engine queue is negligible (v5 §5.2 rule) | TOST on the log backend ratio, plus `engine_queue_negligible` | own criterion |
| **X1-H5** | FCFS replay predictions (§6) hold at (low, C = 8), (low, C = 32) and (high, C = 8) | v5 `score_fcfs` cell and seed rules; tolerances from that platform's calibration LOSO | own criterion; all cells are in the validated envelope by design (§6) |
| X1-D1 | (high, C = 8) magnitude and victim SLO collapse; threshold-above-noise using X-f | descriptive | none |

**Verdict** (fixed in advance; power in `docs/X1_P0_REPORT.md` §5):
- **GENERALISES** iff X1-H1 is supported on ≥ 3 of 4 platforms, **and** X1-H2 is equivalent on ≥ 3 of 4, **and** X1-H4 holds on ≥ 3 of 4.
- **ANCHOR-ONLY** iff X1-H1 is supported only on P0-anchor.
- **PARTIAL** otherwise. The report names the failing platform and claim.

A platform whose X1-H1 is "not supported" is **never** reported as evidence that the mechanism is absent. Power per
platform is bounded (§5 of the P0 report).

## 6. Where X1-H5's service-time distributions come from (resolves the open question)

The FCFS replay needs each platform's hold-time distribution, Σ(t_terminal − t_sent) per request class, *before* the
confirmatory runs. Rule:

1. **Calibration B (hold pools).** On each platform, after the rates are frozen, run blocks D vs S and A/A-ind at
   **(low, C = 8)** and **(high, C = 8)** with calibration seeds **7003–7007**: 5 seeds per block, about 1.7 h per
   platform.
   - These seeds and runs are never used in any confirmatory test.
   - Their traces use separate salts, so they share no request with the main stage.
2. **Pools.** Per (platform, operating point, arm, request class), take the empirical hold-time pool from those runs.
   Nothing from v4/v5 and nothing from the main stage enters.
3. **Predictions.** Replay each main-stage schedule (seeds 8000–8015), which is known before running, through a
   global FCFS queue with C slots, resampling holds from the matching pool. This is the same code path as the frozen
   v5 predictor.
   - Predictions for (low, C = 32) use the (low, C = 8) pools, which carries over the v5 cap-transfer caveat. At C = 32 the predicted queue is about 0, so the test is "queueing vanishes".
   - The (high, C = 8) predictions use pools measured at (high, C = 8). This removes v5's extrapolation, where L = 400 pools came from one over-saturated v4 seed, and puts every X1-H5 cell inside the validated envelope.
4. **Tolerances.** Leave-one-seed-out over the 5 calibration seeds per point: τ_abs = max(5 ms, q95 |err|) and ρ_rel. The rules are the same as v5.
5. **Freeze.** Pools, predictions and tolerances are written and SHA-pinned in **Freeze Commit 3**, before any main-stage run.
6. **No expected error direction is preregistered.** The v5 low-load under-prediction bias reversed at depth (`docs/RESULTS_V4_V5.md` §5.2). X1 reports the sign per regime.

## 7. Power (summary; details in `docs/X1_P0_REPORT.md` §5)

The verdict's power is almost entirely X1-H1's: P(H2 ≥ 3/4) = P(H4 ≥ 3/4) = 1.000 in every simulated scenario.

**At v5's effect (1.565×) and v5 variability:**

| n(X-a) | P(GENERALISES) |
|---|---|
| 16 | 0.68–0.85 |
| 24 | 0.94–0.985 |

With heterogeneity or 1.5× variability, n = 16 gives only 0.15–0.48.

**Pending owner choice:**
- (a) n = 24 for X-a and X-d;
- (b) X1-H1 null log 1, with 1.25 as a secondary classification;
- (c) keep n = 16 and accept the stated power.

Recommendation: (a) + (b). The cell table in §4 shows n = 16 until the owner decides. No false generalisation occurred: P(GENERALISES) = 0 when only 2 of 4 platforms have the effect.

## 8. Gates, governance and artifacts

- **Gates:** every v5 gate, unchanged — cap_configured, occupancy reconstruction, timestamp alignment, server identity before and after every block, budget, private-endpoint fail-closed checks, and the verified pre-block prefix-cache reset. The reset requires `VLLM_SERVER_DEV_MODE=1`.
- **P1 per platform and model**, read-only. This uses an X1 collector that:
  - matches the server by Python executable (fixing the shell-wrapper ambiguity);
  - follows content-store symlinks in the Hugging Face cache.
  
  Evidence needed:
  - version and source SHA-256 values equal the pins;
  - argv carries the template;
  - snapshot hash-verified;
  - `cache_config_info` shows block size 16 and memory utilisation 0.80.
- **Analysis:** `scripts/x1_analysis.py` imports the v5 pure rules without modification, and is frozen in Freeze Commit 1.
- **Export:** per platform, using the existing sanitizer. AWS identifiers (account, instance, VPC IDs and private addresses) are added to the regex gate before any AWS stage.
- **Isolation:** owned and private only. AWS endpoints stay inside the isolated VPC under `*.quotashift.internal`. There is no public endpoint and no third-party API.

## 9. Smoke checks per platform (before calibration)

1. Verified prefix-cache reset probe.
2. `/tokenize` parity with offline tokenizer counts for the frozen prompt templates. For M1, use mistral-common 1.10.0.
3. One fixed-length request per shape: output tokens equal `max_tokens`, finite logprobs, non-empty text.
4. Every v5 gate passes on a 2-seed mini block. Smokes are never analysed.

## 10. Staged GPU and AWS approval plan

Each stage needs explicit owner approval, recorded in `docs/DECISIONS.md`, before it starts. Each stage ends with a
report and a stop.

| Stage | What happens | Touches | Cost | Approval token |
|---|---|---|---|---|
| **X0** | P0 research (this rev) | read-only | $0 | done |
| **X1-A** | Owner answers the open items (§11); draft rev 3; ADR-X1 | docs | $0 | review |
| **X1-B** | **Replace root access keys** with a least-privilege IAM identity for this project | AWS IAM | $0 | owner action |
| **X1-C** | gpu-node-2: create the 0.17.1 environment and download both models (about 30 GB from Hugging Face) | local host | $0 (LAN power) | `x1_local_env` |
| **X1-D** | gpu-node-2: restart the Mistral server with the template; post-launch audit (P1); then the same for Qwen | local host | $0 | `x1_local_restart` |
| **X1-E** | AWS prep: Terraform changes (image digest, instance type, AMI `ami-0b8f7c7154f9e8f8b` pinned, private target profile, exporter), `terraform validate`/`test`/`plan` only | repo + read-only AWS | $0 | review |
| **X1-F** | *Only if* g6.2xlarge is chosen: request the G/VT on-demand quota 4 → 8 vCPU | AWS support | $0 | `x1_quota_request` |
| **X1-G** | Freeze Commit 1 (protocol, analysis code, schedule generator) | repo | $0 | `x1_freeze1` |
| **X1-H** | P2 tokenizer trace freeze for both models, on gpu-node-2 (tokenization is model-specific, not GPU-specific) → Freeze Commit 2 | local host | $0 | `x1_p2` |
| **X1-I** | G0 calibration A + B, both models → rates, pools, predictions | local GPU | $0 | `x1_g0_calibration` |
| **X1-J** | `terraform apply` (`aws_ops.sh deploy`) | AWS | NAT about $1.08/day plus storage while applied | `deploy` |
| **X1-K** | `start-gpu`: L4 P1 for both models, smoke, calibration A + B → stop-gpu | AWS GPU | about 6.5 GPU-h (per model: calibration A ≈ 0.9 h + B ≈ 1.7 h + smoke/P1 ≈ 0.6 h) ≈ $5.2 (g6.xlarge) / $6.4 (g6.2xlarge) |  `start-gpu` (x1_g1_calibration) |
| **X1-L** | Freeze Commit 3 (rates, pools, predictions, tolerances for all 4 platforms) | repo | $0 | `x1_freeze3` |
| **X1-M** | G0 main stages: P0-anchor, then P-M | local GPU | $0 | `x1_g0_main` (per platform) |
| **X1-N** | G1 main stages: P-G, then P-MG → stop-gpu | AWS GPU | 12 h of blocks, about 15.6 GPU-h with the 1.3 budget rule ≈ $12.6 (g6.xlarge) / $15.3 (g6.2xlarge) | `start-gpu` (x1_g1_main) |
| **X1-O** | `destroy`; export, verify, frozen analysis; report | AWS + repo | $0 after destroy | `destroy` |

**Budget envelope for AWS.** Run with the GPU at 0 between stages, `max_run_minutes` set per stage, and
`spending_limit_usd` = **$60**. The estimate is **$32–52**; see the P0 report, §4.

## 11. Open items for the owner

1. **g6.xlarge vs g6.2xlarge.** g6.xlarge fits today's 4-vCPU quota but has 4 vCPU and 16 GiB RAM, against 16–20 threads and 30–31 GiB on the G0 hosts. g6.2xlarge (8 vCPU, 32 GiB, +$0.17/h) needs a quota increase. Recommendation: **g6.2xlarge**, to reduce the CPU-side host confound and memory pressure while loading 14.5 GB of weights.
2. **fp16 on all platforms (continuity with v5) vs bf16** (native for both models; supported on 3090 and L4). Recommendation: fp16, with the smoke check.
3. **n confirmation** after the power table.
4. **G0 host.** gpu-node-2 hosts both G0 platforms. gpu-node-1 stays the untouched v5 server.
5. **Approval of stage X1-A**, and of the IAM change (X1-B) before any AWS stage.
