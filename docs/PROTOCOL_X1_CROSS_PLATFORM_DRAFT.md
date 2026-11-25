# Protocol X1: independent cross-model and cross-GPU validation (rev 4 FINAL, owner-approved; NOT frozen, not run)

**Status:** rev 4, **approved as final by the owner on 2026-11-24 (X1-A)**.
- **No content change** from the reviewed draft.
- **Not yet frozen:** freezing is stage X1-G (Freeze Commit 1), which needs its own approval and first requires building and testing `scripts/x1_analysis.py` and the X1 schedule generator.
- **History:** the review text below is kept as written.
- **Supersedes:** rev 3 (commit `a151327`).
- **Owner review of rev 3:**
  - X1-A approved **conditionally**, for final protocol revisions;
  - preparation of the X1-B least-privilege IAM migration approved.
- **Kept:**
  - g6.xlarge (4 vCPU, 16 GiB, 1 × L4);
  - fp16 and vLLM 0.17.1;
  - n = 24 for X-a and X-d, n = 10 elsewhere;
  - X1-H1 threshold 1.25×;
  - the optional, separately gated 4-core diagnostic;
  - the power analysis, the cost limits and the statistical rules (all unchanged).
- **Rev 4 resolves the rev 3 review items:**
  - **Preflight ordering:** preflight is split into Phase 1 and Phase 2 (§9.1).
  - **Model-loading failure conditions:** failure is judged on observable serving failure, not log text (§9.1).
  - **Tokenization thresholds:** rationale given; isolated latency is separated from burst queueing (§9.1).
  - **Sampler distortion:** measured (§9.2).
  - **Staged plan:** updated (§10).
- **Implementation (not frozen):**
  - `src/quotashift/x1/preflight.py` (rules);
  - `src/quotashift/x1/tokenize_probe.py`;
  - `scripts/x1_host_sampler.py`.
  
  Tests are in `tests/unit/test_x1_*.py` and `tests/integration/test_x1_tokenize_probe.py`.
- **Not yet done:** no hardware provisioned, no model downloaded, no restart, nothing frozen. Every host, GPU or AWS step follows §10.
- **Unchanged by X1:** the v4/v5 results and every frozen v5 artifact.

Companion documents:
- `docs/X1_P0_REPORT.md`;
- `docs/X1_M1_COMPATIBILITY_AUDIT.md`;
- `docs/X1_IAM_MIGRATION_CHECKLIST.md`;
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

## 9. Preflight and smoke (per platform and model)

### 9.1 Preflight, split into two phases (resolves the ordering dependency)

The rev 3 CPU check ran "at the **high** operating point", and the tokenization rule used "the peak offered request
rate at the high operating point". Both exist only **after** calibration A. Rev 4 therefore splits preflight in two:

- **Phase 1:** after the server starts, before any calibration.
- **Phase 2:** after calibration A has chosen the platform's low and high rates, and before calibration B. Phase 2 uses those rates.

Both phases must pass, or flag, before calibration B. A fail in either phase makes the platform **not admissible**:
it is reported, never replaced. Calibration-A arms carry the §9.2 telemetry, so an overloaded host is visible before
Phase 2.

**Thresholds** are module constants in `src/quotashift/x1/preflight.py`, unit-tested, and frozen at X1-G. They are
identical on all platforms.

