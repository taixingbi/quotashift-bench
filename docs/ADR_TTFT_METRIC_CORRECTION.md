# ADR-Q16 / ADR-Q17 — TTFT definitions, metric-labelled reports, and fail-closed validity gates

Status: **accepted 2026-11-21** (owner decision after the Suite S forensic audit,
`reports/v3/SUITE_S_FORENSIC_AUDIT.md`). Written and committed **before** any protocol v3.1 run.

## Context

The Suite S audit found three analysis defects:

1. **TTFT definition mismatch.** `evaluation/attack_effect.run_metrics` has computed victim `ttft_ms` as
   `t_first_token − t_sent` since Phase 5 (commit 4a829d7, 2026-11-19). That is backend TTFT, and it excludes the
   gateway queue. `docs/METRIC_DEFINITIONS.md` and `evaluation/metrics.py` define `ttft_ms` as `t_first_token − t_offered`,
   which is user-facing and includes the gateway queue. Every pre-registered "victim TTFT P95" result for A1–A9 was
   therefore computed as backend TTFT. Where the gateway queue dominates, that hides most of the victim's wait: A8 control
   victims have gateway-queue P95 of 1.7–9.5 s, and A9 token-matched controls 50–52 s.
2. **Report labels.** `write_report` printed every metric as "Mean victim slowdown ratio", with per-seed columns
   headed "attack ms / control ms". For A9 the value is GPU dynamic energy per 1,000 authorized tokens, so the label
   was wrong, although the values were correct.
3. **No validity gates.** A block whose competitor was 97% rejected with HTTP 400 still received a classification.
   Latency ratios silently dropped timed-out victims, which is censoring.

## Decision (ADR-Q16): definitions

| Name | Definition | Population |
|---|---|---|
| **User-facing TTFT** | `t_first_token − t_offered` | completed victim requests |
| **Backend TTFT** | `t_first_token − t_sent` (backend dispatch) | completed victim requests |
| **Gateway queue time** | `t_sent − t_offered` | victim requests that were dispatched |
| **Offered-load SLO success** | #victims completed within their user-facing TTFT, TPOT and E2E SLO ÷ #victims **offered** | all offered victims (timeouts, rejections and errors count as failures) |

- New explicit metric keys are `user_ttft_p95`, `backend_ttft_p95`, `gateway_queue_p95` and `victim_slo_success_offered`.
- **The historical key `ttft_p95` keeps its computed meaning (backend TTFT).** Every pre-registered A1–A9 value,
  ratio, CI and classification therefore reproduces exactly and remains the historical result. Reports now name it
  "Victim backend TTFT P95 (historical `ttft_p95`)".
- **A new scenario pre-registers an explicit key.** `ttft_p95` stays valid only for reproducing historical series.
- **Reanalysis.** Existing A1–A9 runs are reanalysed offline with both definitions by `scripts/reanalyze_suite.py`. The
  user-facing results are labelled **post-hoc correction (not pre-registered)**. They never replace the historical
  classification, and both are shown side by side.
- **Victim outcomes in every report.** Each report lists offered, completed, rejected, timed-out, backend-error and
  cancelled victims per arm and seed, together with offered-load SLO success. A congested arm cannot look fast by
  losing its slow requests, because SLO success counts every offered request.
- **Labels.** Every report heading, table header, figure axis and verdict is generated from a per-metric `MetricInfo`
  (label, unit, kind, definition). `check_report_labels` refuses to write a report whose text disagrees with its
  metric. The A9 primary is labelled "GPU Dynamic Energy per 1,000 Authorized Tokens" (unit: J per 1,000 authorized
  tokens), and its verdict says it is a cost-per-unit difference, not a victim-performance effect.

## Decision (ADR-Q17): fail-closed validity gates

These are applied by `quotashift experiment` to every new experiment (`evaluation/validity.py`). If any fail-severity
gate fails, or is unavailable, the classification becomes `invalid`, the computed label is kept as
`classification_unvalidated`, and the CLI exits 5. The pre-run tokenized-context check refuses with exit 3 before
anything is sent. These are validity thresholds, not effect thresholds. They are fixed here, before the runs they
govern, and are never tuned on results.

| Gate | Rule | Severity |
|---|---|---|
| `backend_error_rate` | backend errors / requests sent ≤ **0.01** in every arm | fail |
| `http_400_rate` | HTTP 400 / requests sent ≤ **0.01** in every arm | fail |
| `admission_rate` | admitted / offered ≥ **0.95** for victims and competitor in every arm | fail |
| `competitor_completion` | (completed + client-designed cancels/timeouts) / offered ≥ **0.95** in every arm | fail |
| `primary_metric_present` | the primary metric is finite for every paired seed | fail |
| `tokenized_context` | pre-run: every request in both arms is tokenized by the live model tokenizer, and prompt tokens + `max_output_tokens` ≤ `max_model_len`; post-run: max completed prompt + max_output ≤ `max_model_len` | fail |
| `planned_vs_reported_tokens` | for `prompt_token_unit: tokenizer` scenarios, engine-reported `prompt_tokens` = planned `input_token_count` for every completed request | fail |
| `provenance` | one clean git SHA, one server start, vLLM version, and an explicit model-revision status recorded | fail |
| `victim_latency_censoring` | (offered − completed) / offered victims ≤ **0.05** in every arm | fail when the primary is a victim-latency metric; flag otherwise |
| report labels | `check_report_labels` | fail (raises) |

Historical reports are **not** re-labelled by these gates. The reanalysis only reports them, and gates that
historical runs cannot satisfy are marked unavailable (for example, no pre-run tokenization was recorded).

## Consequences

- A1–A5 and A7–A9 historical results are unchanged and reproducible. The post-hoc user-facing results sit beside them.
- Which TTFT a future series uses is a pre-registration choice that names the key explicitly.
- The model revision is recorded as the server reports it (`/server_info` → `revision=None` on this target), next to
  the documented value. It is never inferred.
