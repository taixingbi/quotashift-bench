# Metric Definitions

Implemented in `src/quotashift/evaluation/metrics.py`; tested in `tests/unit/test_metrics.py`.
All per-request times are on the runner's single clock (monotonic in live runs, virtual in simulation).

## Per request
| Symbol | Definition |
|---|---|
| `t_offered` | time the client hands the request to the gateway (≈ trace arrival in open loop) |
| `gateway_queue_ms` | `t_sent − t_offered` (gateway waiting only) |
| `ttft_ms` | `t_first_token − t_offered` — **user-facing**, includes gateway queue |
| `backend_ttft_ms` | `t_first_token − t_sent` — vLLM internal waiting + prefill + network; *not* separable further from the client side. vLLM's own `request_queue_time_seconds` / `request_prefill_time_seconds` histograms are scraped for the engine-internal split when available. |
| `e2e_ms` | `t_terminal − t_offered` for completed requests |
| `tpot_ms` | `(t_terminal − t_first_token) / (n_out − 1)` for `n_out > 1`; undefined otherwise (TPOT bound treated as vacuous for 1-token outputs) |
| ITL | gaps between consecutive streamed chunks; `max_itl_s` recorded. A chunk may carry >1 token, so chunk ITL ≠ per-token ITL; vLLM's `inter_token_latency_seconds` histogram is the engine-side source. |
| `output_tokens` | realized generated tokens from `usage.completion_tokens` (`output_tokens_source=usage`); fallback `chunks_lower_bound` is flagged |
| `max_output_tokens` | **requested** cap; never used as realized usage |

## SLO compliance
`slo_met = completed ∧ ttft_ms ≤ ttft_deadline_ms ∧ (tpot_target unset ∨ tpot undefined ∨ tpot_ms ≤ tpot_target_ms) ∧ (e2e_deadline unset ∨ e2e_ms ≤ e2e_deadline_ms)`.
Rejected, timed-out, backend-error and cancelled requests are never SLO-compliant.

## Run-level (window = trace arrivals in `[warmup_s, duration_s)`)
| Metric | Definition |
|---|---|
| **SLO goodput (primary)** | `#slo_met / window_s` (requests/s) |
| offered-load success fraction | `#slo_met / #offered` — denominator includes **all** offered requests |
| accounting conservation | `#offered = #completed + #rejected + #timed_out + #backend_error + #cancelled`, no non-terminal rows |
| per-tenant SLO attainment `s_i` | `#slo_met_i / #offered_i` |
| worst-tenant attainment | `min_i s_i` |
| Jain fairness (normalized) | `J = (Σ s_i)² / (n Σ s_i²)` over SLO attainment `s_i ∈ [0,1]` — comparable across heterogeneous tenants (not raw throughput) |
| weighted tenant goodput | `Σ_i (w_i / Σw) · goodput_i` |
| service tokens | `Σ (input + realized output)` of completed requests per tenant (for weighted-service fairness analyses) |
| output tokens/s | realized output tokens of completed requests / window — exposes policies that win request-count by serving only cheap work |
| warm-up exclusions | counted and reported (`excluded_outside_window`), never silent |

Planned for M2 (definitions fixed now): **non-starvation** — under a feasible load (offered ≤ calibrated
capacity), every tenant with a non-empty queue receives a dispatch within a bounded interval;
**weighted fairness** — among continuously backlogged tenants, normalized service `service_i / w_i` differences
stay bounded over any interval; **work conservation** — the gateway never holds a request while the engine has
spare admitted capacity under the policy's own budget (measured as idle-with-queue time).

## Percentiles
Request percentiles: numpy `linear` interpolation over completed requests, with `n` reported. Prometheus
histogram quantiles: `histogram_quantile` semantics (linear within bucket; lower bound 0; +Inf bucket ⇒ highest
finite bound). Run-level uncertainty in M2+: bootstrap 95% CIs over **independent runs/traces**, never treating
requests as independent units.

## E0-specific
- `completed_rps` (rate sweep): completions with `t_terminal ≤ window end` / window — achieved throughput.
- `completed_eventually_rps`: all completions incl. drain / window — *not* a throughput measure past saturation.
- Knee (provisional): highest offered rate with mean `completed_rps ≥ 0.95 × offered` and mean P95 TTFT ≤ threshold.
- Cell throughput: `Σ output tokens / (last completion − first offer)` in a closed-loop cell.
