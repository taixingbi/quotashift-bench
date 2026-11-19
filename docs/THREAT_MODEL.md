# Threat / attacker-capability model — QuotaShift (v1, 2026-11-19)

QuotaShift characterizes *attacker capability*, not a defense. N synthetic tenants share **one** vLLM engine on
**one** GPU behind our internal gateway, in an owned, isolated VPC. We study whether a competing tenant's workload
*shape and timing* degrades victim tenants' service **under identical, authorized budgets**.

## Assets (victim side)
- **A-latency:** victim tenants' TTFT / end-to-end latency and goodput on the shared engine.
- **A-capacity:** shared GPU compute and KV-cache blocks.

## Adversary
- A **valid synthetic tenant** with an experiment-owned key, sending well-formed requests through the normal gateway
  API. No privileged access: cannot read engine internals, other tenants' traffic, gateway config, or credentials.
- Controls request **shape** (prompt length, requested `max_tokens`) and **timing** within the fixed authorized
  budget. Does **not** use malicious prompt content; prompts are deterministic benign templates.
- Capability is bounded by the scenario `safety` block (per-tenant/total requests, per-request input/output,
  in-flight, runtime). The attacker never exceeds the same budget the victim could use.

## Workload hypotheses (tested, not assumed)
- **H1 (shape):** request-shape composition changes victim impact even when attacker request/token budgets match.
- **H2 (timing):** temporal sequence/burstiness matters beyond the same shuffled mixture.
- **H3 (robustness):** effects persist across seeds, victim profiles, and repeated runs.

## Scenario families (attack side; all in-lab, bounded)
| ID | Scenario | Shape / pattern (QuotaShift) | Matched control |
|----|----------|------------------------------|-----------------|
| B0 | Benign-only baseline | victims only, steady | reference |
| A1 | Burst-shaped arrivals | `burst_bounded`, fixed totals | same totals spread `steady` |
| A2 | Prefill-heavy | `context_heavy` (long input, short output) | token-matched, shorter inputs |
| A3 | Decode-heavy | `decode_heavy` (short input, long output) | token-matched, shorter outputs |
| A4 | Mixed shapes | `mixed` proportions | equal-size homogeneous workload |
| A5 | Stateful sequence | ordered phases (`stateful_sequences.yaml`) | shuffled-phase order, same mixture |

## Explicitly out of scope
- No defenses, no scheduler, no RL. No external targets, third-party APIs, or production tenants.
- No KV/prefix-cache side channels or prompt/data leakage. No quota-bypass or detection-evasion logic.
- No unbounded flooding: every scenario fails closed if its caps cannot be enforced.

## Reporting discipline
A pre-registered degradation threshold (`comparison.preregistered_threshold`) is fixed before runs. Routine
overload is not reported as a novel finding without evidence of *cross-tenant disparity* under matched budgets.
Negative results (effects vanish when budgets are matched) are reported as such.
