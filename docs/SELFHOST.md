# Self-hosted GPU target: setup, preflight and monitoring

Operational guide for the `selfhost` target (`configs/targets/selfhost.yaml`). The useful parts of
[taixingbi/vllm-qwen-serving](https://github.com/taixingbi/vllm-qwen-serving/tree/main) (README,
`per_tenant_cache/PER_TENANT_PREFIX_CACHE_GUIDE.md`, `self-hosted-sample-output.md`, `scripts/gpuwatch.sh`;
copied 2026-11-21, upstream commit `11605de`) are condensed here and adapted to QuotaShift. Facts marked
**measured** were observed by the harness from the runner. Facts marked **upstream** come from the reference repo
and haven't been re-measured here.

Scope reminder (CLAUDE.md): owned, private, isolated LAN target only; synthetic benign prompts; attack-side
characterization; no defenses. The server below runs **without authentication**, so it must never be reachable
from outside the trusted LAN.

## 1. Target facts

| Item | Value | Source |
|---|---|---|
| Endpoint | `http://192.168.86.173:8000` (RFC1918) | measured |
| Server | vLLM `0.17.1` **with the owner's local reporting patch** (§7a); `GET /version` still says `0.17.1` | measured (version) / owner-stated (patch) |
| Model | `Qwen/Qwen2.5-7B-Instruct`, `max_model_len` 4096, revision `a09a35458c702b33eeacc393d103063234e8bc28` | measured (revision: historical manifests) |
| GPU | NVIDIA GeForce RTX 3090, 24 GiB, uuid `a837190a-d9c2-ed45-994b-55319c6e258e`, driver 595.71.05, CUDA 13.2, compute 8.6, power limit 350 W | measured via exporter `nvidia_smi_gpu_info` |
| KV cache | prefix caching ON, `gpu_memory_utilization` 0.80, 4662 GPU blocks of 16 tokens (`vllm:cache_config_info`) | measured |
| Current server start | 2026-11-21 13:44:43.89 UTC (`process_start_time_seconds` 1795268683.89), API server PID 455271 (owner-stated); chat + completions patched | measured (start) / owner-stated (PID) |
| GPU exporter | nvidia_gpu_exporter v2.0.0 on `:9835` | measured |
| Second host | `192.168.86.176`, vLLM 0.34.0. **Never pooled** with .173 (a separate series if used at all) | measured earlier |

Runs on different server starts or configs are never pooled (for example, before and after the
2026-11-21 11:05 UTC restart, which changed `gpu_memory_utilization` from 0.85 to 0.80, or before and after the
~13:01 UTC restart onto the chat-only patch, or the 13:44 UTC restart onto the chat + completions patch).

| Server start (UTC) | `process_start_time_seconds` | Build | Zero-hit `cached_tokens` |
|---|---|---|---|
| 2026-11-21 11:05:29 | 1795259129.33 | stock 0.17.1, dev mode | `null` on both endpoints |
| 2026-11-21 ~13:01:55 | 1795266115.27 | 0.17.1 + chat patch | chat 0, completions `null` |
| 2026-11-21 13:44:43 | 1795268683.89 | 0.17.1 + chat + completions patch (PID 455271) | 0 on both endpoints | `/version` can't tell patched from stock 0.17.1, so the series key is
`process_start_time_seconds` plus the patch note in §7a.

## 2. Server launch (owner action on the GPU host)

The runner has no SSH key for the host, so every launch or restart is done by the owner. QuotaShift needs the
**research configuration** below (from the upstream per-tenant cache guide). Check for and stop any old server
first; never start a second 7B instance on the 24 GB card.

```bash
pgrep -af 'vllm|EngineCore'; nvidia-smi          # confirm only one (or no) server and free VRAM
source ~/miniconda3/etc/profile.d/conda.sh && conda activate vllm

nohup env CUDA_VISIBLE_DEVICES=0 VLLM_SERVER_DEV_MODE=1 \
  vllm serve Qwen/Qwen2.5-7B-Instruct \
  --host 0.0.0.0 --port 8000 \
  --dtype float16 --max-model-len 4096 --gpu-memory-utilization 0.80 \
  --enable-prefix-caching --enable-prompt-tokens-details \
  > ~/vllm.log 2>&1 < /dev/null &
tail -n 50 ~/vllm.log
```

