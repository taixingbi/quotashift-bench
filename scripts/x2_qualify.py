"""X2 per-platform qualification driver: Phase 1, Q0 (host stability, reported) and Q1 (instrumentation invariance,
gate). docs/X2_INSTRUMENTATION_SPEC.md sections 5-6. NOT frozen; live use needs X2 Freeze Commit 1 and its own token.

    QUOTASHIFT_TARGET=x2-g0-qwen QUOTASHIFT_X2_SSH_HOST=<ssh alias> QUOTASHIFT_APPROVED=x2_qual_g0m0 \
        uv run python scripts/x2_qualify.py --platform g0m0 --live
    uv run python scripts/x2_qualify.py --platform g0m0 --mock --out-root /tmp/x2q       # plumbing only (no server)

Phase 1 (fail -> not admissible): identity (vLLM 0.17.1, model listed, server-reported revision, prefix caching on,
KV >= 20,480 tokens), verified /reset_prefix_cache, smoke generation (S and D lengths exact), the platform's own
isolated S and D hold times (20 each, cold cache; S mean -> the calibration-A grid), runner->server HTTP RTT, and one
boundary snapshot (resident-process inventory; recorded for every later inventory comparison).
Q0 / Q1: qualification.q0_order / q1_order segments; each segment = state (P: production before-snapshot, N: idle
wait of the same length) -> GUARD_S -> verified reset -> warm-ups -> M measured requests with the v5 /metrics poller
running at its production interval -> state (P: after-snapshot, N: idle wait). Q1 decides by qualification.q1_decide.
One run per platform: refuses if experiments/x2/<plat>/QUALIFICATION.json exists. No retry.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics as st
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_x2  # noqa: E402

from quotashift.x2 import qualification as q  # noqa: E402
from quotashift.x2 import snapshot as snap  # noqa: E402

X2 = REPO / "experiments" / "x2"
KV_MIN_TOKENS = 20480
HOLD_PROBES, HOLD_SEED_S, HOLD_SEED_D = 20, 21100, 21120
RTT_PROBES = 20
METRICS_POLL_S = 0.5                      # the harness's production /metrics interval (config.RunConfig.metrics_interval_s)


def now() -> str:
    return datetime.now(UTC).isoformat()


def prompt_of(n_words: int, seed: int) -> str:
    import numpy as np

    from quotashift.workload.generator import synthetic_prompt
    return synthetic_prompt(n_words, np.random.default_rng(seed))


# ------------------------------------------------------------------------------------------------ live primitives
class Live:
    def __init__(self, base: str, model: str) -> None:
        self.base, self.model = base.rstrip("/"), model

    def ttft(self, prompt: str) -> float | None:
        import httpx
        body = {"model": self.model, "prompt": prompt, "max_tokens": q.MAX_TOKENS, "temperature": 0.0,
                "ignore_eos": True, "stream": True}
        try:
            with httpx.Client(timeout=120) as c:
                t0 = time.perf_counter()
                with c.stream("POST", self.base + "/v1/completions", json=body) as r:
                    for line in r.iter_lines():
                        if line.startswith("data: ") and line != "data: [DONE]":
                            d = json.loads(line[6:])
                            if d.get("choices") and d["choices"][0].get("text"):
                                return (time.perf_counter() - t0) * 1000
        except (httpx.HTTPError, json.JSONDecodeError):
            return None
        return None

    def hold(self, prompt: str, max_tokens: int) -> tuple[float, int]:
        import httpx
        t0 = time.perf_counter()
        r = httpx.post(self.base + "/v1/completions", json={"model": self.model, "prompt": prompt, "max_tokens": max_tokens,
                                                            "temperature": 0.0, "ignore_eos": True}, timeout=120).json()
        return time.perf_counter() - t0, int(r["usage"]["completion_tokens"])

    def reset(self, tag: str) -> dict:
        from quotashift.instrumentation.cache_reset import reset_and_verify
        return reset_and_verify(self.base, self.model, tag=tag)

    def poll_metrics(self) -> None:
        import httpx
        try:
            httpx.get(self.base + "/metrics", timeout=5)
        except httpx.HTTPError:
            pass

    def rtt_ms(self) -> float:
        import httpx
        t0 = time.perf_counter()
        httpx.get(self.base + "/health", timeout=10)
        return (time.perf_counter() - t0) * 1000

    def facts(self) -> dict:
        import httpx

        from quotashift.instrumentation.prom import parse_prometheus_text, resolve
        with httpx.Client(timeout=20) as c:
            ver = c.get(self.base + "/version").json().get("version")
            models = [m["id"] for m in c.get(self.base + "/v1/models").json()["data"]]
            si = c.get(self.base + "/server_info")
            met = resolve(parse_prometheus_text(c.get(self.base + "/metrics").text))
        cc = met.info.get("vllm:cache_config_info") or {}
        return {"vllm_version": ver, "model_listed": self.model in models,
                "server_info_text": json.dumps(si.json()) if si.status_code == 200 else "",
                "process_start_time_seconds": met.values.get("process_start_time_seconds"),
                "prefix_caching": str(cc.get("enable_prefix_caching")) in ("True", "true"),
                "kv_tokens": int(float(cc.get("num_gpu_blocks", 0))) * int(float(cc.get("block_size", 0)))}


# ------------------------------------------------------------------------------------------------ procedure
def segment(io, take: Callable[[], dict], state: str, label: str, *, m: int, guard_s: float,  # noqa: ANN001
            sleep: Callable[[float], None], idle_s: float) -> dict:
    """One qualification segment. state P = production snapshot procedure; N (and Q0's a/b) = same idle time, no snapshot."""
    t_state0 = time.monotonic()
    before = take() if state == "P" else None
    state_s = time.monotonic() - t_state0
    if state != "P":
        sleep(idle_s)
    sleep(guard_s)
    reset = io.reset(f"x2-q-{label}")
    for s in q.WARMUP_SEEDS:
        io.ttft(prompt_of(q.PROMPT_WORDS, s))
    stop = threading.Event()

    def poller() -> None:
        while not stop.wait(METRICS_POLL_S):
            io.poll_metrics()
    th = threading.Thread(target=poller, daemon=True)
    th.start()
    t0 = time.time()
    ttft = [io.ttft(prompt_of(q.PROMPT_WORDS, s)) for s in q.prompt_seeds(m)]
    t1 = time.time()
    stop.set()
    th.join(timeout=5)
    after = take() if state == "P" else None
    if state != "P":
        sleep(idle_s)
    rec = {"label": label, "state": state, "ttft_ms": ttft, "reset_verified": bool(reset.get("verified")),
           "t_start": t0, "t_end": t1, "state_s": state_s,
           "procedure_ok": (before is not None and after is not None) if state == "P" else True}
    if state == "P" and before and after:
        rec["snapshot_metrics"] = snap.arm_metrics(before, after)
    return rec


def run_q(io, take, order: list[tuple[int, str]], *, m: int, guard_s: float, sleep, tag: str, log=print) -> list[dict]:  # noqa: ANN001
    segs, idle = [], 1.0
    for i, (k, arm) in enumerate(order):
        state = "P" if arm == "P" else "N"
        r = segment(io, take, state, f"{tag}-{k}-{arm}", m=m, guard_s=guard_s, sleep=sleep, idle_s=idle)
        if state == "P":
            idle = max(0.5, r["state_s"])                       # N waits as long as the last real snapshot took
        r |= {"pair": k, "arm": arm, "position": i}
        segs.append(r)
        good = [x for x in r["ttft_ms"] if x is not None]
        log(f"[{datetime.now().strftime('%H:%M:%S')}] {tag} segment {i + 1}/{len(order)} pair {k} {arm}: "
            f"p50 {q.pctl50(good) if good else float('nan'):.2f} ms, n {len(good)}, reset {r['reset_verified']}")
    return segs


def phase1(io, take, plat: str) -> dict:  # noqa: ANN001
    exp = build_x2.PLATFORMS[plat]
    f = io.facts()
    reset = io.reset(f"x2-p1-{plat}")
    smoke = {sh: io.hold(prompt_of(60, 1 + i), build_x2.SHAPES[sh][1]) for i, sh in enumerate(("S", "D"))}
    io.reset(f"x2-p1-hold-{plat}")
    hold_s = [io.hold(prompt_of(60, HOLD_SEED_S + i), build_x2.SHAPES["S"][1])[0] for i in range(HOLD_PROBES)]
    hold_d = [io.hold(prompt_of(60, HOLD_SEED_D + i), build_x2.SHAPES["D"][1])[0] for i in range(HOLD_PROBES)]
    rtt = [io.rtt_ms() for _ in range(RTT_PROBES)]
    inv = take()
    checks = {
        "vllm_version": f["vllm_version"] == "0.17.1", "model_listed": f["model_listed"],
        "revision_server_reported": exp["revision"] in f["server_info_text"], "prefix_caching": f["prefix_caching"],
        "kv_capacity": f["kv_tokens"] >= KV_MIN_TOKENS, "cache_reset_verified": bool(reset.get("verified")),
        "smoke_lengths": all(smoke[sh][1] == build_x2.SHAPES[sh][1] for sh in smoke),
        "hold_probes_finite": all(math.isfinite(x) and x > 0 for x in hold_s + hold_d),
    }
    return {"status": "pass" if all(checks.values()) else "fail", "checks": checks, "facts":
            {k: v for k, v in f.items() if k != "server_info_text"}, "hold_s_mean": st.mean(hold_s),
            "hold_s_samples": hold_s, "hold_d_mean": st.mean(hold_d), "rtt_ms": {"median": st.median(rtt), "max": max(rtt),
                                                                              "samples": rtt},
            "inventory": inv.get("inventory"), "inventory_sha256": inv.get("inventory_sha256"),
            "snapshot_transport_ok": True}


def qualify(io, take, plat: str, *, sleep=time.sleep, guard_s: float = q.GUARD_S, m: int = q.M_PER_SEGMENT,  # noqa: ANN001
            k: int = q.K_PAIRS, k0: int = q.K0_PAIRS, log=print) -> dict:
    rec: dict = {"platform": plat, "started_utc": now(), "design": {"test": q.TEST, "ci_level": q.CI_LEVEL, "K": k, "M": m,
                 "K0": k0, "warmup": q.WARMUP, "guard_s": guard_s}}
    rec["phase1"] = phase1(io, take, plat)
    log(f"phase 1: {rec['phase1']['status']} (hold S {rec['phase1']['hold_s_mean']:.3f} s)")
    if rec["phase1"]["status"] != "pass":
        return rec | {"status": "fail", "reason": "phase 1", "finished_utc": now()}
    q0 = run_q(io, take, q.q0_order(k0), m=m, guard_s=guard_s, sleep=sleep, tag="Q0", log=log)
    q1 = run_q(io, take, q.q1_order(k), m=m, guard_s=guard_s, sleep=sleep, tag="Q1", log=log)
    rec["q0"] = q.q0_describe(q0, k0=k0, m=m)
    rec["q1"] = q.q1_decide(q1, k=k, m=m)
    rec["segments"] = {"q0": q0, "q1": q1}
    return rec | {"status": rec["q1"]["status"], "finished_utc": now()}


def live_problems(plat: str) -> list[str]:
    p = []
    tok = f"x2_qual_{plat}"
    if os.environ.get("QUOTASHIFT_APPROVED") != tok:
        p.append(f"QUOTASHIFT_APPROVED must be {tok}")
    chk = subprocess.run([sys.executable, str(REPO / "scripts" / "pin_x2.py"), "--check"], cwd=REPO,
                         capture_output=True, text=True)
    if chk.returncode:
        p.append(f"X2 Freeze Commit 1 not in place or pins changed: {chk.stdout.strip()[-200:]}")
    if (X2 / plat / "QUALIFICATION.json").exists():
        p.append(f"{plat}: qualification already recorded (one run per platform; no retry)")
    st_ = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    if st_:
        p.append("git tree not clean")
    return p


class Mock:
    """Plumbing only (no server): deterministic synthetic timings, marked synthetic."""
    def __init__(self) -> None:
        self.n = 0

    def ttft(self, prompt: str) -> float:  # noqa: ARG002
        self.n += 1
        return 50.0 + (self.n * 7919 % 100) / 100.0

    def hold(self, prompt: str, max_tokens: int) -> tuple[float, int]:  # noqa: ARG002
        return 1.3 + max_tokens / 1000.0, max_tokens

    def reset(self, tag: str) -> dict:  # noqa: ARG002
        return {"verified": True}

    def poll_metrics(self) -> None:
        return None

    def rtt_ms(self) -> float:
        return 1.0

    def facts(self) -> dict:
        return {"vllm_version": "0.17.1", "model_listed": True, "server_info_text": " ".join(
            p["revision"] for p in build_x2.PLATFORMS.values()), "process_start_time_seconds": 1.0,
            "prefix_caching": True, "kv_tokens": 65536}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", choices=tuple(build_x2.PLATFORMS), required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--live", action="store_true")
    g.add_argument("--mock", action="store_true")
    ap.add_argument("--out-root", help="mock only: output directory outside the repository")
    a = ap.parse_args()
    if a.mock:
        out = Path(a.out_root or "")
        if not a.out_root or out.resolve() == REPO or REPO in out.resolve().parents:
            print("REFUSED: mock output needs --out-root outside the repository", file=sys.stderr)
            return 3
        rec = qualify(Mock(), snap.take_mock, a.platform, sleep=lambda s: None, guard_s=0.0, k=4, k0=2, m=5)
        rec["synthetic"] = True
        out.mkdir(parents=True, exist_ok=True)
        (out / f"QUALIFICATION_{a.platform}.json").write_text(json.dumps(rec, indent=1, default=str) + "\n")
        print(f"mock {a.platform}: {rec['status']} (synthetic; plumbing only)")
        return 0
    probs = live_problems(a.platform)
    ok = sys.stdin.isatty() and input(f"Type 'yes' to run X2 qualification for {a.platform} live: ").strip() == "yes"
    if not ok:
        probs.append("operator did not confirm interactively")
    if probs:
        print("REFUSED:\n  " + "\n  ".join(probs), file=sys.stderr)
        return 3
    from quotashift.targets import active_target
    t = active_target()
    if not t.name.startswith("x2-") or t.model != build_x2.PLATFORMS[a.platform]["model"]:
        print(f"REFUSED: active target {t.name} is not the X2 target of {a.platform}", file=sys.stderr)
        return 3
    sys.path.insert(0, str(REPO / "scripts"))
    import x2_stage
    take = snap.taker(x2_stage.boundary_config(a.platform, mode="live"))
    rec = qualify(Live(t.backend_url, t.model), take, a.platform)
    raw = REPO / "reports" / "x2" / a.platform / "qualification"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "segments.json").write_text(json.dumps(rec.get("segments"), default=str))
    rec.pop("segments", None)
    (X2 / a.platform).mkdir(parents=True, exist_ok=True)
    (X2 / a.platform / "QUALIFICATION.json").write_text(json.dumps(rec, indent=1, default=str) + "\n")
    print(f"{a.platform} qualification: {rec['status']}")
    return 0 if rec["status"] == "pass" else 4


if __name__ == "__main__":
    raise SystemExit(main())
