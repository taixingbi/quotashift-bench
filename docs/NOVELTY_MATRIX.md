# Novelty Matrix — RISK-Sched (Paper A)

Status: **Milestone 0 draft, 2026-11-18.** This is an audit, not a claim. The proposed novelty is
**tentative and currently at risk** (see §3). Verification level is stated for every entry; "full text
read" is **not** yet true for any entry. Reported numbers from other papers are their authors' claims.

Verification levels:
- **V1** — venue/proceedings or arXiv abstract page located via web search on 2026-11-18; abstract-level summary only.
- **V0** — title/ID seen only in search listings or reference lists; content unverified. Must be read before citing.

## 1. Proposal under test (tentative)

Tenant-level allocation of **SLO-violation risk** (a per-tenant probabilistic allowance), jointly with GPU
compute and KV-cache pressure, driven by **calibrated output-length uncertainty** that is updated online,
plus **work-conserving reclamation** of unused budget. Initial implementation point: **gateway-level
admission/dispatch** in front of an unmodified, pinned vLLM (ADR-001); token-step scheduling is *not* claimed.

## 2. Matrix

| Work (venue) | Verif. | Information used | Granularity / where | Decisions | Objective | Fairness model | Workloads | Specific difference from proposal | Overlap risk |
|---|---|---|---|---|---|---|---|---|---|
| **VTC** — Sheng et al., *Fairness in Serving LLMs*, OSDI 2024. [usenix](https://www.usenix.org/conference/osdi24/presentation/sheng), [arXiv 2401.00588](https://arxiv.org/abs/2401.00588), artifact [Ying1123/VTC-artifact](https://github.com/Ying1123/VTC-artifact) | V1 | Per-client service received (weighted input/output tokens), observed online | Inside the engine, continuous-batching iteration | Which client's requests join the batch | Service equality among backlogged clients; work-conserving; proven 2x bound | Weighted token-service fairness | Synthetic + real traces (paper) | VTC equalizes **service**, not **SLO-violation risk**; no output-length uncertainty or KV-pressure model; engine-internal. RISK-Sched must beat or complement VTC on worst-tenant SLO attainment, not on service equality. | Medium (fairness baseline; mandatory comparison) |
| **JITServe** (earlier *Tempo*) — Zhang et al., NSDI 2026. [usenix](https://www.usenix.org/conference/nsdi26/presentation/zhang-wei), [arXiv 2504.20068](https://arxiv.org/abs/2504.20068v3), artifact [UIUC-MLSys/JITServe](https://github.com/UIUC-MLSys/JITServe) | V1 | Imprecise request info (response length, dependencies); quantile-regression-forest upper bounds, refined during generation | Engine-level scheduler (GMAX: Grouped Margin Goodput Maximization) | Bandwidth allocated per request "just-in-time" to meet its SLO | SLO attainment / goodput under mixed SLOs | Not tenant-centric as far as the abstract shows (**verify**) | Mixed-SLO apps (chat, streaming, batch/agent) | Closest prior art on **uncertainty-aware SLO scheduling with online refinement**. Remaining candidate differences: explicit **per-tenant risk budgets**/isolation and gateway-only deployability. Both must be checked against the full paper. | **High** |
| **DLPM / D²LPM** — Cao et al., *Locality-aware Fair Scheduling in LLM Serving*, 2025. [arXiv 2501.14312](https://arxiv.org/abs/2501.14312) | V1 | Prefix-cache locality + per-client deficit counters | Engine scheduler + distributed router | Ordering that trades locality vs fairness | Throughput with fairness guarantee | Deficit-based client fairness | Prefix-heavy workloads | Prefix locality, not SLO risk / length uncertainty. Our E0–E4 disable prefix caching by default, so DLPM's main lever is intentionally neutralized — must be stated as a scope choice. | Low–Medium |
| **Equinox** — Wei et al., *Holistic Fair Scheduling in Serving LLMs*, 2025. [arXiv 2508.16646](https://arxiv.org/abs/2508.16646) | V1 | User fairness counter + resource fairness counter; **predicted** post-execution metrics (Mixture of Prediction Experts) | Engine scheduler | Holistic-fairness-ordered batching | Fairness + throughput/TTFT | Holistic (user + resource) fairness | ShareGPT, LMSYS, synthetic | Already combines fairness with **predicted** resource use. Difference must come from SLO-*risk* budgeting and calibration guarantees, not from "fairness + prediction". | **Medium–High** |
| **Justitia** — Yang et al., 2025/2026. [arXiv 2510.17015](https://arxiv.org/abs/2510.17015) | V1 | Memory-centric service cost; virtual-time fair queuing (application level) | Engine/app scheduler | Application ordering | App completion time with bounded fairness delay | Virtual-time fair queuing (memory cost) | Task-parallel LLM agents | KV/memory-cost fairness already exists; it targets completion time, not tenant SLO-risk allowances. | Medium |
| **QLM** — Patke et al., *Queue Management for SLO-Oriented LLM Serving*, SoCC 2024. [ACM](https://dl.acm.org/doi/pdf/10.1145/3698038.3698523), [arXiv 2407.00047](https://arxiv.org/abs/2407.00047) | V1 | Request waiting-time estimator; output lengths from a fitted history distribution | **Queue / global scheduler outside the engine** (multi-model) | Request groups, eviction, model swapping, admission/rate limiting | SLO attainment + throughput | Not tenant-fairness-centric (verify) | Batch + interactive across models | Closest **gateway-level** prior art using length distributions for SLO-aware queueing. Our distinction would be per-tenant risk budgets + KV-pressure feedback on one shared engine. | **Medium–High** |
| **Andes** — Liu et al., 2024. [arXiv 2404.16283](https://arxiv.org/abs/2404.16283) (venue not confirmed) | V1 | Token-delivery timeline (QoE), GPU resource use | Token-level preemptive engine scheduler | Preemption/prioritization per token | Average QoE | None (QoE) | Text streaming | Per-request QoE, no tenant budgets or length-uncertainty calibration. | Low–Medium |
| **Learning to Rank (LTR)** — Fu et al., NeurIPS 2024. [proceedings](https://proceedings.neurips.cc/paper_files/paper/2024/hash/6c8985579293e0209bdaa4f21bb1d237-Abstract.html), code [hao-ai-lab/vllm-ltr](https://github.com/hao-ai-lab/vllm-ltr) | V1 | Learned relative output-length ranking | Engine scheduler (vLLM fork) | Approximate SJF order | Latency / throughput | None | Chatbot, synthetic data generation | Predictor + SJF; no tenant risk or KV budget. A natural **predictor baseline** for M3. | Low (as method), useful baseline |
| **Adaptively Robust LLM Inference under Prediction Uncertainty** — Chen, Ye, Zhou, 2025. [arXiv 2508.14544](https://arxiv.org/abs/2508.14544) | V1 | Prediction **intervals** for output length | Theory + simulation scheduling | Batch/ordering using lower (A_min) vs upper (A_max) bounds | Total latency, competitive ratio | None | LMSYS-Chat-1M | Shows upper-bound (A_max-like) reservation underutilizes as uncertainty grows; informs our "max_tokens reservation" baseline and calibration design. | Low–Medium |
| **FairInference / Token Latency Fairness** — *Performance Isolation for Multi-Tenant LLM Serving*, 2026. [arXiv 2609.18112](https://arxiv.org/abs/2609.18112) | V1 (abstract via search summary) | Per-token deadlines; delay from compute sharing **and shared KV cache** | Engine (SGLang) | Per-token deadline enforcement | δ-fairness: bounded per-token delay vs isolated execution | Latency isolation for well-behaved tenants | Single A100, Llama-3-8B (per summary) | **Directly targets multi-tenant latency isolation with KV-aware accounting.** Our candidate difference: probabilistic risk *budgets* (allowing controlled misses) and gateway-level deployment; may be insufficient. | **High** |
| **Robust KV Cache Management under Output-Length Uncertainty**, 2026. [arXiv 2607.16892](https://arxiv.org/abs/2607.16892) | V0/V1 (search summary only) | Output-length distribution; Wasserstein DRO | KV reservation policy | How much KV to reserve vs preemption risk | Cost vs SLO violations | Tenant handling unknown | BurstGPT, Azure, ShareGPT (per summary) | Uncertainty-calibrated **KV reservation with explicit risk** — overlaps component A+B of our method. Need full read. | **High** |
| **Cascade: SLO-aware latency budget for fair and high goodput LLM serving**, 2026. [arXiv 2608.06557](https://arxiv.org/abs/2608.06557) | **V0** | Unknown (title suggests SLO latency budgets + fairness) | Unknown | Unknown | Fairness + goodput | Unknown | Unknown | Title overlaps "SLO budget + fairness + goodput". **Must be read before any novelty claim.** | **Potentially High** |
| **MAPS** — Memory-Aware Predictive Scheduling, 2026. [arXiv 2609.15359](https://arxiv.org/html/2609.15359v1) | V0/V1 | Conformal output-length intervals for memory budgeting | PD-disaggregated serving | Memory budgeting / scheduling | Throughput/SLO | Unknown | Unknown | Calibrated (conformal) length intervals for KV budgeting already exist; our calibration component is not novel by itself. | Medium–High |
| **throttLL'eM**, 2024. [arXiv 2408.05235](https://arxiv.org/html/2408.05235v2) | V1 (search summary) | Predicted generation lengths → projected KV usage and batch size | Admission + GPU frequency throttling | Admit / throttle | Energy under SLO | None | — | Admission control via projected KV usage + SLO check already exists (single-tenant, energy objective). | Medium |
| **Scheduling the Unschedulable: Taming Black-Box LLM Inference at Scale**, 2026. [arXiv 2604.06970](https://arxiv.org/pdf/2604.06970) | **V0** | Unknown | Likely external / black-box | Unknown | Unknown | Unknown | Unknown | Title suggests **engine-agnostic (black-box) scheduling** — would overlap our "gateway-only" deployability argument. Must be read. | **Potentially High** |
| **vLLM native** — FCFS (default) and `--scheduling-policy priority`; KV preemption (V1 default: recompute); Prometheus `/metrics`. [docs](https://docs.vllm.ai/), [metrics design](https://docs.vllm.ai/en/v0.12.0/design/metrics/) | V1 (flag listing seen in engine-args docs; semantics to be verified on the pinned version) | Arrival order / client-supplied priority | Engine | Batch admission, preemption | Throughput | None | — | Mandatory baselines. Priority semantics (lower value first? preemption on priority?) must be verified against pinned v0.33.0 source. | Baseline |

Also to audit in M2/M3 (not yet searched in depth): Sarathi-Serve, DistServe, Llumnix, SLOs-Serve, ELIS
([arXiv 2505.09142](https://arxiv.org/pdf/2505.09142)), S³, SSJF/proxy-model length prediction, OUTLETS
([arXiv 2609.01068](https://arxiv.org/pdf/2609.01068)), HAServe ([arXiv 2605.08581](https://arxiv.org/pdf/2605.08581)),
LayerKV, SOLA, FairBatching (ID unconfirmed).

## 3. Assessment (honest, Milestone 0)

1. **No single component is novel.** Uncertainty-aware SLO scheduling (JITServe), fairness with predicted
   resource use (Equinox), KV/memory-cost fairness (Justitia), calibrated length intervals for KV budgeting
   (MAPS, DRO-KV), KV-aware tenant latency isolation (FairInference), and gateway-level SLO queueing with
   length distributions (QLM) all exist.
2. **Candidate remaining gap (unverified):** a *per-tenant probabilistic SLO-violation budget* (allowing a
   controlled, tenant-weighted miss rate rather than per-token deadlines or service equality), coupled to
   measured KV/compute pressure on a **shared, unmodified** engine, with reclamation. Whether this survives
   depends on Cascade, FairInference, DRO-KV, JITServe and "Scheduling the Unschedulable" full texts.
3. **Recommendation:** Do **not** implement the RISK-Sched method (M4) until the five High/Potentially-High
   entries are read in full and their artifacts' availability checked. Proceed with M1/M2 infrastructure
   (which is needed regardless) and run the E0/E4 go/no-go checks.
4. **Fallback narrower research questions** if the gap closes:
   - (a) *Measurement paper:* how much output-length uncertainty actually costs in tenant isolation on
     commodity GPUs (L4) under black-box vLLM, and which gateway-observable signals predict it (RQ1 alone).
   - (b) *Gateway-only vs engine-internal:* quantify what fraction of engine-internal fair/SLO schedulers'
     benefit (VTC, JITServe) is recoverable with admission/dispatch only, at what overhead.
   - (c) *Risk-budget semantics:* if FairInference gives deterministic per-token δ-isolation, study the
     goodput gained by relaxing it to a calibrated probabilistic budget — only if (2) holds.

## 4. Fair-comparison design notes

- VTC and JITServe ship their own engine forks; versions will differ from pinned vLLM v0.33.0. Any
  head-to-head must either run their pinned environments on the same GPU/model/trace (and say so) or be
  labelled "not apples-to-apples".
- Gateway-level re-implementations of VTC-like counters are a *different mechanism* and must be named
  "VTC-inspired gateway counter", never "VTC".
- Equal tuning budget for all methods; held-out test traces fixed before tuning (EXPERIMENT_PROTOCOL §6).

## 5. Security pivot (ADR-011) — prior art on resource-exhaustion attacks/defenses (V1 unless noted)

| Work | Type | What it shows | Relation to our defense |
|---|---|---|---|
| Engorgio — Dong et al., ICLR 2025. [arXiv 2412.19394](https://arxiv.org/abs/2412.19394), [ICLR](https://iclr.cc/virtual/2025/poster/28485) | Attack (T1) | Optimized prompts suppress EOS; 2–13× longer outputs, ~90%+ of length limit (white-box); service-availability experiment | Attack we must reproduce/adapt; defense must not rely on knowing the prompt is adversarial |
| OverThink — Kumar et al., 2025. [arXiv 2502.02542](https://arxiv.org/abs/2502.02542) | Attack (T2) | Decoy reasoning tasks → up to 18×/46× slowdown on reasoning models; explores LLM- and system-level defenses | Qwen3 thinking mode makes this relevant; read their system-level defenses (overlap check) |
| *Rethinking Latency DoS: Attacking the LLM Serving Framework, Not the Model*, 2026. [arXiv 2602.07878](https://arxiv.org/abs/2602.07878) | Attack (T3) | "Fill" exhausts shared KV → HOL blocking; "Squeeze" forces repeated preemption; attacker is a normal tenant, infers KV occupancy via ITL timing; assumes FCFS, shared KV pool, no per-tenant KV isolation; evaluates overprovisioning as defense | **Closest threat**; its stated assumptions (no per-tenant KV isolation) are exactly what a tenant-aware gateway can break — the core defense hypothesis. Must read in full |
| PrefixShield — *Preserving Admission Responsibility in Multi-Tenant LLM Prefix Caches*, 2026. [arXiv 2608.01657](https://arxiv.org/pdf/2608.01657) | Defense | Charges sustained KV pressure from prefix-cache pollution to the responsible tenant | Overlaps "per-tenant KV accounting"; scope is prefix cache, excludes compute-only DoS. **High** overlap risk on accounting idea — read in full |
| *Cooldown Landmines: Cross-Tenant Interference Attacks on LLM Gateways*, 2026. [arXiv 2610.05089](https://arxiv.org/pdf/2610.05089) | Attack (gateway state) | Shared LiteLLM cooldown state lets a valid tenant knock deployments out for others | Different mechanism (gateway routing state); related-work + reminder that our gateway itself is attack surface |
| OWASP LLM10:2025 Unbounded Consumption. [genai.owasp.org](https://genai.owasp.org/llmrisk/llm102025-unbounded-consumption/) | Guidance | Rate limits, quotas, input/output caps, timeouts, monitoring | Static-quota baseline family |
| Prompt Leakage via KV-Cache Sharing (NDSS 2025). [paper](https://www.ndss-symposium.org/wp-content/uploads/2025-1772-paper.pdf) | Side channel | Cross-tenant leakage via shared KV | Out of scope (confidentiality); keep prefix caching off in experiments |
| Robust KV under length uncertainty (2607.16892) | Systems | DRO KV reservation; benign traces only | Reservation component; not adversarial |

**Candidate gap (tentative):** an evaluated, engine-agnostic defense that bounds benign-tenant SLO loss and
attacker amplification for T1–T4 at fixed capacity, **robust to adaptive attackers** (T6) and with measured
false positives on legitimately heavy tenants. Overlap risks to clear first: Fill & Squeeze paper's own
defense section, PrefixShield, OverThink's system-level defenses.
