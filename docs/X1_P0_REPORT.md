# X1 P0: read-only research and compatibility report

**Date:** 2026-11-24.
**Scope:** P0 only, as approved by the owner.
- Public metadata lookups (Hugging Face API, Docker Hub registry).
- Free, read-only AWS API calls: EC2 instance-type offerings and descriptions, Service Quotas, the Price List API, SSM public parameters and `sts get-caller-identity`. No Cost Explorer.
- A planning-only power simulation.
- **Nothing provisioned, downloaded, started or frozen.**
- The v4/v5 results and every frozen artifact are unchanged (`scripts/pin_v5.py --check` passes).

Companion documents:
- `docs/PROTOCOL_X1_CROSS_PLATFORM_DRAFT.md`: rev 2 of the X1 draft.
- `docs/X1_M1_COMPATIBILITY_AUDIT.md`: the gpu-node-2 audit.

---

## 0. Security finding (action required before any AWS stage)

`aws sts get-caller-identity` shows that this workstation's AWS credentials are the **account root user**
(`arn:aws:iam::<account>:root`). `docs/aws_cost_controls.md` requires a least-privilege IAM identity instead.

I used these credentials only for the free, read-only P0 calls listed above. Recommendation:
1. Create a project IAM identity with a scoped policy. Short-lived SSO credentials are preferred.
2. Deactivate the root access keys.
3. Re-run P0's read-only checks under the new identity before stage X1-J.

This is stage **X1-B** in the approval plan.

## 1. Model M1: mistralai/Mistral-7B-Instruct-v0.3

| Item | Verified value | Source |
|---|---|---|
| Official revision | **`c170c708c41dac9275d15a8fff4eca08d52bab71`**, current `main` (last commit 2025-12-03: "Update README.md"). The weight and tokenizer files are older; the tokenizer dates from 2024-08-21 | HF API |
| Licence | **Apache-2.0** (`cardData.license`), not gated | HF API at the pinned revision |
| Architecture | `MistralForCausalLM`: 32 layers, d = 4096, 32 query heads / **8 KV heads**, head dim 128, FFN 14336, vocab **32,768**, rope θ 1e6, no sliding window, untied embeddings | `config.json` / `params.json` at the pinned revision |
| Parameters / stored dtype | **7,248,023,552**, BF16 | HF safetensors metadata |
| Weights (Mistral format) | `consolidated.safetensors`, 14,496,078,512 B, SHA-256 `76d5729b…94d1f`. Also hash-verified on gpu-node-2 | HF tree API, plus the local hash |
| Tokenizer | mistral-common **v3** SentencePiece (`tokenizer.model.v3`). HF `tokenizer.json` also exists. X1 pins `--tokenizer-mode mistral` so the choice is never automatic | HF tree; the gpu-node-2 log ("Using tokenizer.model.v3") |
| vLLM 0.17.1 compatibility | **Supported** in the installed source: `MistralForCausalLM` is registered, `--tokenizer-mode/--config-format/--load-format mistral` exist, and the loader handles `consolidated*.safetensors`; mistral_common 1.10.0. *A clean load and tokenizer parity are confirmed only at the X1-D smoke* | 0.17.1 source on gpu-node-1 |
| Chat template | Not used. X1, like v5, sends `/v1/completions` with frozen benign prompts | — |

### fp16 VRAM (estimates, not measurements)

**Method.** The overhead model is calibrated on the measured 3090 + Qwen + 0.17.1 run: memory budget 0.80 × 23.56 GiB =
18.85 GiB, minus Qwen weights 14.18 GiB, minus logged KV 3.98 GiB, leaves **0.69 GiB** of overhead. The same overhead is
assumed everywhere. KV cost per token = 2 × layers × KV heads × head dim × 2 B.

| Platform | Memory budget at 0.80 | Weights (fp16) | KV left | KV bytes/token | **KV tokens** | Concurrency at 4,096 tokens | Concurrency at the largest X1 request (320 tokens) |
|---|---|---|---|---|---|---|---|
| G0 + Qwen (measured, v5) | 18.85 GiB | 14.18 GiB | 3.98 GiB | 56 KiB | **74,592** (measured) | 18.2× | 233 |
| G0 + Mistral | 18.85 | 13.50 | ≈ 4.66 | 128 KiB | **≈ 38,000** | ≈ 9.3× | ≈ 119 |
| G1 + Qwen | ≈ 17.88 (L4 22,888 MiB per EC2) | 14.18 | ≈ 3.01 | 56 KiB | **≈ 56,000** | ≈ 13.8× | ≈ 176 |
| G1 + Mistral | ≈ 17.88 | 13.50 | ≈ 3.69 | 128 KiB | **≈ 30,000** | ≈ 7.4× | ≈ 94 |

