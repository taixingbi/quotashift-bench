"""Render reports/v3/SUITE_S_FORENSIC_AUDIT.md from the read-only audit CSVs (no hand-copied numbers in tables)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from quotashift.evaluation.attack_effect import bootstrap_ci, classify

S = Path(sys.argv[1])
OUT = Path(sys.argv[2])
r = pd.read_csv(S / "per_arm.csv")
e = pd.read_csv(S / "endpoints_per_seed.csv")
cov = pd.read_csv(S / "coverage.csv")
tid = pd.read_csv(S / "trace_identity.csv")
BLOCKS = list(r.block.unique())
A9 = [b for b in BLOCKS if b.startswith("a9")]


def f(x, n=1):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{n}f}"


def ci_row(vals):
    lo, hi = bootstrap_ci(list(vals))
    return np.mean(vals), lo, hi, classify((lo, hi), 1.25, "two_sided")


def table(df, cols, hdr=None):
    hdr = hdr or cols
    out = ["| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
    for _, x in df.iterrows():
        out.append("| " + " | ".join(str(x[c]) for c in cols) + " |")
    return "\n".join(out)


md = []
A = md.append

A("""# Suite S forensic audit (A7–A9, protocol v3)

Read-only audit, 2026-11-21 20:39–20:48 EST. No GPU runs were made, no data was overwritten, and the pre-registered protocol,
thresholds and classifications were not changed. Every number in the tables below comes from `results/<block>__{attack,control}/*/`
(`requests.parquet`, `trace.jsonl`, `metrics_timeseries.parquet`, `metrics_summary.json`, `manifest.json`) and
`reports/v3/<block>/{manifest.json,summary.md}`. The audit scripts are in the session scratchpad (`audit.py`, `write_audit.py`), and their
CSV outputs (`per_arm.csv`, `endpoints_per_seed.csv`, `coverage.csv`, `trace_identity.csv`, `provenance.csv`,
`report_vs_recomputed.csv`) are copied to `reports/v3/suite_s_audit/`.

## 0. Conclusions

1. **A9 "low victim TTFT ratios" (0.18–0.62): the cause is a report labelling defect, not a measurement.** For A9 the
   pre-registered `degradation_metric` is `gpu_energy_per_1k_authorized_tokens`, and the reported ratios are exactly that
   primary endpoint. `write_report` prints it under the fixed label "Mean victim slowdown ratio", with per-seed columns
   headed "attack ms / control ms". Those columns are actually J per 1k authorized tokens. Recomputed from raw files, all 60 per-seed ratios
   (A7–A9) match the reports to within rounding (max |Δratio| = 0.005). No arm is reversed and no denominator is wrong. My earlier progress messages that called these
   "victim speed-ups" were wrong. The actual secondary victim TTFT results are in §2.4. For example, `a9_rate_prefill` victim backend
   TTFT P95 is **3.44× the control** (a slowdown), not 0.29×.
2. **Why the A9 rate-matched energy ratios are low: real and mechanical.** Dynamic GPU energy per arm is nearly constant
   (27.0–37.3 kJ, mean board power 261–317 W) because the GPU runs near full power whenever any request is in flight.
   Rate-matched attack arms authorize 1.7–6.7× more tokens than their short control (decode 1.7×, prefill and prefix-reuse 3.3–3.8×,
   long context 4.4–6.7×), so J per 1k authorized tokens falls by about the same factor. This is a measured property of this GPU at this load, with no sign of an accounting error. It is still mostly a
   denominator effect, and it should be reported that way.