| Setting | Why QuotaShift needs it |
|---|---|
| `VLLM_SERVER_DEV_MODE=1` | Enables `POST /reset_prefix_cache`, which the verified-reset A7 variant needs (`cache_reset: vllm_endpoint`). Without it the endpoint returns 404. |
| `--enable-prefix-caching` | The A7 variable. Scenarios declare `expect_prefix_caching` and fail closed if the server differs. |
| `--enable-prompt-tokens-details` | Adds `usage.prompt_tokens_details.cached_tokens` per request, which makes per-tenant hit ratios observable. |
| `--gpu-memory-utilization 0.80`, `--max-model-len 4096` | Part of the locked serving config. Changing either starts a new, unpooled series. |

Cache-OFF blocks (Suite R2) restart with `--no-enable-prefix-caching` instead, and are a separate series.

**Dev-mode warning (upstream):** dev mode also exposes `/collective_rpc`, `/update_weights`, `/sleep`, `/pause`,
`/load` and similar endpoints, all without authentication. The harness calls only `/reset_prefix_cache`. Keep the
host on the isolated LAN, or bind to localhost and use an SSH tunnel.

`nohup` survives SSH disconnects but not a reboot. After a reboot, launch again and re-run the preflight.

Stop: `pgrep -af 'vllm serve'`, then `kill <PID>`.

## 3. GPU exporter (owner action on the GPU host)

