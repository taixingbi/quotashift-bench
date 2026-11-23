"""Read-only Suite S forensic audit. Reads results/ and reports/v3/; writes only to the scratchpad."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/Users/h/Documents/paper/paper13-quotashift-bench/quotashift-bench")
OUT = Path(sys.argv[1])
BLOCKS = ("a7_prefix_cache a7_prefix_cache_reset a8_lifecycle_churn a8_retry_churn a9_tok_prefill a9_tok_decode "
          "a9_tok_longctx a9_tok_prefix_reuse a9_rate_prefill a9_rate_decode a9_rate_longctx a9_rate_prefix_reuse").split()


def pct(s, q):
    s = pd.Series(s).dropna()
    return float(np.percentile(s, q)) if len(s) else None


def trace_key(rec):
    return (rec["tenant_id"], round(rec["arrival_time_s"], 9), rec["input_token_count"], rec["max_output_tokens"],
            hashlib.sha256(rec["prompt_text"].encode()).hexdigest()[:16])


def load_trace(d):
    return [json.loads(x) for x in (d / "trace.jsonl").read_text().splitlines() if x.strip()]


rows, cov_rows, trace_rows, prov_rows = [], [], [], []
for b in BLOCKS:
    rep = json.loads((ROOT / f"reports/v3/{b}/manifest.json").read_text())
    for seed_s, arms in ((s, {a: rep["run_dirs"][a][s] for a in ("attack", "control")}) for s in rep["run_dirs"]["attack"]):
        traces = {}
        for arm, dstr in arms.items():
            d = Path(dstr)
            s = json.loads((d / "metrics_summary.json").read_text())
            m = json.loads((d / "manifest.json").read_text())
            df = pd.read_parquet(d / "requests.parquet")
            ts = pd.read_parquet(d / "metrics_timeseries.parquet")
            tr = load_trace(d)
            traces[arm] = tr
            e, ca = s.get("engine_counters") or {}, s.get("cost_accounting") or {}
            warm = float(s.get("warmup_s") or 0)
            w = df[df.trace_arrival_s >= warm]
            vic, comp = w[w.workload_class == "victim"], w[w.workload_class == "competitor"]
            vok = vic[vic.terminal_status == "completed"]
            backend_ttft = (vok.t_first_token - vok.t_sent) * 1000
            client_ttft = (vok.t_first_token - vok.t_offered) * 1000
            gwq = (vic.t_sent - vic.t_accepted) * 1000
            done = df[df.terminal_status == "completed"]
            realized = float(pd.to_numeric(done.prompt_tokens_reported, errors="coerce").sum()
                             + pd.to_numeric(done.output_tokens, errors="coerce").sum())
            dyn, auth = ca.get("gpu_dynamic_energy_j"), ca.get("authorized_tokens")
            dyn_tail = ca.get("gpu_dynamic_energy_with_tail_j")
            svc = (e.get("prefill_time_seconds_sum") or 0) + (e.get("decode_time_seconds_sum") or 0)
            pw = ts.gpu_power_w.dropna()
            span = float(ts.t_rel_s.max() - ts.t_rel_s.min()) if len(ts) else None
            st = e.get("engine_state_at_start") or {}
            vc = vic.terminal_status.value_counts().to_dict()
            rows.append(dict(
                block=b, seed=int(seed_s), arm=arm,
                v_offered=len(vic), v_admitted=int(vic.t_accepted.notna().sum()), v_sent=int(vic.t_sent.notna().sum()),
                v_completed=vc.get("completed", 0), v_timed_out=vc.get("timed_out", 0),
                v_rejected=sum(v for k, v in vc.items() if "reject" in str(k)),
                v_cancelled=sum(v for k, v in vc.items() if "cancel" in str(k)),
                v_other=sum(v for k, v in vc.items() if k not in ("completed", "timed_out") and "reject" not in str(k)
                            and "cancel" not in str(k)),
                v_pending=int(len(vic) - vic.terminal_status.notna().sum()),
                v_noncompleted_with_first_token=int(((vic.terminal_status != "completed") & vic.t_first_token.notna()).sum()),
                v_ttft_p50=pct(backend_ttft, 50), v_ttft_p95=pct(backend_ttft, 95), v_ttft_p99=pct(backend_ttft, 99),
                v_client_ttft_p95=pct(client_ttft, 95), v_gwq_p95=pct(gwq, 95), v_gwq_max=pct(gwq, 100),
                c_offered=len(comp), c_completed=int((comp.terminal_status == "completed").sum()),
                c_status=json.dumps(comp.terminal_status.value_counts().to_dict()),
                c_req_in=int(comp.input_token_count.sum()), c_req_out=int(comp.max_output_tokens.sum()),
                c_real_prompt=float(pd.to_numeric(comp[comp.terminal_status == "completed"].prompt_tokens_reported, errors="coerce").sum()),
                c_real_out=float(pd.to_numeric(comp[comp.terminal_status == "completed"].output_tokens, errors="coerce").sum()),
                running_mean=float(ts.num_requests_running.mean()), running_max=float(ts.num_requests_running.max()),
                waiting_max=float(ts.num_requests_waiting.max()), kv_mean=float(ts.kv_cache_usage_perc.mean()),
                kv_max=float(ts.kv_cache_usage_perc.max()), gw_inflight_max=float(ts.gw_inflight.max()) if "gw_inflight" in ts else None,
                power_mean=float(pw.mean()) if len(pw) else None, power_samples=int(len(pw)), ts_rows=int(len(ts)),
                ts_span_s=span, max_gap_s=float(ts.t_rel_s.diff().max()) if len(ts) > 1 else None,
                idle_w=ca.get("gpu_idle_power_w"), idle_settled=(ca.get("gpu_idle_baseline") or {}).get("settled"),
                tail_settled=(ca.get("gpu_tail") or {}).get("settled"),
                energy_j=ca.get("gpu_energy_j"), dyn_j=dyn, dyn_tail_j=dyn_tail,
                auth_tok=auth, comp_auth_tok=ca.get("competitor_authorized_tokens"), realized_tok=realized,
                e_per_1k_auth=(dyn / (auth / 1000)) if dyn is not None and auth else None,
                e_tail_per_1k_auth=(dyn_tail / (auth / 1000)) if dyn_tail is not None and auth else None,
                e_per_1k_real=(dyn / (realized / 1000)) if dyn is not None and realized else None,
                svc_s=svc, svc_per_1k_auth=svc / (auth / 1000) if auth else None,
                engine_busy_s=ca.get("engine_busy_s"), prefill_s=e.get("prefill_time_seconds_sum"),
                decode_s=e.get("decode_time_seconds_sum"), eng_prompt=e.get("prompt_tokens_total"),
                eng_gen=e.get("generation_tokens_total"), hit_ratio=e.get("prefix_cache_hit_ratio"),
                attribution=e.get("attribution_mode"), unrelated=e.get("unrelated_traffic_suspected"),
                residual=((s.get("cached_tokens") or {}).get("engine_reconciliation") or {}).get("residual"),
                nulls_implied_zero=((s.get("cached_tokens") or {}).get("engine_reconciliation") or {}).get("nulls_implied_zero"),
                server_start=st.get("process_start_time_seconds"), restarted=e.get("server_restarted"),
                leak=(s.get("cleanup_checks") or {}).get("leak_detected"), warmup_s=warm,
                victim_deadline=json.dumps(sorted(set(zip(vic.ttft_deadline_ms, vic.e2e_deadline_ms)))),
            ))
            # coverage by tenant x status, from raw per-request rows (all rows, no warm-up cut)
            for (ten, stt), g in df.groupby(["tenant_id", "terminal_status"], dropna=False):
                ct = g.cached_tokens_reported
                cov_rows.append(dict(block=b, seed=int(seed_s), arm=arm, tenant=ten, status=stt, n=len(g),
                                     ct_dtype=str(ct.dtype), ct_null=int(ct.isna().sum()), ct_zero=int((ct == 0).sum()),
                                     ct_pos=int((ct > 0).sum()), ct_sum=float(ct.sum(skipna=True)),
                                     pt_null=int(g.prompt_tokens_reported.isna().sum())))
            # summary-reported coverage, kept as reported (None stays None)
            for ten, v in ((s.get("cached_tokens") or {}).get("by_tenant") or {}).items():
                cov_rows.append(dict(block=b, seed=int(seed_s), arm=arm, tenant=ten, status="__summary__",
                                     n=v.get("completed"), summary_coverage=v.get("coverage"),
                                     summary_noncompleted=v.get("noncompleted"), summary_reporting=v.get("reporting")))
            run = m.get("run_context") or {}
            prov_rows.append(dict(block=b, seed=int(seed_s), arm=arm, experiment_id=m.get("experiment_id"),
                                  run_id=m.get("run_id"), git_sha=(m.get("git") or {}).get("sha"),
                                  git_dirty=(m.get("git") or {}).get("dirty"), trace_sha256=m.get("trace_sha256"),
                                  config_sha256=m.get("config_sha256"), vllm=(m.get("backend_info") or {}).get("/version"),
                                  base_url=(m.get("backend_info") or {}).get("base_url"),
                                  admission=json.dumps(run.get("admission_policy")), rate_limits=json.dumps(run.get("rate_limits")),
                                  queue_caps=json.dumps(run.get("queue_caps")),
                                  arm_order=json.dumps(rep.get("arm_order", {}).get(seed_s)),
                                  server_start=st.get("process_start_time_seconds"),
                                  manifest_keys=",".join(sorted(m))))
        # trace identity
        ka = {trace_key(r) for r in traces["attack"] if r["workload_class"] == "victim"}
        kc = {trace_key(r) for r in traces["control"] if r["workload_class"] == "victim"}
        ca_ = sorted(r["arrival_time_s"] for r in traces["attack"] if r["workload_class"] == "competitor")
        cc_ = sorted(r["arrival_time_s"] for r in traces["control"] if r["workload_class"] == "competitor")
        same_arr = len(ca_) == len(cc_) and bool(np.allclose(ca_, cc_, atol=1e-9)) if ca_ and cc_ else (ca_ == cc_)
        trace_rows.append(dict(block=b, seed=int(seed_s), victim_n_attack=len(ka), victim_n_control=len(kc),
                               victim_identical=ka == kc, comp_n_attack=len(ca_), comp_n_control=len(cc_),
                               comp_arrivals_identical=same_arr,
                               comp_in_attack=sum(r["input_token_count"] for r in traces["attack"] if r["workload_class"] == "competitor"),
                               comp_in_control=sum(r["input_token_count"] for r in traces["control"] if r["workload_class"] == "competitor"),
                               comp_out_attack=sum(r["max_output_tokens"] for r in traces["attack"] if r["workload_class"] == "competitor"),
                               comp_out_control=sum(r["max_output_tokens"] for r in traces["control"] if r["workload_class"] == "competitor"),
                               comp_shapes_attack=json.dumps(sorted({(r["input_token_count"], r["max_output_tokens"]) for r in traces["attack"] if r["workload_class"] == "competitor"})[:4]),
                               comp_shapes_control=json.dumps(sorted({(r["input_token_count"], r["max_output_tokens"]) for r in traces["control"] if r["workload_class"] == "competitor"})[:4])))

OUT.mkdir(parents=True, exist_ok=True)
pd.DataFrame(rows).to_csv(OUT / "per_arm.csv", index=False)
pd.DataFrame(cov_rows).to_csv(OUT / "coverage.csv", index=False)
pd.DataFrame(trace_rows).to_csv(OUT / "trace_identity.csv", index=False)
pd.DataFrame(prov_rows).to_csv(OUT / "provenance.csv", index=False)
print("rows", len(rows), "cov", len(cov_rows), "trace", len(trace_rows))