3. **Long-context coverage = 0.0: the 0.0 came from my own check script, but it exposed a real defect.** In `a9_{tok,rate}_longctx`, the
   attack-arm competitor completed **4 of 116** requests. The other **112 failed with HTTP 400** ("You passed 3841 input tokens
   ... maximum input length of 3840 tokens"). In seeds 42 and 46 the competitor tenant completed 0 requests, so the harness
   correctly records its coverage as `null` (empty denominator). My `suite_check.py` turned that `null` into 0 with `or 0`. All
   29,975 completed requests in Suite S report a numeric `cached_tokens`, with 0 nulls. All 1,648 non-completed requests have `null`, kept as missing.
4. **Root cause of the long-context failure: the planned token unit is whitespace words, not tokenizer tokens.** Realized prompt tokens per
   planned word are 2.03–2.14 for the pseudo-word filler and 1.21–1.36 for the single-token prefix vocabulary. The long-context family
   plans 1,136–3,584 words (3,584 is the cap), which is about 2,300–7,300 real tokens, against a 3,840-token input limit. The schema safety
   check (`scenario.py:284`) compares planned words with `model_max_len`, so it passed. No long-context smoke was run.
   **Both long-context blocks are invalid: the manipulation failed** (the competitor workload was never served).
5. **TTFT definition discrepancy (affects all A1–A9 TTFT endpoints).** `attack_effect.run_metrics` computes `ttft_ms =
   t_first_token − t_sent` (backend TTFT, excluding gateway queueing; `attack_effect.py:98-100`, since commit 4a829d7, Phase 5).
   `docs/METRIC_DEFINITIONS.md:11` and `evaluation/metrics.py:37` define `ttft_ms = t_first_token − t_offered`
   (user-facing, including the gateway queue). The pre-registered "victim TTFT P95" has always been computed as backend TTFT.
   This matters a lot where the gateway queue dominates. Examples: A8 control-arm victims wait 1.7–9.5 s at P95 in the gateway, and A9 token-matched controls 50–52 s.
   The pre-registered labels for A7 and A8 do not change under the other definition (§2.5), but A9's secondary TTFT does.
6. **Token-matched A9 victims are censored.** In `a9_tok_{prefill,longctx,prefix_reuse}` controls, victims hit the
   gateway's 60 s queue timeout (12, 36 and 13 requests over 5 seeds; seeds 44–46 only). Timed-out requests are excluded from TTFT,
   so the control-arm TTFT is survivor-biased toward faster requests.
7. **Other integrity checks are clean.** One server start (1795268683.89) and no restarts. Engine reconciliation residual is 0 in all 120 runs, with no
   unrelated traffic, no leaks and request accounting conserved. Victim workloads are identical across arms up to the designed per-arm salt.
   Competitor arrival schedules are identical in every rate-matched block. The GPU idle baseline and tail settled in every arm, with
   166–206 power samples per arm and a maximum gap of 2.0 s.
8. **GPU reruns:** needed only for the two long-context blocks, after a scenario fix that changes the protocol and needs approval and
   a fresh pre-registration (§7). Every other correction is analysis-side and can be recomputed from the existing data.
""")

# ---------------- P0-1 ----------------
A("## 1. Evidence: A9 metric mapping\n")
A("""- `experiments/v3/a9_*.yaml`: `comparison.degradation_metric: gpu_energy_per_1k_authorized_tokens` (all 8 files).
  A7/A8: `ttft_p95`.
- `src/quotashift/evaluation/attack_effect.py:163-173` `_metric_value`: for this metric, returns
  `gpu_dynamic_energy_j / (authorized_tokens / 1000)`. `analyze_pair` (`:198-251`) takes ratio = attack / control per seed.
- `attack_effect.py:284` prints `"Mean victim slowdown ratio"`, and `:296` prints the per-seed table header
  `"| seed | attack ms | control ms | ratio |"` whatever the metric. The figure's y-label (`:415`) is
  "victim slowdown ratio" too. **Labelling defect only; values are correct.**
- `authorized_tokens` (`runtime/runner.py:283`) = Σ over **all** requests in the arm, victims included, of
  `input_token_count + max_output_tokens`, in planned (whitespace-word) units, per ADR-Q10 ("budgets compared are
  planned/requested quantities"). `gpu_dynamic_energy_j` (`instrumentation/engine_counters.py:148-156`) is a trapezoid
  integral of board power over the arm's scrape window, minus pre-arm idle power × span.
- Report vs recomputed: `suite_s_audit/report_vs_recomputed.csv`, 60 seed pairs, max |Δratio| 0.0049 (2-decimal rounding
  in `summary.md`).
- Trace checks (`trace_identity.csv`): victim requests in every block have identical `request_id`, tenant, arrival time,
  `input_token_count`, `max_output_tokens`, deadlines and SLO class across arms. Their prompt text differs only in the designed
  per-arm salt (4 nonce words, `workload/isolation.py`; A7: the 192-word arm-salted tenant prefix, `workload/prefix_cache.py:37-58`).
  `rate_matched_short` keeps the competitor request count and the arrival times exactly the same in all 20 rate-matched seed pairs
  (`comp_arrivals_identical = True`) and changes the shape to (64 in / 64 out), as designed
  (`scenario.py:61`). Admission policy (FCFS), rate limits (none), queue caps (`max_queue_wait_s = 60`), backend URL,
  vLLM 0.17.1, and cache config (`gpu_memory_utilization` 0.8, 4662 blocks, prefix caching on) are identical in every
  run manifest.
""")

# ---------------- per-seed A9 primary ----------------
A("## 2. Per-seed metrics\n")
A("### 2.1 A9 primary endpoint: GPU dynamic energy per 1k authorized tokens (arm window)\n")
x = e[e.block.isin(A9)].copy()
x["e_a"] = x.e_a.map(lambda v: f(v, 1)); x["e_c"] = x.e_c.map(lambda v: f(v, 1)); x["ratio"] = x.e_ratio.map(lambda v: f(v, 3))
x["dyn_a"] = x.dyn_a.map(lambda v: f(v / 1000, 2)); x["dyn_c"] = x.dyn_c.map(lambda v: f(v / 1000, 2))
x["real_a"] = x.real_a.astype(int); x["real_c"] = x.real_c.astype(int)
A(table(x, ["block", "seed", "dyn_a", "dyn_c", "auth_a", "auth_c", "real_a", "real_c", "e_a", "e_c", "ratio"],
        ["block", "seed", "dyn. energy A (kJ)", "dyn. energy C (kJ)", "authorized tok A", "authorized tok C",
         "realized tok A", "realized tok C", "J/1k auth A", "J/1k auth C", "ratio A/C"]))
A("\nAuthorized = planned `input_token_count + max_output_tokens` over all requests (victims included). Realized = Σ "
  "`prompt_tokens_reported + output_tokens` over completed requests (engine tokenizer).\n")

A("### 2.2 Victim request outcomes per arm (all blocks, mean of 5 seeds)\n")
g = r.groupby(["block", "arm"], sort=False)[["v_offered", "v_admitted", "v_sent", "v_completed", "v_timed_out", "v_rejected",
                                            "v_cancelled", "v_other", "v_pending"]].mean().reset_index()
for c in g.columns[2:]:
    g[c] = g[c].map(lambda v: f(v, 1))
A(table(g, list(g.columns), ["block", "arm", "offered", "admitted", "sent to vLLM", "completed", "timed out", "rejected",
                             "cancelled", "other", "pending"]))
A("\nAll victim timeouts are `terminal_detail = gateway_queue_timeout` with `t_sent = null`: they never reached vLLM. "
  "There were no rejections and no pending (non-terminal) requests. No non-completed victim has a first token, so excluding them from TTFT drops "
  "no partial TTFT observations, but it does drop the slowest requests (censoring).\n")
tt = r[r.block.str.startswith("a9_tok") & (r.arm == "control")].groupby("block", sort=False).v_timed_out.apply(lambda s: ", ".join(map(str, s)))
A("Victim gateway-queue timeouts by seed (42..46), token-matched controls: " + "; ".join(f"`{k}` {v}" for k, v in tt.items()) + ". "
  "Attack arms: 0 in every block.\n")

A("### 2.3 Victim latency per seed (ms; backend TTFT = `t_first_token − t_sent`, completed victims, as analysed)\n")
y = e.copy()
for c in ("ttft_a50", "ttft_c50", "ttft_a95", "ttft_c95", "ttft_a99", "ttft_c99"):
    y[c] = y[c].map(lambda v: f(v, 1))
y["ratio95"] = e.ttft_ratio.map(lambda v: f(v, 3))
A(table(y, ["block", "seed", "ttft_a50", "ttft_c50", "ttft_a95", "ttft_c95", "ttft_a99", "ttft_c99", "ratio95", "vto_a", "vto_c"],
        ["block", "seed", "P50 A", "P50 C", "P95 A", "P95 C", "P99 A", "P99 C", "P95 ratio A/C", "victim timeouts A", "victim timeouts C"]))

A("\n### 2.4 Mechanism and pressure per arm (mean of 5 seeds)\n")
m = r.groupby(["block", "arm"], sort=False).agg(
    gwq95=("v_gwq_p95", "mean"), cttft95=("v_client_ttft_p95", "mean"), run=("running_mean", "mean"), runmax=("running_max", "mean"),
    wait=("waiting_max", "mean"), kv=("kv_max", "mean"), infl=("gw_inflight_max", "mean"), pw=("power_mean", "mean"),
    dyn=("dyn_j", "mean"), svc=("svc_s", "mean"), busy=("engine_busy_s", "mean"), ep=("eng_prompt", "mean"), eg=("eng_gen", "mean"),
    hit=("hit_ratio", "mean"), c_off=("c_offered", "mean"), c_done=("c_completed", "mean")).reset_index()
fmt = {"gwq95": 0, "cttft95": 0, "run": 2, "runmax": 1, "wait": 1, "kv": 3, "infl": 1, "pw": 0, "dyn": 0, "svc": 0, "busy": 0, "ep": 0,
       "eg": 0, "hit": 3, "c_off": 1, "c_done": 1}
for c, n in fmt.items():
    m[c] = m[c].map(lambda v, n=n: f(v, n))
A(table(m, ["block", "arm", "c_off", "c_done", "gwq95", "cttft95", "run", "runmax", "wait", "kv", "infl", "pw", "dyn", "svc", "busy", "ep", "eg", "hit"],
        ["block", "arm", "comp offered", "comp completed", "victim gw-queue P95 ms", "victim user TTFT P95 ms", "running mean",
         "running max", "waiting max", "KV max", "gw inflight max", "GPU W mean", "dyn. energy J", "engine prefill+decode s",
         "engine busy s", "engine prompt tok", "engine gen tok", "prefix hit ratio"]))
A("\nGateway inflight is capped at `max_global_inflight: 8`. When the competitor floods it (the token-matched short controls send "
  "about 560–630 competitor requests, against 23–123 in the attack arm), victims wait in the FCFS gateway queue, not in vLLM. vLLM `waiting` stays at about 0 throughout.\n")

A("### 2.5 Block-level endpoints: pre-registered (unchanged) and sensitivity (not pre-registered)\n")
rows = []
for b in BLOCKS:
    gg = e[e.block == b]
    def c(col):
        mn, lo, hi, cl = ci_row(gg[col])
        return f"{mn:.2f} [{lo:.2f}, {hi:.2f}] {cl}"
    rows.append(dict(block=b, primary=("energy/1k auth: " + c("e_ratio")) if b in A9 else ("backend TTFT P95: " + c("ttft_ratio")),
                     ttft_backend=c("ttft_ratio"), ttft_user=c("client_ttft_ratio"), e_tail=c("etail_ratio"), e_real=c("ereal_ratio"),
                     svc=c("svc_ratio")))
t5 = pd.DataFrame(rows)
A(table(t5, ["block", "primary", "ttft_backend", "ttft_user", "e_tail", "e_real", "svc"],
        ["block", "pre-registered primary (as reported)", "victim backend-TTFT P95 ratio", "victim user-facing TTFT P95 ratio",
         "energy-with-tail /1k auth", "energy /1k realized tok", "engine service s /1k auth"]))
A("\nMean ratio [95% percentile bootstrap CI, 10,000 resamples, seed 0, same function as the pipeline] and the two-sided 1.25 "
  "classification applied mechanically. A8 is pre-registered one-sided (`increase`), so its primary label is `negative`, as "
  "reported. Only the \"pre-registered primary\" column carries a claim. The other columns are diagnostics for this audit and are "
  "not re-classifications.\n")

# ---------------- coverage ----------------
A("## 3. Long-context coverage = 0.0\n")
A("""- **What 0.0 was:** a `null` turned into 0 in my own post-run script
  (`scratchpad/suite_check.py`, `min((v.get("coverage") or 0) ...)`). The harness's own `cached_token_summary`
  (`evaluation/cache_hits.py:24-41`) returns `coverage: None` for a tenant with 0 completed requests (an empty denominator) and does not
  impute anything. Nothing in `results/` or `reports/` contains 0.0 coverage.
- **Why the denominator was empty:** the competitor's long-context requests failed with HTTP 400 (context length). See the table
  below and §0.4.
- **0 vs null vs unavailable** (raw `requests.parquet`, all 120 runs; `coverage.csv` has tenant × status × arm × seed):
""")
raw = cov[cov.status != "__summary__"]
k = raw.assign(done=raw.status == "completed").groupby("status").agg(n=("n", "sum"), null=("ct_null", "sum"), zero=("ct_zero", "sum"),
                                                                     pos=("ct_pos", "sum")).reset_index()
for c in ("n", "null", "zero", "pos"):
    k[c] = k[c].astype(int)
A(table(k, ["status", "n", "zero", "pos", "null"], ["terminal status", "requests", "cached_tokens = 0", "cached_tokens > 0", "cached_tokens = null"]))
A("\n  Completed requests: numeric `cached_tokens` in every row (0 is an observed zero-hit, which the owner's §7a server patch reports on both "
  "endpoints). Non-completed requests: always `null` (no usage block), kept as missing and excluded from the ratio, as documented.\n")
sm = cov[(cov.status == "__summary__") & cov.block.str.contains("longctx")]
pv = sm.pivot_table(index=["block", "arm", "seed"], columns="tenant", values="summary_coverage", aggfunc="first", dropna=False).reset_index()
nn = sm[sm.tenant == "comp"].set_index(["block", "arm", "seed"])[["n", "summary_noncompleted"]]
pv = pv.join(nn, on=["block", "arm", "seed"])
for c in ("comp", "v00", "v01", "v02"):
    pv[c] = pv[c].map(lambda v: "null" if not np.isfinite(v) else f"{v:.1f}")
pv["n"] = pv["n"].astype(int); pv["summary_noncompleted"] = pv["summary_noncompleted"].astype(int)
A("\nCoverage by tenant, arm and seed, as stored in `metrics_summary.json` (long-context blocks):\n")
A(table(pv, ["block", "arm", "seed", "comp", "n", "summary_noncompleted", "v00", "v01", "v02"],
        ["block", "arm", "seed", "comp coverage", "comp completed", "comp non-completed", "v00", "v01", "v02"]))
A("""
- **Engine reconciliation:** residual = Δ`prefix_cache_hits_total` − Σ per-request `cached_tokens` = **0 in every run**.
  Attribution is `exact` where every request completed and `bounded` where some did not (A8, long-context attack arms).
  Engine hit ratio is 0.000 in every long-context arm.
- **Censoring and timeouts:** the competitor's HTTP 400 errors are fast failures, so the attack arm effectively ran victims alone (engine running
  mean 1.25 vs 7.2 in the token-matched control). Victims never timed out in long-context attack arms. They did time out in the token-matched long-context control
  (36 over 5 seeds, gateway queue, §2.2).
""")

# ---------------- energy ----------------
A("## 4. Energy metric audit (A9)\n")
a9r = r[r.block.isin(A9)]
A(f"""- **Power coverage:** {a9r.power_samples.min()}–{a9r.power_samples.max()} board-power samples per arm (exporter :9835, about 0.65 s
  scrape), max gap {a9r.max_gap_s.max():.2f} s, window span {a9r.ts_span_s.min():.1f}–{a9r.ts_span_s.max():.1f} s. Pre-arm idle settled in
  120/120 runs ({a9r.idle_w.min():.1f}–{a9r.idle_w.max():.1f} W in A9). The post-arm tail settled in 120/120.
- **Idle subtraction:** dynamic = ∫P dt − P_idle × span (`engine_counters.py:148-156`). P_idle is the median of the settled
  pre-arm samples (SM ≤ 500 MHz, util 0, spread ≤ 15 W).
- **Arm-window vs with-tail:** the with-tail ratio agrees with the arm-window ratio within 0.02 in every A9 block, with no change in
  direction or classification (§2.5).
- **Denominator:** pre-registered "authorized tokens" = planned `input_token_count + max_output_tokens`, victims included.
  Planned input is in whitespace words: realized/planned prompt tokens are 2.03–2.14 (pseudo-word filler) and 1.21
  (single-token prefix vocabulary, A7 / `prefix_reuse` competitor). So token-matched (`a9_tok_*`) arms are matched in planned
  units only. In realized tokens they differ: for seed 42, prefill 145,115 vs 117,517; decode 58,989 vs 71,841; prefix reuse 95,576
  vs 117,517; long context 20,156 vs 101,172.
- **Absolute energy is nearly flat:** {a9r.dyn_j.min()/1000:.1f}–{a9r.dyn_j.max()/1000:.1f} kJ per arm, mean board power
  {a9r.power_mean.min():.0f}–{a9r.power_mean.max():.0f} W, against about 34 W idle. With identical victims (about 0.9 rps) the GPU is near peak power
  for the whole window in every arm, so dynamic energy hardly tracks the competitor's token volume. Per 1k tokens, the result is set
  by the denominator. Board power also includes the victims' work (a documented confounder).
""")
A("### 4.1 A9 primary (H9) classification, as pre-registered (unchanged), and validity\n")
v = []
for b in A9:
    gg = e[e.block == b]; mn, lo, hi, cl = ci_row(gg.e_ratio)
    status = ("INVALID: manipulation failed (112/116 competitor requests HTTP 400)" if "longctx" in b else
              "valid as computed; matched in planned (word) units only, realized tokens differ" if b.startswith("a9_tok") else
              "valid as computed; denominator-dominated by design (authorized tokens differ 1.7–3.8×)")
    v.append(dict(block=b, ratio=f"{mn:.3f}", ci=f"[{lo:.3f}, {hi:.3f}]", cls=cl, status=status))
A(table(pd.DataFrame(v), ["block", "ratio", "ci", "cls", "status"], ["block", "mean ratio", "95% CI", "pre-registered classification", "audit status"]))
A("""
Valid series: token-matched prefill, decode and prefix-reuse are **negative** for H9 (CI inside (0.8, 1.25)). Rate-matched prefill,
decode and prefix-reuse are **supported** (CI ≤ 0.8). In the rate-matched series that means energy per authorized token is lower for the heavy
family, mainly because arm energy stays nearly constant while authorized tokens rise 1.7–3.8×. Both long-context results (token-matched `inconclusive`,
rate-matched `supported`) are **invalid** and should be reported as such, not interpreted.
""")

# ---------------- provenance ----------------
p = pd.read_csv(S / "provenance.csv")
A("## 5. Provenance (from the 120 run manifests and 12 report manifests)\n")
A(f"""- **Commit:** `{p.git_sha.unique()[0]}` in all 120 runs. **Dirty:** `{p.git_dirty.unique().tolist()}`, meaning dirty in all runs. The only
  uncommitted change was `experiments/PLAN.md`, the S0 result note, later committed as 856fc07. The run manifests do not list
  dirty files, so this comes from the session record, not from the manifest.
- **Arm identity:** run `experiment_id` = `<block>__attack|__control` in 120/120 runs. Report `run_dirs` map every
  seed to one attack and one control run.
- **Arm order:** counterbalanced: even seeds attack→control, odd seeds control→attack (`arm_order` in the report manifests).
  It matches the run start timestamps in 60/60 pairs.
- **Hashes:** `config_sha256` is constant within each block×arm. `trace_sha256` is distinct per seed (5 per block×arm), and no trace hash is shared
  across blocks.
- **Backend:** `base_url` http://192.168.86.173:8000, vLLM `{p.vllm.unique()[0]}`. Server start from
  `engine_state_at_start.process_start_time_seconds` = `{p.server_start.unique()[0]:.2f}` in all 120 runs.
- **Missing fields:** `run_context.backend_identity.model_revision = null` (not reported by the server). Per-run manifests
  contain no `server_start` key (it lives in `metrics_summary.json → engine_counters.engine_state_at_start`), no arm-order field
  (that is only in the report manifest), and no list of dirty files. Report manifests have no `git` block (the summary I gave earlier said "dirty: None" because
  the field is missing, not because the tree was clean). The pre-block hygiene reset is recorded in
  `reports/v3/<block>/prerun_cache_reset.json`, not in any manifest.
""")

# ---------------- validity ----------------
A("## 6. Validity status per block\n")
val = [
    ("a7_prefix_cache (S1)", "ttft_p95, two-sided", "0.61 [0.56, 0.66] supported", "valid; **exploratory** by design (no per-arm reset). Manipulation check passed (hit ratio 0.596 vs 0.191, Δ 0.41 ≥ 0.1). Direction: victim faster when the competitor reuses its prefix. User-facing TTFT agrees (0.56)."),
    ("a7_prefix_cache_reset (S1′)", "ttft_p95, two-sided", "0.62 [0.57, 0.67] supported", "valid, **confirmatory** (per-arm verified reset). Same manipulation check and direction."),
    ("a8_lifecycle_churn", "ttft_p95, increase", "0.98 [0.87, 1.06] negative", "valid as computed. Note: backend TTFT excludes the gateway queue. Victims in the control wait much longer in the gateway (P95 1.7 s vs 0.04 s), because attack-arm cancellations free inflight slots. One-sided label is unchanged under either definition."),
    ("a8_retry_churn", "ttft_p95, increase", "1.12 [0.98, 1.23] negative", "valid as computed. Same gateway-queue note (control P95 9.5 s vs 1.9 s), and the label is unchanged under either definition."),
    ("a9_tok_prefill / decode / prefix_reuse", "energy/1k auth, two-sided", "negative (all three)", "primary valid as computed, with the denominator caveat (§4). Secondary TTFT is **pending validation**: control victims censored by 60 s gateway timeouts, backend vs user TTFT definition."),
    ("a9_tok_longctx", "energy/1k auth, two-sided", "0.78 inconclusive", "**INVALID**: 112/116 competitor requests rejected (context length)."),
    ("a9_rate_prefill / decode / prefix_reuse", "energy/1k auth, two-sided", "supported (all three, ratio < 0.8)", "primary valid as computed, denominator-dominated (§4). Secondary victim backend TTFT: prefill 3.44×, decode 0.90×, prefix reuse 1.27× (not pre-registered claims)."),
    ("a9_rate_longctx", "energy/1k auth, two-sided", "0.18 supported", "**INVALID**: same rejection as tok_longctx."),
]
A(table(pd.DataFrame(val, columns=["block", "metric", "pre-registered result", "status"]), ["block", "metric", "pre-registered result", "status"]))
A("""
S0 (A7-V) noise floor: unaffected. It used the same backend-TTFT definition as the A7 blocks, so the comparison inside the suite is consistent.
""")

# ---------------- corrections ----------------
A("## 7. Corrections required\n")
A("""Analysis code. Recompute offline from existing data; no rerun:
1. `attack_effect.write_report` / `_figures`: label the headline, per-seed columns and y-axis from `analysis["metric"]`
   (for example "J per 1k authorized tokens"), not with a fixed "victim slowdown" / "ms". For A9, also print the secondary victim TTFT ratio
   separately and clearly labelled.
2. `attack_effect.run_metrics`: name the TTFT it uses. Either rename the current column `backend_ttft_ms` and add the
   user-facing `ttft_ms = t_first_token − t_offered` (as in `METRIC_DEFINITIONS.md` and `metrics.py`), or amend
   `METRIC_DEFINITIONS.md`. **Which definition is the pre-registered one is the owner's decision.** The code has used backend TTFT
   since Phase 5, including the A1–A5 headlines. Changing it would change those results, so this needs an ADR. It is not a silent fix.
3. Report victim timeouts and gateway-queue time beside every TTFT ratio, and flag a block as censored when either arm has
   victim timeouts. Today they appear only as a count column.
4. Add a manipulation check that fails a block (or marks it invalid) when the competitor's completed fraction falls below a
   pre-set floor. Today a block whose competitor was 97% rejected gets a classification.
5. My `suite_check.py`: use `None`, not `or 0`, for missing coverage. This is not part of the harness.

Scenario and harness. Needs owner approval, a protocol amendment, and new pre-registration before any rerun:
6. The `scenario.py:284` safety check compares planned words with `model_max_len`. With about 2.1 real tokens per filler word it should
   use the live tokenizer, or a measured tokens-per-word bound. `a9_*_longctx` must be re-sized so the real input stays ≤ 3,840
   tokens. This changes the family's definition, so it is a protocol change.
7. A design-doc statement is wrong for the filler: "Tokenized lengths are verified equal across arms on the live tokenizer (single-token vocab)"
   (`A7_A9_EXPERIMENT_DESIGN.md:50`) holds for the nonce and prefix vocabularies only. Pseudo-word filler is about 2.1 tokens per word. Victim
   prompts are still identical across arms, so victim matching holds, but token-budget matching in A9 is in planned units.
   This should go into `KNOWN_LIMITATIONS.md`.
8. Run a smoke test for each family before a suite. No long-context smoke was run.

## 8. Are GPU reruns needed?

- **No** for A7 (S1, S1′), A8a, A8b, and the six valid A9 blocks. Their data is intact, and items 1–5 are analysis-only.
- **Yes, but only after approval and re-pre-registration**, for `a9_tok_longctx` and `a9_rate_longctx` (about 50 min for both at the
  observed pace, plus a long-context smoke). A new `isolation_salt` is required (warm-cache guard), or a server restart, which
  would start a new non-pooled series.
- If the owner picks user-facing TTFT as the pre-registered definition (item 2), the TTFT results can still be recomputed
  from the existing timestamps, with no rerun needed.
""")

OUT.write_text("\n".join(md) + "\n")
print("wrote", OUT, len("\n".join(md)), "chars")