`nvidia-smi` runs only on the GPU host. [nvidia_gpu_exporter](https://github.com/utkuozdemir/nvidia_gpu_exporter)
wraps it and serves Prometheus metrics on `:9835`, so the runner reads GPU power without SSH. Install (upstream):

```bash
cd ~
VER=$(curl -s https://api.github.com/repos/utkuozdemir/nvidia_gpu_exporter/releases/latest | grep -Po '"tag_name": "v\K[^"]+')
curl -LO https://github.com/utkuozdemir/nvidia_gpu_exporter/releases/download/v${VER}/nvidia_gpu_exporter_${VER}_linux_x86_64.tar.gz
tar xzf nvidia_gpu_exporter_${VER}_linux_x86_64.tar.gz && sudo mv nvidia_gpu_exporter /usr/local/bin/
nohup nvidia_gpu_exporter > ~/gpu_exporter.log 2>&1 &
curl -s localhost:9835/metrics | grep nvidia_smi_power_draw_watts
sudo ufw allow from 192.168.86.0/24 to any port 9835 proto tcp     # LAN only, if the port is blocked
```

Record the installed version: v2.0.0 was verified on 2026-11-21. Changing the version means re-checking the metric
names below. QuotaShift's own `quotashift gpu-exporter --host <LAN IP>` is an alternative; the harness parses DCGM,
nvidia_gpu_exporter and its own exporter.

Harness wiring: `gpu_exporter_url: http://192.168.86.173:9835/metrics` in `configs/targets/selfhost.yaml`.
The sampler (`src/quotashift/instrumentation/gpu.py`) maps these metrics:

| Exporter metric | Harness field | Conversion |
|---|---|---|
| `nvidia_smi_power_draw_watts` | `power_w` | W |
| `nvidia_smi_utilization_gpu_ratio` | `gpu_util_perc` | × 100 |
| `nvidia_smi_memory_used_bytes` / `_total_bytes` | `mem_used_mib` / `mem_total_mib` | ÷ 2^20 |
| `nvidia_smi_temperature_gpu` | `temp_c` | °C |
| `nvidia_smi_clocks_current_sm_clock_hz` / `_memory_clock_hz` | `sm_clock_mhz` / `mem_clock_mhz` | ÷ 10^6 |
| `nvidia_smi_gpu_info{index,uuid,name,driver_version,…}` | GPU index ↔ uuid, and `static_info` | labels |

Metrics are labelled by `uuid`; a uuid without a matching `gpu_info` index is ignored, never assumed to be
GPU 0. To list every metric your exporter version reports:
`curl -s http://192.168.86.173:9835/metrics | grep '^nvidia_smi' | cut -d'{' -f1 | sort -u`.

Live view from the Mac (needs only `curl` and `awk`): `scripts/gpuwatch.sh [host] [interval_s]`. Its columns follow
`nvidia-smi dmon`: `pcap` and `tthrot` are 0/1 throttle-reason flags, not dmon's `pviol` or `tviol` percentages.
For cumulative power-cap time, use `nvidia_smi_clocks_event_reasons_counters_sw_power_cap_seconds`.

## 4. GPU power behaviour (measured 2026-11-21) and what the harness does about it

| State | SM / mem clock | Board power | Util |
|---|---|---|---|
| Idle, model loaded | 210 / 405 MHz | ~31 W, with ~40 W blips about every 7 s (upstream dmon: 19–29 W) | 0% |
| Under load (8 concurrent prefill+decode) | ~1700 / 9501 MHz | 290–340 W | 100% |
| **Post-load plateau** | **1725 / 9501 MHz** | **~130 W for ~16 s** | **0%** |
| P-state transition | 345 → 210 MHz | 123 → 77 → 35 W over ~3 s | 0% |

An idle GPU still holds about 20 GiB of VRAM (weights plus the KV allocator), so a high `fb` value doesn't mean
the GPU is busy, and 0% SM doesn't mean the model is unloaded.

Consequences for energy measurement (ADR / design-doc amendment 2026-11-21):
- **Idle baseline:** before each arm the harness waits (at most 90 s) until 6 consecutive samples show util 0,
  SM ≤ 500 MHz and power spread ≤ 15 W, then uses their **median**. Without the clock check, the 130 W plateau
  (and 216 W right after an arm) was accepted as "idle". If the GPU doesn't settle, dynamic energy is reported as
  unavailable. The 500 MHz threshold is calibrated on this card.
- **Post-arm tail:** about 22 s and about 2 kJ per arm. It's recorded as `gpu_tail` and
  `gpu_dynamic_energy_with_tail_j` (secondary); the primary metric is the pre-registered arm-window energy.
- Both waits add about 25 s per run.

## 5. Preflight (from the runner, before every suite)

```bash
uv run quotashift target check selfhost
```

Expected under `check.capabilities` (2026-11-21):
- `served_models` includes `Qwen/Qwen2.5-7B-Instruct`.
- `prefix_caching: true` and `gpu_memory_utilization: 0.8` (they must match the series).
- `reset_prefix_cache_listed: true` (needed for the verified-reset A7 variant).
- `engine_idle: true`.
- `gpu_exporter.power_w_ok: true`, with idle `sm_clock_mhz` around 210.
- `process_start_time_seconds` equals the value recorded for the series; any change means a server restart, so
  start a new series.

`quotashift experiment --live` runs this check automatically, saves it to `<report>/target_snapshot/`, and refuses to
start if it fails. During the run, each arm also waits (at most 30 s) for the engine to be awake and idle
(`EngineNotReady` otherwise), and stops with `ServerRestarted` if `process_start_time_seconds` changes. Without a
verified reset, re-sending a byte-identical trace to the same server start is refused (warm prefix cache): use a
new `isolation_salt` per replication.

Manual equivalents (all read-only, except the reset):

```bash
B=http://192.168.86.173:8000
curl -s $B/version; curl -s $B/v1/models
curl -s $B/openapi.json | grep -o '"/[^"]*reset_prefix_cache[^"]*"'          # listed => dev mode on
curl -s $B/metrics | grep -E '^(process_start_time_seconds|vllm:(num_requests_(running|waiting)|cache_config_info|engine_sleep_state))'
curl -s http://192.168.86.173:9835/metrics | grep -E '^nvidia_smi_(power_draw_watts|utilization_gpu_ratio|clocks_current_sm_clock_hz)'
```

**Cache reset:** reset only when no requests are running. The reset clears the whole instance, not one tenant.
HTTP 200 only shows that the request was handled, so the harness always verifies it with `reset_and_verify`
(a probe that must hit, then miss after the reset, and fails closed otherwise). Measured 2026-11-21: probe hits
went from 96 before the reset to 0 after it.

## 6. Metrics the harness reads

From vLLM `/metrics` (engine-global; no tenant labels):

| Metric | Use |
|---|---|
| `vllm:num_requests_running` / `_waiting` | engine idle/drain checks, queue depth |
| `vllm:kv_cache_usage_perc` | KV pressure (older vLLM name: `vllm:gpu_cache_usage_perc`) |
| `vllm:prefix_cache_queries_total` / `_hits_total` | per-arm hit ratio (Δ between arm snapshots) |
| `vllm:prompt_tokens_total`, `vllm:generation_tokens_total` | attribution check against client usage |
| `vllm:num_preemptions_total` | KV-pressure preemptions |
| `vllm:time_to_first_token_seconds`, `vllm:e2e_request_latency_seconds`, prefill/decode time histograms | engine-side timing (`_sum` / `_count`) |
| `vllm:cache_config_info` | config check (prefix caching, memory utilization, block count) |
| `process_start_time_seconds` | restart / counter-reset detection |

| `vllm:prompt_tokens_by_source_total{source=local_compute\|local_cache_hit}` | measured prefill-computed tokens (beside the Δprompt − Δhits estimate) |
| `vllm:engine_sleep_state{sleep_state="awake"}` | preflight: the engine must be awake |
| `process_start_time_seconds` | also: series key, restart stop, warm-cache re-run guard |

Available but **not read**: `vllm:estimated_flops_per_gpu_total` and the related read/write-bytes counters
(0 unless MFU tracking is enabled).

Observed on 0.17.1 (patched): Δ`local_compute` + Δ`local_cache_hit` exceeded Δ`prompt_tokens_total` by 4 tokens
in a 18,250-token arm, while Δ`local_compute` matched Δprompt − Δ`prefix_cache_hits_total` exactly. The cause
isn't known; it's reported, not corrected.

Histograms appear as `_bucket`, `_sum` and `_count`. Names change between vLLM versions, so confirm them with
`curl -s $B/metrics | grep '^vllm:'` after any upgrade.

## 7. Per-request cached tokens (enabled by `--enable-prompt-tokens-details`)

- **Measured 2026-11-21:** the same 569-token chat prompt returned `prompt_tokens_details` values of
  `null`, then `{cached_tokens: 560}`, then `{cached_tokens: 560}`. Streaming `/v1/completions` with
  `stream_options.include_usage=true` also reports it (528 of 540 cached).
- **`cached_tokens: 0` is an observation; `null` is missing data.** Stock vLLM 0.17.1 returns `null` for any
  zero-hit request; after the local patch (§7a), the chat endpoint reports 0. The harness never imputes a null
  as 0. Telemetry coverage (completed requests with a numeric value ÷ completed requests) is reported next to
  every ratio.
- **Per-tenant ratio:** the harness's gateway assigns `tenant_id`. The ratio is token-weighted,
  Σ cached_tokens ÷ Σ prompt_tokens over the tenant's completed requests with a valid value (zeros included), and
  never a mean of per-request ratios. Cancelled and timed-out requests carry no usage; they're counted as
  `noncompleted`, never in the ratio. When coverage is below 1, the missing requests are the zero-hit ones, so the
  "reported-only" ratio is biased upward.
- **Engine reconciliation** (`cached_tokens.engine_reconciliation` in each live run summary): residual =
  engine Δ`prefix_cache_hits_total` − Σ reported `cached_tokens`. If the arm's attribution is exact (no unrelated
  traffic, no cancelled requests) and residual = 0, then every `null` request had exactly 0 hits, because hits
  can't be negative. Only in that case the summary adds `hit_ratio_all_completed_reconciled` (Σ cached ÷ Σ prompt
  over **all** completed requests), labelled as derived. The reported-only ratio and coverage stay beside it.