| Phase | Check | Measurement | Fail (not admissible) | Flag (reported) |
|---|---|---|---|---|
| 1 | **Model loading** (§9.1.1) | `/health`; "Application startup complete"; `/v1/models`; snapshot weight SHA-256; argv vs template; one fixed-length smoke generation per shape; load wall-time | **Observable** failure only: not healthy; startup not completed; pinned revision not listed; hash mismatch; argv ≠ template; smoke generation wrong length, non-finite logprobs or empty; no healthy server within 30 min | ERROR/CRITICAL/Traceback lines on an otherwise healthy server (owner review); load time > 2 × G0 for the same model |
| 1 | **GPU KV capacity** (preserved) | `vllm:cache_config_info` num_gpu_blocks × block_size | KV < **20,480** tokens | — (Phase 2: KV < 4 × the direct-path peak KV demand seen in calibration A) |
| 1 | **System RAM, idle** (preserved) | `MemAvailable` after load; `oom_kill`; `pswpin` | any OOM kill; MemAvailable < **1 GiB** | < 2 GiB; any swap-in |
| 1 | **Isolated tokenization latency** | 200 sequential `/tokenize` requests over the frozen prompt templates, one in flight (no queueing) | p99 > **25 ms** | p99 > 2 × G0's p99 for the same model (with a 1 ms floor) |
| 1 | **Idle TTFT floor** (descriptive) | 20 single requests per shape, idle server | — | — (recorded) |
| 1 | **Sampler on/off equivalence** (§9.2) | the idle TTFT floor, measured twice: sampler running vs stopped | difference in median > 1 ms **and** > 2% | — |
| 2 | **CPU under the high load** | §9.2 sampler during a 2-seed smoke mini-block at the calibrated **high** rate | host CPU ≥ 95% for ≥ 10% of samples | API server ≥ 85% of a core for ≥ 5% of samples; host ≥ 80% for ≥ 10% |
| 2 | **RAM under load** (preserved) | the same mini-block | any OOM kill; MemAvailable < 1 GiB | < 2 GiB; any swap-in |
| 2 | **Tokenization capacity** | utilisation ρ = (peak offered request rate at the high rate) × (mean isolated latency from Phase 1); then an open-loop `/tokenize` burst at **10 × peak** for 30 s | ρ > **0.10**; burst sustains < 95% of the offered rate; burst p99 − isolated p99 > **10 ms** | burst p99 − isolated p99 > 5 ms |

#### 9.1.1 Model loading: what can and cannot fail a platform

A serving instance is judged on **observable behaviour**, never on log text alone.

- **Never relevant:** WARNING lines. Examples seen on the real hosts:
  - `Casting torch.bfloat16 to torch.float16`;
  - the 131 per-weight dtype warnings of vLLM 0.34.0;
  - `FlashInfer kernels are disabled`;
  - torch deprecation notices;
  - "unauthenticated requests to the HF Hub".
- **Flag only:** ERROR, CRITICAL or Traceback lines on a server that is otherwise healthy and passes the smoke generation. They are recorded for owner review before calibration. A crash that matters always shows up in one of the observable fail conditions.
- **Fail:** the conditions in the table above.

#### 9.1.2 Tokenization thresholds: rationale (isolated latency vs burst queueing)

The two measurements answer different questions and are evaluated separately (`tokenization_check`).

1. **Isolated latency** is the per-request CPU cost of tokenizing one prompt, plus HTTP overhead, with nothing
   queued. It is an upper bound on what tokenization adds to **every** request's TTFT.
   - In D vs S both arms send 64-token prompts, so a constant tokenization cost largely cancels in the attack/control ratio. The isolated check therefore guards against a *pathologically slow* platform: for example a slow tokenizer fallback, or the wrong tokenizer mode.
   - **Fail at p99 > 25 ms.** That is about 30% of the about 82 ms idle victim TTFT in v5. Beyond it, user-facing TTFT on that platform would be dominated by CPU-side work, so it would no longer be the system under study.
   - **Flag at > 2 × G0's value.** This makes a host-induced slowdown visible even when the absolute threshold is met.
   - Rev 3's single "p99 > 50 ms during a concurrency-8 burst" mixed this cost with queueing. Under a closed-loop burst, latency includes waiting behind up to 7 other requests, so a 50 ms burst p99 could hide a 6 ms service time or a 45 ms one. It is therefore replaced.
2. **Burst queueing** asks whether the API server has enough tokenization *capacity* at the platform's peak load.
   - **Capacity rule:** utilisation ρ = λ_peak × E[S] ≤ 0.10. This is the rev 3 "10× headroom", now stated as a utilisation. For an M/G/1 queue the mean wait is W = ρ/(1−ρ) · E[S²]/(2E[S]). At ρ = 0.10 that is 0.056 E[S] for deterministic and 0.111 E[S] for exponential service times. Tokenization queueing is then a small fraction of one tokenization, which is itself bounded by part 1.
   - **Validating test:** the queueing model is an assumption, so it is checked empirically. An **open-loop** burst at 10 × λ_peak, at fixed arrival times, must be **sustained** (≥ 95% of the offered rate completed) and must not raise p99 by more than 10 ms over the isolated p99 (flag above 5 ms).
   - The burst must be open-loop. A closed-loop burst slows its own arrivals when the server slows, and so hides saturation.
   - **Limit:** `/tokenize` exercises the API server's tokenizer path but not the generation scheduler. The per-arm §9.2 telemetry covers the generation path.

### 9.2 Per-arm host telemetry and flag gates; sampler distortion check