- **Fit.** Both models fit in fp16 on both GPUs at 0.80. G1 + Mistral is the tightest platform.
- **KV is not the binding resource in X1's operating range.** The largest request (64 + 256 tokens) fits about 94 times over on G1 + Mistral. v4/v5 direct-path runs peaked at about 25 concurrent requests, and C = 32 means at most 32 on the gated path.
- **Check at P1.** The actual `cache_config_info` and KV tokens per platform are recorded at P1, and X1-H4's "engine queue negligible" criterion would detect KV-driven admission waits.
- **The KV difference is model-intrinsic.** Mistral uses 2.3× Qwen's KV per token, so this difference is part of the M contrast and is disclosed.

## 2. GPU G1: NVIDIA L4 on AWS (us-east-1)

| Item | Finding (2026-11-24) |
|---|---|
| Availability | g6.xlarge, g6.2xlarge and g6.4xlarge are offered in **all 5** relevant us-east-1 AZs (1a, 1b, 1c, 1d, 1f). g5.2xlarge is offered too |
| Instance specs | g6.xlarge: 4 vCPU, 16 GiB, 1 × L4 (22,888 MiB). g6.2xlarge: 8 vCPU, 32 GiB, 1 × L4. g6.4xlarge: 16 vCPU, 64 GiB, 1 × L4 |
| On-demand G/VT quota (`L-DB2E81BA`) | **4 vCPU** (a request was closed at 4 on 2026-11-18) → **g6.xlarge fits; g6.2xlarge needs an increase to 8** |
| Spot G/VT quota | 0. Spot is not planned anyway, because interruptions would break server identity |
| ECS GPU AMI (AL2023) | `ami-0b8f7c7154f9e8f8b` = `al2023-ami-ecs-gpu-hvm-2023.0.20261119-kernel-6.1-x86_64-ebs` (SSM, updated 2026-11-20; 30 GB root snapshot). Its driver/CUDA compatibility with the 0.17.1 image is checked at P1 |
| vLLM image | `vllm/vllm-openai:v0.17.1` = `sha256:0dc46f74eb0e630675d83101dc66c6441c4475cceedcf9235ee42b87c3affd23` (Docker Hub index digest). Not pulled. Its vLLM source SHA-256 values are checked at P1. The repo's current stack pins **v0.33.0** (`configs/infrastructure/aws-l4.yaml`) and must be changed in X1-E |
| Host comparison with G0 | g6.xlarge has 4 vCPU / 16 GiB, against i7-12700K (20 threads) / 31 GiB and Ryzen 7 7800X3D (16 threads) / 30 GiB. The API server and tokenization are CPU-side: a host confound inside the G contrast. g6.2xlarge narrows it |

## 3. Regional pricing (us-east-1, on-demand, Linux, shared tenancy)

Price List API: effective 2026-11-01, publication 2026-11-24.

| Item | USD |
|---|---|
| g6.xlarge | **0.8048 / h** |
| g6.2xlarge | **0.9776 / h** |
| g6.4xlarge | 1.3232 / h |
| g5.2xlarge (reference) | 1.2120 / h |
| EBS gp3 | 0.08 / GB-month |
| NAT gateway | 0.045 / h, plus 0.045 / GB |
| Public IPv4, logs, S3, ECR | as in `configs/infrastructure/prices.us-east-1.yaml` (2026-11-18). Fargate values there are **unverified** list prices |

## 4. Estimated total AWS cost

**Method.** Uses `scripts/estimate_cost.py` with the price file above and NAT network mode. Assumptions:
- the infrastructure exists for 96 h;
- 60 GB passes through the NAT (two models at about 15 GB each, plus the image, plus slack);
- 120 GB EBS;
- 2 GB of logs.

| Scenario | GPU-hours | g6.xlarge | g6.2xlarge |
|---|---|---|---|
| Plan: G1 calibration 6.5 h + G1 main 12 h, ×1.3 contingency, plus startup | **≈ 26** | **$32.41** | **$36.91** |
| Pessimistic: reruns, a second P1, slow model loads | 40 | $45.25 | $52.16 |

- **What the estimates exclude:** taxes, data transfer out, support, and the G0 local electricity.
- **Proposed limits:** `spending_limit_usd` = $60 and `max_run_minutes` per stage.
- **Cost Explorer was not used.** Its calls are billed and gated.

## 5. Joint power of the 3-of-4 verdict under Holm (planning simulation)

**Method.** `scripts/x1_power.py` (planning only), with the full table in `reports/x1/P0_POWER.md`.
- 1,000 replicates per scenario. The frozen v5 decision functions are imported unchanged.
- Inputs are v5 Stage A per-seed moments: X-a log ratio mean 0.448 (1.565×), SD 0.330; X-b SD 0.023; X-c SD 0.021; backend log ratio SD 0.014.
- Varied:
  - the true X-a ratio (1.4, 1.565, 1.8);
  - platform heterogeneity τ on the log scale (0, 0.2);
  - an SD inflation k for the unknown L4/Mistral variability (1, 1.5);
  - n(X-a) (10, 16, 20, 24);
  - the noise model: Normal, or "empirical", meaning resampled v5 residuals with their right tail.