- A hit means reused prefix KV blocks. It is not KV occupancy and not direct evidence of eviction.
- **Status (implemented 2026-11-21):** the harness records `cached_tokens_reported` per request in
  `requests.parquet`. Each run's `metrics_summary.json` gets `cached_tokens.by_tenant` and `.by_class`
  (completed, reporting, coverage, `hit_ratio_reported`), and the paired report gets a per-arm table
  (`src/quotashift/evaluation/cache_hits.py`). Live check (A7 smoke, 1 seed): Σ per-request `cached_tokens`
  equalled the engine's Δ`prefix_cache_hits_total` exactly in both arms (4240 and 9424), with victim coverage 0.885.
  These are secondary metrics; the engine-global per-arm counters stay the reference.
- **GPU-server requirement:** the §2 launch flags; `--enable-prompt-tokens-details` is what turns the field on.
  Without it every request reports `null`, coverage is 0 and the per-tenant ratios are `n/a`.

### 7a. Local vLLM patch: zero-hit reporting (owner-applied, 2026-11-21)

What changed (owner-stated). In `vllm/entrypoints/openai/chat_completion/serving.py`, two conditions became
`... and num_cached_tokens is not None:` and `... and final_res.num_cached_tokens is not None:`. The same fix was
then applied to the completions serving code, and the server restarted at 13:44:43 UTC (PID 455271, log shows
`Application startup complete`). Before, zero
hits produced `prompt_tokens_details: null`; now a successful zero-hit chat request returns
`{"cached_tokens": 0}`. The owner's validation: tenant A cold 0 / 1080, warm 1072 / 1080 twice; tenant B cold
16 / 931 (shared template block), warm 928 / 931 twice.

