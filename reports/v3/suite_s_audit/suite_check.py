import json, glob, pandas as pd
B="a7_prefix_cache a7_prefix_cache_reset a8_lifecycle_churn a8_retry_churn a9_tok_prefill a9_tok_decode a9_tok_longctx a9_tok_prefix_reuse a9_rate_prefill a9_rate_decode a9_rate_longctx a9_rate_prefix_reuse".split()
rows=[]
for b in B:
  for arm in ("attack","control"):
    for d in sorted(glob.glob(f"results/{b}__{arm}/*")):
      try: s=json.load(open(d+"/metrics_summary.json"))
      except FileNotFoundError: continue
      e=s.get("engine_counters") or {}; c=s.get("cached_tokens") or {}; ca=s.get("cost_accounting") or {}
      bt=c.get("by_tenant") or {}
      rows.append(dict(block=b,arm=arm,
        cov=min((v.get("coverage") or 0) for v in bt.values()) if bt else None,
        resid=(c.get("engine_reconciliation") or {}).get("residual"),
        attr=e.get("attribution_mode"),unrel=e.get("unrelated_traffic_suspected"),
        restart=e.get("server_restarted"),start=(e.get("engine_state_at_start") or {}).get("process_start_time_seconds"),
        pf_diff=e.get("prefill_est_minus_measured"),hit=e.get("prefix_cache_hit_ratio"),
        prompt=e.get("prompt_tokens_total"),gen=e.get("generation_tokens_total"),
        busy=(e.get("prefill_time_seconds_sum") or 0)+(e.get("decode_time_seconds_sum") or 0),
        offered=s.get("offered"),completed=(s.get("status_counts") or {}).get("completed"),
        idle_ok=(ca.get("gpu_idle_baseline") or {}).get("settled"),
        energy=ca.get("gpu_dynamic_energy_j"),
        leak=(s.get("cleanup_checks") or {}).get("leak_detected"),
        acc=s.get("accounting_conserved")))
r=pd.DataFrame(rows)
print("runs:",len(r),"server starts:",sorted(set(r.start)))
g=r.groupby("block",sort=False)
q=g.agg(n=("arm","size"),cov_min=("cov","min"),resid_max=("resid",lambda x: x.abs().max()),
  attr=("attr",lambda x:",".join(sorted(set(map(str,x))))),unrel=("unrel","sum"),restart=("restart","sum"),
  pf_diff_max=("pf_diff",lambda x: x.abs().max()),idle_ok=("idle_ok","all"),leak=("leak","sum"),acc=("acc","all"))
pd.set_option("display.width",250); print(q.to_string())
m=r.groupby(["block","arm"],sort=False)[["hit","prompt","gen","busy","offered","completed","energy"]].mean().round(3)
print(m.to_string())