**Results.**
1. **Power comes from H1.** P(H2 ≥ 3/4) and P(H4 ≥ 3/4) are **1.000 in every scenario**. Their margins are huge at v5-like variability, so the verdict's power equals P(X1-H1 Holm-supported on ≥ 3 of 4).
2. **At the v5 estimate (1.565×) with v5 variability (k = 1, τ = 0):**

   | n(X-a) | P(GENERALISES), normal | P(GENERALISES), empirical |
   |---|---|---|
   | 10 | 0.27 | 0.31 |
   | **16** | **0.68** | **0.85** |
   | 20 | 0.87 | 0.95 |
   | 24 | 0.94 | 0.985 |

3. **Fragility.** With moderate heterogeneity (τ = 0.2) or 1.5× variability, n = 16 drops to **0.15–0.48**, and even n = 24 reaches only 0.37–0.59.
   - At 1.8×, n = 16 gives 0.61–1.00 across the scenarios.
   - At 1.4× (close to the 1.25 threshold), power is below 0.25 at every n tested.
4. **No false generalisation.** With the mechanism present (1.8×) on only 2 of 4 platforms, P(GENERALISES) = **0.000** at n = 16 and at n = 24. The verdict does not over-claim.

**Interpretation.** The binding constraint is that X1-H1 tests "> 1.25" on every platform, under Holm, with a 3-of-4
requirement. That is a demanding *magnitude* claim. Owner decision 4 (n = 16) gives adequate power only if the true
per-platform effect is at least v5-sized **and** variability on L4 and Mistral is no larger than on the 3090 with Qwen.

**Options for the owner** (one must be chosen before freeze; this is not changed unilaterally):
- **(a) n(X-a) = n(X-d) = 24.** Power is 0.94–0.985 in the base case. Cost: about +1.3 h of wall time per platform, i.e. about +3.4 AWS GPU-h ≈ +$3 at g6.2xlarge, and about +2.6 h on G0.
- **(b) Keep n = 16 and change X1-H1's null from log 1.25 to log 1** ("amplification exists"). Keep 1.25 as a reported magnitude classification. This tests transfer of the *mechanism*, which is X1's stated purpose, and has much higher power. It is a hypothesis change, so it must be decided before freeze.
- **(c) Keep n = 16 and the 1.25 null**, accepting about 0.7–0.85 power in the base case and much less under heterogeneity, and say so in the protocol.

**Recommendation: (a) + (b) together**: n = 24 for X-a and X-d, with the primary null log 1, and the 1.25 test kept as a
preregistered secondary. Lower-cost alternative: (b) alone. The joint table for option (b) needs one more simulation
run, cheap and offline, once the owner picks it.

## 6. X1-H5 service-time source (owner question)

Resolved in draft rev 2, §6.
- **Source.** Hold-time pools come from a dedicated per-platform **Calibration B**: seeds 7003–7007, D vs S and A/A at both operating points with C = 8.
- **Independence.** Calibration runs are never used confirmatorily, and the main-stage seeds 8000–8015 are disjoint from them.
- **Order.** Pools, predictions and LOSO tolerances are pinned in Freeze Commit 3, before any main-stage run.
- **Effect.** All X1-H5 cells fall inside the validated envelope. This removes v5's extrapolation problem.

## 7. Preserved invariants
- Per-platform slot-demand calibration (draft §3) and independently sampled seeds (draft §4) are kept.
- The v4/v5 results and all frozen artifacts are unchanged.
- No AWS resource was created. No model, image or weights were downloaded. No GPU work was run. Nothing was frozen.

---

## Addendum: owner decision of 2026-11-24 (g6.xlarge)

The owner chose **g6.xlarge** (4 vCPU, 16 GiB, 1 × L4) in us-east-1. This replaces the recommendation in §2 and §4
of this report.
- **No quota increase.** The current 4-vCPU G/VT quota fits exactly one g6.xlarge.
- **Kept:** fp16, the model revisions, the full 2 × 2 design, n = 24 for X-a and X-d (power option (a)), and the primary 1.25× threshold.

**Recalculated AWS cost** (g6.xlarge $0.8048/h re-verified today):
- **Inputs:** `configs/infrastructure/prices.us-east-1.2026-11-24.yaml`; NAT mode; the stack existing 120 h; 60 GB through the NAT; 120 GB EBS.
- **GPU-hours:** G1 calibration ≈ 6.5 h, plus G1 main 14.7 h of blocks at n = 24 (≈ 19.1 h with the 1.3 rule), plus startup.

| Scenario | GPU-hours | Total |
|---|---|---|
| Plan | ≈ 29 | **$36.24** |
| Pessimistic | 45 | **$50.91** |

The $60 cap and every cost control are kept.

**CPU and RAM confounders.** CPU and RAM limits on g6.xlarge are treated as possible cross-platform confounders. Draft
rev 3 adds:
- preregistered preflight checks (§9.1): model-loading success, GPU KV capacity, available system RAM, CPU utilisation and tokenization throughput;
- per-arm host-telemetry flag gates (§9.2);
- an interpretation rule that labels flagged GPU contrasts "GPU+host, host-limited" (§2.2).