- **Sampler.** `scripts/x1_host_sampler.py`: standard library, read-only `/proc`, 1 Hz, `nice 19`, output to stdout. It identifies the API server by its Python executable plus `vllm … serve` argv, which excludes the `bash -c` wrapper, and EngineCore by name.
- **`host_cpu_headroom` (flag):** API server ≥ 85% of one core for ≥ 5% of the arm's samples, **or** host total ≥ 80% for ≥ 10%.
- **`host_ram_headroom` (flag):** MemAvailable < 2 GiB at any sample, or any swap-in.
- **Fail severity:** an OOM kill during an arm → the block fails (v5 rerun rule).
- **Sampler cost:** a sampler using ≥ 1% of one core during an arm → that arm's host telemetry is invalid (`sampler_overhead_check`). It reports its own CPU in every run.

**Measured distortion** (2026-11-24, 20:06–20:07; gpu-node-2, the X1 G0 host; idle Mistral 0.34.0 server; 60 s; read-only):

| Quantity | Value |
|---|---|
| Sampler CPU | **0.0278 s in 60.0 s = 0.046% of one core** (≈ 0.012% of host capacity on a 4-vCPU g6.xlarge) |
| Sampler memory | 12.6 MiB max RSS |
| Tick spacing | 1.000 s (max 1.000 s) |
| Processes found | API server and EngineCore found; the wrapper was excluded |

- **Why it cannot distort materially:**
  - Every tick reads about six small `/proc` files. It does not ptrace, signal or lock the vLLM processes.
  - It writes no files on the host and uses no GPU or network beyond the ssh stdout stream.
- **Still to check under load:** load-dependent effects are covered by the Phase 1 sampler on/off TTFT equivalence check, which runs during the approved X1-D stage.

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
| **X1-A** | Owner review of rev 4 (conditionally approved for final revisions); ADR-X1 | docs | $0 | review |
| **X1-B** | Least-privilege, temporary-credential migration per `docs/X1_IAM_MIGRATION_CHECKLIST.md`. **Every create, deactivate or rotate step is performed by the owner**, with explicit confirmation. `aws_ops.sh` already refuses root credentials | AWS IAM | $0 | owner action, step by step |
| **X1-C** | gpu-node-2: create the 0.17.1 environment; download both models (≈ 30 GB) | local host | $0 | `x1_local_env` |
| **X1-D** | gpu-node-2: restart with the template; P1 and **preflight Phase 1** per model (incl. the sampler on/off check); smoke | local host | $0 | `x1_local_restart` |
| **X1-E** ✅ 2026-11-24 | AWS prep in the repo: Terraform variables (`g6.xlarge`, AMI pinned, image digest 0.17.1, host-telemetry sampler, exporter, private target profile, AWS identifiers in the export gate); `terraform fmt`/`validate`/`test`/read-only `plan` | repo + read-only AWS | $0 | review |
| ~~X1-F~~ | ~~quota increase~~: **not requested** (owner decision) | — | — | — |
| **X1-G** | Freeze Commit 1 (protocol, analysis code, schedule generator, preflight thresholds) | repo | $0 | `x1_freeze1` |
| **X1-H** | P2 tokenizer trace freeze for both models on gpu-node-2 → Freeze Commit 2 | local host | $0 | `x1_p2` |
| **X1-I** | G0, per model: calibration A → **preflight Phase 2** at the chosen high rate → calibration B. Stop if Phase 2 fails | local GPU | $0 | `x1_g0_calibration` |
| **X1-J** | `aws_ops.sh deploy` (reviewed plan only) | AWS | NAT ≈ $1.08/day plus storage while applied | `deploy` |
| **X1-K** | `start-gpu`, per model: P1 + **Phase 1** + smoke → calibration A → **Phase 2** → calibration B → `stop-gpu`. Stop at any fail | AWS GPU | ≈ 6.5 GPU-h ≈ **$5.23** | `start-gpu` (x1_g1_calibration) |
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
1. Review the rev 4 resolutions in §9.1–9.2, including the replacement of the rev 3 "p99 > 50 ms during a concurrency-8 burst" check by isolated p99 > 25 ms, plus ρ ≤ 0.10, plus an open-loop burst excess ≤ 10 ms.
2. Carry out X1-B step by step, following the checklist. No credential is created, deactivated or rotated automatically.
3. Final approval of X1-A, after which X1-G (Freeze Commit 1) can be requested.
