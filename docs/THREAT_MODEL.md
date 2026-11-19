# Threat Model — Resource-Exhaustion Defense for Multi-Tenant LLM Serving (draft v0.1, 2026-11-18)

Pivot recorded in `docs/DECISIONS.md` ADR-011. Infrastructure is unchanged: N virtual tenants share **one**
vLLM engine on **one** GPU behind our gateway (ECS, Terraform as proposed).

## 1. Assets
- **A-avail:** benign tenants' latency SLOs (TTFT/TPOT/E2E) and goodput on the shared engine.
- **A-wallet:** the operator's and each tenant's spend / token budget (GPU-hours ⇒ $).
- **A-capacity:** shared GPU compute and KV-cache blocks.

## 2. Adversary
- A **valid tenant** with a legitimate API key (or a small set of Sybil keys — stretch goal), sending
  well-formed requests through the normal API. No privileged access: cannot read engine internals, other
  tenants' traffic, gateway config, or credentials.
- Controls request **content** (prompts), **parameters** within API limits (`max_tokens`, sampling, thinking mode),
  and **timing**. May observe its own latencies (e.g. inter-token latency) to infer KV occupancy.
- Knows the defense algorithm (adaptive / white-box defense assumption) but not its runtime state or thresholds'
  random components.

## 3. Attacks to reproduce (only against our own deployment)
| ID | Attack | Mechanism | Prior work |
|---|---|---|---|
| T1 | Output-length inflation | Prompts that suppress EOS so outputs run to `max_tokens` | Engorgio (ICLR 2025), sponge examples (Shumailov et al. 2021) |
| T2 | Reasoning inflation | Decoy tasks that inflate (hidden) reasoning tokens; Qwen3 thinking mode | OverThink (arXiv 2502.02542) |
| T3 | KV Fill & Squeeze | Fill the shared KV pool → head-of-line blocking, then sustain repeated preemption; timing-guided | *Rethinking Latency DoS* (arXiv 2602.07878) |
| T4 | Denial-of-wallet / budget drain | Maximize billable tokens per request within quota (long prompts + max `max_tokens`) | OWASP LLM10:2025 Unbounded Consumption |
| T5 | Burst / quota-edge pacing | Stay just under rate limits; burst at window boundaries | classic rate-limit evasion |
| T6 | Adaptive attacker | Mimic a legitimate heavy tenant (e.g. agent/batch class) to evade anomaly scores | required for a credible evaluation |

Out of scope (initially): KV/prefix-cache **side channels and data leakage** (e.g. NDSS 2025 prompt leakage via KV
sharing), jailbreaks/content safety, network-layer DDoS (assumed handled by L3/L4 controls), compromised
engine/host, gateway-state attacks such as shared cooldown records (*Cooldown Landmines*, arXiv 2610.05089 —
noted as related).

## 4. Defense goals (hypotheses, to be tested)
- **G1 isolation:** benign tenants' SLO attainment under attack ≥ (1−ε) × their no-attack attainment, for
  attack intensities up to a stated bound, at fixed GPU capacity (no overprovisioning).
- **G2 bounded damage:** attacker's induced victim harm and spend are bounded by its own budget
  (amplification factor ≤ small constant), without a priori knowledge of which tenant is malicious.
- **G3 low false positives:** legitimately heavy tenants (long-decode agent/batch class) are not throttled
  below their contracted share.
- **G4 low overhead:** decision latency and throughput loss small relative to inference.

## 5. Defense mechanism under study (reuses the existing gateway)
Per-tenant **multi-dimensional budgets** — tokens, **KV-block-seconds**, and SLO-risk — enforced at admission and
dispatch; calibrated per-tenant output-length predictions; online **deviation scores** (realized vs predicted
length, KV-seconds, preemptions attributed to a tenant) that tighten a tenant's in-flight/KV allowance
progressively; reclamation of unused budget to benign tenants. All decisions use online-observable signals only
(ADR-004). Claim boundary unchanged (ADR-001): gateway admission/dispatch, not token-step scheduling.

## 6. Metrics
benign-tenant SLO attainment and goodput (attack vs no-attack, paired traces); worst benign tenant;
**amplification factor** = victim goodput loss (or victim GPU-seconds lost) per attacker token/$;
attacker cost to achieve a given degradation; detection/mitigation latency; false-positive throttling of
benign heavy tenants; defense overhead; total GPU utilization.

## 7. Ethics / safety of the research
Attacks run only against infrastructure we own, with synthetic tenants; no third-party services are probed.
Attack prompt corpora are not released in a form that is directly weaponizable against public APIs without
review; follow responsible-disclosure norms if a vLLM-specific vulnerability is found.
