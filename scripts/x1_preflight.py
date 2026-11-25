"""X1 P1 + preflight driver for G0 platforms (rev 4 sections 8, 9). Decisions use the FROZEN rule functions in
src/quotashift/x1/preflight.py; this driver only measures and records.

    QUOTASHIFT_TARGET=x1-g0-mistral uv run python scripts/x1_preflight.py phase1 --platform g0m1 --host gpu-node-2
    QUOTASHIFT_TARGET=x1-g0-mistral uv run python scripts/x1_preflight.py phase2 --platform g0m1 --host gpu-node-2

Writes experiments/x1/<plat>/HOST_VERIFICATION.json (sanitized: no addresses, paths or device ids) with
`p1` (identity evidence) and `preflight.phase1` / `preflight.phase2` (status + every check). Raw measurement files go to
reports/x1/<plat>/preflight/ (git-ignored). Requests sent: /version, /v1/models, /server_info, /metrics, /health,
/tokenize, /reset_prefix_cache (verified probe), short fixed-length /v1/completions (smoke, decode-rate probe, TTFT
floor) and the two experiment mini-blocks (smoke in Phase 1, high-rate load in Phase 2) through the harness.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_x1  # noqa: E402

from quotashift.instrumentation.cache_reset import reset_and_verify  # noqa: E402
from quotashift.instrumentation.prom import parse_prometheus_text, resolve  # noqa: E402
from quotashift.targets import active_target  # noqa: E402
from quotashift.x1 import preflight as pf  # noqa: E402
from quotashift.x1.tokenize_probe import burst, clock_offset_probe, isolated  # noqa: E402

X1 = REPO / "experiments" / "x1"
TEMPLATE = {"--dtype": "float16", "--max-model-len": "4096", "--gpu-memory-utilization": "0.80",
            "--enable-prefix-caching": None, "--enable-prompt-tokens-details": None, "--max-num-seqs": "256",
            "--max-num-batched-tokens": "2048", "--host": "0.0.0.0", "--port": "8000"}
M1_EXTRA = {"--tokenizer-mode": "mistral", "--config-format": "mistral", "--load-format": "mistral"}
ENV_PY = "$HOME/miniconda3/envs/vllm0171/bin/python"


def ssh(host: str, cmd: str, stdin: str | None = None, timeout: int = 900) -> str:
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", host, cmd], input=stdin, capture_output=True, text=True,
                       timeout=timeout)
    if r.returncode:
        raise RuntimeError(f"ssh {cmd[:60]!r} failed: {r.stderr[-400:]}")
    return r.stdout


def now() -> str:
    return datetime.now(UTC).isoformat()


# ------------------------------------------------------------------------------------------------ server identity
def server_facts(base: str, model: str) -> dict:
    with httpx.Client(timeout=20) as c:
        ver = c.get(base + "/version").json().get("version")
        models = [m["id"] for m in c.get(base + "/v1/models").json()["data"]]
        si = c.get(base + "/server_info")
        info = si.json() if si.status_code == 200 else {}
        met = resolve(parse_prometheus_text(c.get(base + "/metrics").text))
    cc = met.info.get("vllm:cache_config_info") or {}
    blocks, bsz = int(float(cc.get("num_gpu_blocks", 0))), int(float(cc.get("block_size", 0)))
    blob = json.dumps(info)
    return {"vllm_version": ver, "models": models, "model_listed": model in models,
            "server_info_available": si.status_code == 200, "server_info_text": blob,
            "process_start_time_seconds": met.values.get("process_start_time_seconds"),
            "cache_config": {k: cc.get(k) for k in ("block_size", "num_gpu_blocks", "gpu_memory_utilization",
                                                    "enable_prefix_caching", "cache_dtype")},
            "kv_tokens": blocks * bsz}


def argv_check(host: str, plat: str) -> dict:
    out = ssh(host, "for p in $(pgrep -u $USER -f 'vllm serve'); do printf '%s|' \"$(readlink /proc/$p/exe)\"; "
                    "tr '\\0' ' ' < /proc/$p/cmdline; echo; done")
    procs = [ln.split("|", 1) for ln in out.strip().splitlines() if ln]
    py = [(exe, args.split()) for exe, args in procs if "python" in exe.rsplit("/", 1)[-1]]
    if len(py) != 1:
        return {"ok": False, "reason": f"{len(py)} python vllm-serve processes", "n_processes": len(procs)}
    argv = py[0][1]
    i = argv.index("serve")
    model, rest = argv[i + 1], argv[i + 2:]
    flags: dict = {}
    k = 0
    while k < len(rest):
        if k + 1 < len(rest) and not rest[k + 1].startswith("--"):
            flags[rest[k]], k = rest[k + 1], k + 2
        else:
            flags[rest[k]], k = None, k + 1
    exp = {**TEMPLATE, "--revision": build_x1.PLATFORMS[plat]["revision"], **(M1_EXTRA if plat.endswith("m1") else {})}
    return {"ok": model == build_x1.PLATFORMS[plat]["model"] and flags == exp, "model": model,
            "unexpected": sorted(set(flags) ^ set(exp)), "mismatched": sorted(k for k in exp if k in flags and flags[k] != exp[k]),
            "env_python_is_pinned_env": "vllm0171" in py[0][0]}


def env_sources(host: str) -> dict:
    out = ssh(host, f"{ENV_PY} - <<'EOF'\nimport hashlib, importlib.metadata as md, vllm, os\n"
                    "b=os.path.dirname(vllm.__file__)\n"
                    "h=lambda r: hashlib.sha256(open(os.path.join(b,r),'rb').read()).hexdigest()\n"
                    "import json; print(json.dumps({'vllm': md.version('vllm'), 'torch': md.version('torch'), "
                    "'transformers': md.version('transformers'), 'mistral_common': md.version('mistral_common'), "
                    "'sources': {r: h(r) for r in ('engine/arg_utils.py','config/vllm.py','entrypoints/cli/serve.py')}}))\nEOF")
    return json.loads(out)


V5_SOURCE_PINS = {"engine/arg_utils.py": "846fe5ade00f9651e7cee487092c6cb69eb02f19b15906a8c68a3683678a179f",
                  "config/vllm.py": "405074725a88d63cf1221caf84261485f97d3f1d4eadb2837df78753fc8d5490",
                  "entrypoints/cli/serve.py": "64b4427d989d6e35b353d1d718075a1c6560e1c65026de8592a57c1567e7b0ec"}


def weight_hashes(host: str, plat: str) -> dict:
    p = build_x1.PLATFORMS[plat]
    tree = httpx.get(f"https://huggingface.co/api/models/{p['model']}/tree/{p['revision']}", timeout=30).json()
    want = {f["path"]: f["lfs"]["oid"] for f in tree if f.get("lfs") and f["path"].endswith(".safetensors")}
    if plat.endswith("m1"):
        want = {k: v for k, v in want.items() if k.startswith("consolidated")}   # --load-format mistral
    snap = f"$HOME/.cache/huggingface/hub/models--{p['model'].replace('/', '--')}/snapshots/{p['revision']}"
    got = {}
    for name in sorted(want):
        got[name] = ssh(host, f"nice -n 19 sha256sum \"$(readlink -f {snap}/{name})\" | cut -d' ' -f1", timeout=1800).strip()
    return {"ok": bool(want) and got == want, "files": {k: {"expected": want[k], "actual": got[k]} for k in want}}


# ------------------------------------------------------------------------------------------------ requests
def completion(base: str, model: str, prompt: str, max_tokens: int, *, stream: bool = False) -> dict:
    body = {"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0.0, "ignore_eos": True,
            "logprobs": 1}
    with httpx.Client(timeout=120) as c:
        if not stream:
            t0 = time.perf_counter()
            r = c.post(base + "/v1/completions", json=body).json()
            ch = r["choices"][0]
            lps = (ch.get("logprobs") or {}).get("token_logprobs") or []
            return {"out_tokens": r["usage"]["completion_tokens"], "text_len": len(ch["text"]),
                    "finite": bool(lps) and all(x is None or math.isfinite(x) for x in lps), "wall_s": time.perf_counter() - t0}
        body |= {"stream": True, "stream_options": {"include_usage": True}}
        body.pop("logprobs")
        t0, first, last, n = time.perf_counter(), None, None, 0
        with c.stream("POST", base + "/v1/completions", json=body) as resp:
            for line in resp.iter_lines():
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                d = json.loads(line[6:])
                if d.get("choices") and d["choices"][0].get("text"):
                    t = time.perf_counter()
                    first = first or t
                    last = t
                    n += 1
        return {"ttft_ms": (first - t0) * 1000 if first else None, "chunks": n,
                "decode_tps": (n - 1) / (last - first) if first and last and last > first else None}


def prompt_of(n_words: int, seed: int) -> str:
    import numpy as np

    from quotashift.workload.generator import synthetic_prompt
    return synthetic_prompt(n_words, np.random.default_rng(seed))


def tokenizer_parity(host: str, base: str, plat: str, n: int = 60) -> dict:
    p = build_x1.PLATFORMS[plat]
    texts = [prompt_of(16 + 37 * i % 1000, 9000 + i) for i in range(n)]
    with httpx.Client(timeout=30) as c:
        srv = [c.post(base + "/tokenize", json={"model": p["model"], "prompt": t}).json()["count"] for t in texts]
    if plat.endswith("m1"):
        code = ("import json,sys,glob,os\nfrom mistral_common.tokens.tokenizers.mistral import MistralTokenizer\n"
                f"snap=os.path.expanduser('~/.cache/huggingface/hub/models--mistralai--Mistral-7B-Instruct-v0.3/snapshots/{p['revision']}')\n"
                "tok=MistralTokenizer.from_file(os.path.join(snap,'tokenizer.model.v3')).instruct_tokenizer.tokenizer\n"
                "print(json.dumps([len(tok.encode(t,bos=True,eos=False)) for t in json.load(sys.stdin)]))\n")
    else:
        code = ("import json,sys,os\nfrom transformers import AutoTokenizer\n"
                f"tok=AutoTokenizer.from_pretrained('{p['model']}', revision='{p['revision']}', local_files_only=True)\n"
                "print(json.dumps([len(tok.encode(t)) for t in json.load(sys.stdin)]))\n")
    ssh(host, "cat > $HOME/x1/parity.py", stdin=code)
    off = json.loads(ssh(host, f"HF_HUB_OFFLINE=1 {ENV_PY} $HOME/x1/parity.py", stdin=json.dumps(texts)))
    mism = [i for i, (a, b) in enumerate(zip(srv, off, strict=True)) if a != b]
    return {"ok": not mism, "n": n, "mismatches": len(mism), "examples": [(srv[i], off[i]) for i in mism[:5]],
            "offline": "mistral_common (tokenizer.model.v3, bos)" if plat.endswith("m1") else "transformers AutoTokenizer"}


# ------------------------------------------------------------------------------------------------ host sampler
def sampler_start(host: str, tag: str, duration: float = 0) -> None:
    """duration <= 0: daemon mode (periodic overhead line every 60 samples; killed by sampler_stop). duration > 0: the
    frozen sampler exits by itself and writes its {"summary": ...} line (ADR-X1-G0M0-P1-RECOVERY)."""
    # three separate ssh calls: a pkill/pgrep pattern must never match the remote shell that carries it
    ssh(host, "cat > $HOME/x1/x1_host_sampler.py", stdin=(REPO / "scripts" / "x1_host_sampler.py").read_text())
    ssh(host, "pkill -f '[x]1_host_sampler' || true")
    ssh(host, f"cd $HOME/x1; setsid nohup python3 ./x1_host_sampler.py --duration {duration:g} > telemetry_{tag}.jsonl "
              "2>&1 < /dev/null &")
    time.sleep(2)
    if not ssh(host, "pgrep -f '[x]1_host_sampler' || true").strip():
        raise RuntimeError("host sampler did not start")


def sampler_wait(host: str, timeout_s: float) -> bool:
    """Wait for a finite-duration sampler to exit on its own (so it writes its summary). False on timeout."""
    end = time.time() + timeout_s
    while time.time() < end:
        if not ssh(host, "pgrep -f '[x]1_host_sampler' || true").strip():
            return True
        time.sleep(2)
    return False


def sampler_stop(host: str, tag: str, dst: Path) -> list[dict]:
    ssh(host, "pkill -INT -f '[x]1_host_sampler' || true")
    time.sleep(1)
    ssh(host, "pkill -f '[x]1_host_sampler' || true")
    text = ssh(host, f"cat $HOME/x1/telemetry_{tag}.jsonl")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text)
    return [json.loads(x) for x in text.splitlines() if x.startswith("{")]


def window(samples: list[dict], t0: float, t1: float) -> list[dict]:
    return [s for s in samples if "ts" in s and t0 <= s["ts"] <= t1]


def overhead(samples: list[dict]) -> dict:
    """The sampler's own-CPU report: the final {"summary"} line if present (finite run), else the last periodic
    {"overhead"} line (daemon run). Both carry overhead_core_frac over the whole run so far."""
    oh = [s.get("summary") or s.get("overhead") for s in samples if "summary" in s or "overhead" in s]
    return oh[-1] if oh else {}


SAMPLER_PHASE1_S = 65      # >= 60 samples at 1 s, and the frozen sampler's summary line on exit


# ------------------------------------------------------------------------------------------------ mini-blocks
def mini_block(plat: str, rate: int, reps: int, runtime: int, tag: str, out: Path) -> dict:
    """D vs S at C = 8 through the harness (`quotashift experiment --live`), all v5 gates. Never analysed."""
    sid = f"x1_{plat}_{tag}_decode_vs_short_C8"
    text = build_x1.scenario(plat=plat, sid=sid, phase=f"preflight {tag} (never analysed)", what=f"{tag} at {rate} tok/s",
                             shape="D", load=rate, control="token_matched_fixed", cap=8, reps=reps, seed=4990,
                             traces="NONE")
    lines = [ln for ln in text.splitlines() if not ln.startswith("frozen_traces:")]
    lines = [ln.replace(f"runtime_seconds: {build_x1.RUNTIME}", f"runtime_seconds: {runtime}") for ln in lines]
    lines = [ln.replace(f"duration_seconds: {build_x1.RUNTIME}", f"duration_seconds: {runtime}")
             .replace(f"request_count: {build_x1.count('D', rate)}", f"request_count: {max(2, round(build_x1.count('D', rate) * runtime / build_x1.RUNTIME))}")
             for ln in lines]
    y = out / f"{sid}.yaml"
    y.parent.mkdir(parents=True, exist_ok=True)
    y.write_text("\n".join(lines) + "\n")
    t0 = time.time()
    r = subprocess.run([sys.executable, "-m", "quotashift.cli", "experiment", str(y), "--reps", str(reps), "--live",
                        "--path", "gateway", "--out", str(out / sid), "--results-root", str(REPO / "results"), "--force"],
                       cwd=REPO, capture_output=True, text=True)
    man = out / sid / "manifest.json"
    checks = json.loads(man.read_text())["validity"]["checks"] if man.exists() else []
    failed = [c["name"] for c in checks if c.get("severity") == "fail" and not c.get("passed")]
    flags = [c["name"] for c in checks if c.get("severity") != "fail" and not c.get("passed")]
    return {"rc": r.returncode, "t0": t0, "t1": time.time(), "rate": rate, "reps": reps, "runtime_s": runtime,
            "gates": {c["name"]: ("pass" if c.get("passed") else c.get("severity")) for c in checks},
            "failed_gates": failed, "flagged_gates": flags, "status": "pass" if r.returncode == 0 and checks and not failed else "fail",
            "stderr_tail": r.stderr[-300:] if r.returncode else ""}


# ------------------------------------------------------------------------------------------------ phases
def phase1(plat: str, host: str, anchor_tps: float | None) -> dict:
    t = active_target()
    base, model = t.backend_url.rstrip("/"), t.model
    rawdir = REPO / "reports" / "x1" / plat / "preflight"
    rawdir.mkdir(parents=True, exist_ok=True)
    rec: dict = {"started_utc": now()}
    facts = server_facts(base, model)
    launch = json.loads(ssh(host, f"cat $HOME/x1/launch_{plat}.json"))
    logtxt = ssh(host, f"cat $HOME/x1/vllm_{plat}.log")
    startup_complete = "Application startup complete" in logtxt
    errs = [ln[:200] for ln in logtxt.splitlines()
            if (" ERROR " in ln or " CRITICAL " in ln or ln.startswith("Traceback")) and "Attempted" not in ln]
    rev_ok = build_x1.PLATFORMS[plat]["revision"] in facts["server_info_text"]
    argv = argv_check(host, plat)
    env = env_sources(host)
    env["sources_match_v5_pins"] = env["sources"] == V5_SOURCE_PINS
    weights = weight_hashes(host, plat)
    smoke_gen = {sh: completion(base, model, prompt_of(60, 1 + i), build_x1.SHAPES[sh][1])
                 for i, sh in enumerate(("D", "S"))}
    smoke_gen_ok = all(v["out_tokens"] == build_x1.SHAPES[k][1] and v["finite"] and v["text_len"] > 0
                       for k, v in smoke_gen.items())
    reset = reset_and_verify(base, model, tag=f"x1-preflight-{plat}")
    parity = tokenizer_parity(host, base, plat)
    iso = __import__("asyncio").run(isolated(base, model, [prompt_of(60, 77), prompt_of(60, 78)], repeats=200))
    (rawdir / "isolated_ms.json").write_text(json.dumps(iso))
    tps = [completion(base, model, prompt_of(60, 100 + k), 256, stream=True)["decode_tps"] for k in range(5)]
    decode_tps = st.median([x for x in tps if x])
    # Sampler on/off TTFT floor (ADR-X1-G0M0-P1-RECOVERY): the same 20 prompts in both passes, each pass starting from
    # a verified-cold prefix cache, so a cache hit can never masquerade as a sampler effect.
    reset_off = reset_and_verify(base, model, tag=f"x1-ttft-off-{plat}")
    time.sleep(3)
    ttft_off = [completion(base, model, prompt_of(60, 200 + k), 8, stream=True)["ttft_ms"] for k in range(20)]
    sampler_start(host, f"{plat}_phase1", duration=SAMPLER_PHASE1_S)
    reset_on = reset_and_verify(base, model, tag=f"x1-ttft-on-{plat}")
    time.sleep(3)
    ttft_on = [completion(base, model, prompt_of(60, 200 + k), 8, stream=True)["ttft_ms"] for k in range(20)]
    tq0 = time.time()
    sampler_exited = sampler_wait(host, SAMPLER_PHASE1_S + 60)
    samples = sampler_stop(host, f"{plat}_phase1", rawdir / "telemetry_phase1.jsonl")
    (rawdir / "ttft_onoff_ms.json").write_text(json.dumps({"off": ttft_off, "on": ttft_on}))
    cold = {"status": "pass" if reset_off.get("verified") and reset_on.get("verified") else "fail",
            "reasons": [] if reset_off.get("verified") and reset_on.get("verified")
            else ["prefix cache not verified cold before a TTFT pass"],
            "reset_before_off": reset_off, "reset_before_on": reset_on, "sampler_exited_by_itself": sampler_exited}
    idle = window(samples, tq0, time.time() + 5)
    clock = clock_offset_probe(base, n=20)
    s_p = 1.0 if plat == "g0m0" else (decode_tps / anchor_tps if anchor_tps else None)
    smoke_rate = int(round(build_x1.GRID_BASE[2] * (s_p or 1.0) / 5.0)) * 5
    smoke = mini_block(plat, smoke_rate, 2, 60, "smoke", rawdir)
    checks = {
        "server_version": {"status": "pass" if facts["vllm_version"] == "0.17.1" else "fail", "value": facts["vllm_version"]},
        "env_sources": {"status": "pass" if env["sources_match_v5_pins"] else "fail", **env},
        "model_load": pf.model_load_check(healthy=True, startup_complete=startup_complete,
                                          models_lists_pinned_revision=facts["model_listed"] and rev_ok,
                                          weight_hash_ok=weights["ok"], argv_matches_template=argv["ok"],
                                          smoke_generation_ok=smoke_gen_ok, startup_s=launch["startup_s"],
                                          log_error_lines=errs),
        "kv_capacity": pf.kv_capacity_check(facts["kv_tokens"]),
        "prefix_cache": {"status": "pass" if (facts["cache_config"]["enable_prefix_caching"] in ("True", True)
                                              and str(facts["cache_config"]["block_size"]) == "16"
                                              and str(facts["cache_config"]["gpu_memory_utilization"]) in ("0.8", "0.80"))
                         else "fail", **facts["cache_config"]},
        "prefix_cache_reset": {"status": "pass" if reset.get("verified") else "fail", **reset},
        "tokenizer_parity": {"status": "pass" if parity["ok"] else "fail", **parity},
        "ram_idle": pf.ram_check(idle),
        "tokenization_isolated": pf.tokenization_check(isolated_ms=iso, peak_request_rps=0.0),
        "sampler_overhead": pf.sampler_overhead_check(overhead(samples) or {}),
        "sampler_equivalence": pf.sampler_equivalence_check([x for x in ttft_on if x], [x for x in ttft_off if x]),
        "ttft_passes_cache_cold": cold,
        "clock_offset": pf.clock_offset_check(clock.get("offset_s"), clock.get("bound_s")),
        "smoke_mini_block": smoke,
    }
    rec |= {"status": pf.combine(*(c for c in checks.values() if "status" in c)), "checks": checks,
            "decode_tps_D": decode_tps, "decode_tps_samples": tps, "speed_factor": s_p,
            "anchor_decode_tps": anchor_tps if plat != "g0m0" else decode_tps,
            "clock_offset_s": clock.get("offset_s"), "clock_bound_s": clock.get("bound_s"),
            "ttft_floor_ms": {"median_rule": "nearest-rank p50 (frozen pf.pctl, as the equivalence check)",
                              "sampler_off_median": pf.pctl([x for x in ttft_off if x], 50),
                              "sampler_on_median": pf.pctl([x for x in ttft_on if x], 50),
                              "sampler_off_ms": ttft_off, "sampler_on_ms": ttft_on},
            "finished_utc": now()}
    p1 = {"platform": plat, "model": model, "revision": build_x1.PLATFORMS[plat]["revision"],
          "vllm_version": facts["vllm_version"], "process_start_time_seconds": facts["process_start_time_seconds"],
          "argv": argv, "weights": weights, "kv_tokens": facts["kv_tokens"], "launch_startup_s": launch["startup_s"],
          "verified_by": "Claude under owner batch approval x1_local_restart (experiments/x1/approvals/)",
          "verified_utc": now()}
    return {"p1": p1, "phase1": rec}


def phase2(plat: str, host: str, rates: dict, iso_ms: list[float]) -> dict:
    t = active_target()
    base, model = t.backend_url.rstrip("/"), t.model
    rawdir = REPO / "reports" / "x1" / plat / "preflight"
    high = rates["high"]
    peak = build_x1.count("S", high) / build_x1.RUNTIME + 0.3 * 3     # control S competitor + 3 benign tenants
    sampler_start(host, f"{plat}_phase2")
    mb = mini_block(plat, high, 2, build_x1.RUNTIME, "phase2", rawdir)
    samples = sampler_stop(host, f"{plat}_phase2", rawdir / "telemetry_phase2.jsonl")
    off = 0.0
    hv = X1 / plat / "HOST_VERIFICATION.json"
    if hv.exists():
        off = json.loads(hv.read_text())["preflight"]["phase1"].get("clock_offset_s") or 0.0
    win = window(samples, mb["t0"] + off, mb["t1"] + off)
    b = __import__("asyncio").run(burst(base, model, [prompt_of(60, 77), prompt_of(60, 78)], rate_rps=10 * peak,
                                        seconds=30))
    checks = {
        "cpu_under_high_load": pf.cpu_check(win, preflight=True),
        "ram_under_load": pf.ram_check(win),
        "sampler_overhead": pf.sampler_overhead_check(overhead(samples) or {}),
        "tokenization_capacity": pf.tokenization_check(isolated_ms=iso_ms, peak_request_rps=peak,
                                                       burst_offered_rps=b["offered_rps"],
                                                       burst_achieved_rps=b["achieved_rps"], burst_ms=b["latencies_ms"]),
        "high_load_mini_block": mb,
    }
    return {"status": pf.combine(*(c for c in checks.values() if "status" in c)), "checks": checks,
            "high_rate": high, "peak_request_rps": peak, "burst": {k: v for k, v in b.items() if k != "latencies_ms"},
            "finished_utc": now()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("phase", choices=("phase1", "phase2"))
    ap.add_argument("--platform", choices=("g0m0", "g0m1"), required=True)
    ap.add_argument("--host", required=True)
    a = ap.parse_args()
    out = X1 / a.platform / "HOST_VERIFICATION.json"
    if a.phase == "phase1":
        anchor = None
        if a.platform != "g0m0":
            av = X1 / "g0m0" / "HOST_VERIFICATION.json"
            if not av.exists():
                print("REFUSED: the G0 anchor (g0m0) Phase 1 is needed for the speed factor s_p", file=sys.stderr)
                return 3
            anchor = json.loads(av.read_text())["preflight"]["phase1"]["decode_tps_D"]
        r = phase1(a.platform, a.host, anchor)
        doc = {"platform": a.platform, "p1": r["p1"], "preflight": {"phase1": r["phase1"]}}
    else:
        doc = json.loads(out.read_text())
        rates = json.loads((X1 / a.platform / "RATES.json").read_text())
        iso_ms = json.loads((REPO / "reports" / "x1" / a.platform / "preflight" / "isolated_ms.json").read_text())
        doc["preflight"]["phase2"] = phase2(a.platform, a.host, rates, iso_ms)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, indent=1, default=str)
    import re
    text = re.sub(r"/home/[A-Za-z0-9_.-]+", "~", text)                                   # no home paths
    text = re.sub(r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))(?:\.\d{1,3}){2,3}\b", "<rfc1918>", text)   # no LAN addresses
    out.write_text(text + "\n")
    st_ = doc["preflight"][a.phase]["status"]
    print(f"{a.platform} {a.phase}: {st_}")
    return 0 if st_ in ("pass", "flag") else 4


if __name__ == "__main__":
    raise SystemExit(main())