**What it does not change:** this patch fixes **reporting only**. It doesn't change the prefix cache, cache
isolation between tenants, block allocation or eviction, scheduling, or batching. Engine counters, latencies and
every pre-registered endpoint are unaffected. The server was still restarted, though, so the series rule above
applies.

What the harness measured (2026-11-21):

| Endpoint | Cold request, chat-only patch (~08:05 local) | Cold request, chat + completions patch (08:45 local) |
|---|---|---|
| `/v1/chat/completions` (non-stream + stream) | `{"cached_tokens": 0}` | `{"cached_tokens": 0}` |
| `/v1/completions` (non-stream + stream) | `null` | `{"cached_tokens": 0}` (warm repeat: 64 / 72) |

A cold *chat* request usually reports 16, not 0: the Qwen chat template's default system preamble fills a
shared first 16-token block. Only a unique first block gives 0.

**Consequence:** both harness paths now get full coverage: the **live runner** (`/v1/completions`, all Suite R/S
experiments) and the **gateway-server path** (`/v1/chat/completions`). The live runner's endpoint and workload
were not changed. On the earlier chat-only build the live runner saw `null` for zero-hit requests; those runs are
kept, and their nulls were shown to be zeros by the engine reconciliation.

**Validation (A7 smoke, 1 paired seed, 2026-11-21 08:45–08:47 local, unchanged config):** coverage 1.000 for every
tenant and class in both arms, 0 nulls among 34 completed requests per arm. Σ per-request `cached_tokens` equals the
engine's Δhits exactly (attack 9424, control 4240; residual 0, exact attribution, no unrelated traffic). The
observed token-weighted ratios equal the earlier reconciliation-derived ones exactly: victim 0.452 / 0.452,
competitor 0.585 (attack) / 0.000 (control). Single seed; harness validation only, not an attack effect.
- vLLM's per-request `cache_salt` (upstream `--salted` demo) is a tenant-isolation mechanism, i.e. it changes the
  system under test. It is **not** used in QuotaShift's locked serving config; a salted condition would be a
  separate series.

## 8. Chat-template overhead

The chat template adds system and role tokens: the 7-word message "Explain vLLM in one sentence." counts as 38
prompt tokens (upstream sample). The harness therefore compares *realized* `usage.prompt_tokens` across arms
instead of planned word counts, and the budget gate works on the traces as sent.

## 9. Troubleshooting

| Symptom | Check |
|---|---|
| `target check` unreachable / `curl: (7)` | Server starting or exited: `tail -n 80 ~/vllm.log`, `pgrep -af 'vllm|EngineCore'` (owner) |
| `/reset_prefix_cache` 404 | Running server lacks `VLLM_SERVER_DEV_MODE=1`; restart per §2 (then a new series) |
| `prompt_tokens_details` null on a cold request | Stock 0.17.1 or a build without the §7a patch: check `process_start_time_seconds` against the table in §1 |
| `prompt_tokens_details` null on warm repeats | Check `--enable-prompt-tokens-details` and prefix caching in the log; prompts must share a full 16-token block |
| Exporter `:9835` unreachable | Exporter not running (`pgrep -af nvidia_gpu_exporter`) or firewall; allow the LAN only |
| Idle baseline never settles (energy unavailable) | Another process on the GPU (`nvidia-smi`), or a different GPU whose idle SM clock is > 500 MHz (re-calibrate) |
| CUDA OOM at launch | A duplicate server is holding VRAM; stop it first |
| `process_start_time_seconds` changed mid-suite | Server restarted: discard the affected pair, start a new series |
