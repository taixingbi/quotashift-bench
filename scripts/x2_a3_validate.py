"""X2 Amendment A3 offline validation (no GPU, no AWS, no network beyond 127.0.0.1).

    uv run --with sentencepiece python scripts/x2_a3_validate.py --sp-model <tokenizer.model.v3> \
        --out reports/x2_a3/A3_OFFLINE_VALIDATION.json

A local mock vLLM `/tokenize` + `/v1/completions` server is backed by the pinned Mistral-7B-Instruct-v0.3 SentencePiece
model (BOS + encode, which equals live sequential /tokenize for 464 + 212 texts in the g1m1 diagnostics). It can inject
the observed artifact: a trailing EOS (id 2) on a /tokenize response whenever another request is in flight, either
another /tokenize ("tokenize") or any request including generation ("any"). The fault model is an OFFLINE MODEL of the
live behaviour, not the live server; nothing here proves the server-side mechanism.

Rows (all 36 g1m1 calibration-A scenario-seeds = 6 grid files + 6 rerun files x 3 seeds, the committed YAMLs):
  F16-fault   frozen 16-worker counter, artifact injected      -> expected REFUSED (reproduces the live refusal)
  F16-clean   frozen 16-worker counter, clean mock              -> expected pass (counter logic itself is sound)
  A3-fault    A3 sequential counter, artifact injected          -> expected pass, 0 guard trips
  A3-clean    A3 sequential counter, clean mock (x2 runs)        -> expected pass, digests == A3-fault
  SP-direct   in-process SentencePiece count, no HTTP            -> digests == A3 (HTTP path adds nothing)
  RT-presend  runtime pre-send path of run_matched_pairs per scenario-seed, fresh A3 counter, against the A3-fault
              freeze: paired_traces + check_frozen + exact verify_trace (attack budget view and control)
  A3-ext      A3 counter, artifact on ANY concurrency, with concurrent external /v1/completions traffic
              -> expected fail closed (guard trips), never a silent miscount
  A3-quiet    A3 counter, artifact on ANY concurrency, no external traffic -> expected pass
  MAIN-hyp    HYPOTHETICAL A2 main files at every calA grid rate (temp dir, not a rate selection), A3 counter vs the
              injected artifact, frozen A2 freeze path -> expected pass
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))
SP_SHA256 = "37f00374dea48658ee8f5d0f21895b9bc55cb0103939607c8185bfd1c6ca1f89"
MODEL = "mistralai/Mistral-7B-Instruct-v0.3"
PLAT = "g1m1"
H = lambda s: hashlib.sha256(s.encode()).hexdigest()  # noqa: E731


class Mock:
    def __init__(self, sp, fault: str = "none", delay_s: float = 0.0005) -> None:  # noqa: ANN001
        self.sp, self.fault, self.delay = sp, fault, delay_s
        self.lock = threading.Lock()
        self.inflight = {"tokenize": 0, "all": 0}
        self.injected = 0
        self.max_tok_inflight = 0
        mock = self

        class Hd(BaseHTTPRequestHandler):
            def log_message(self, *a) -> None:  # noqa: ANN002
                pass

            def do_POST(self) -> None:  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                out = mock.handle(self.path, body)
                b = json.dumps(out).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Hd)
        self.srv.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def ids(self, text: str) -> list[int]:
        return [1, *self.sp.encode(text)]

    def handle(self, path: str, body: dict) -> dict:
        tok = path == "/tokenize"
        with self.lock:
            self.inflight["all"] += 1
            self.inflight["tokenize"] += tok
            self.max_tok_inflight = max(self.max_tok_inflight, self.inflight["tokenize"])
        try:
            ids = self.ids(body["prompt"])
            if self.delay:
                time.sleep(self.delay)
            with self.lock:
                others = (self.inflight["tokenize"] - 1) if self.fault == "tokenize" else (self.inflight["all"] - 1)
            if tok:
                if self.fault != "none" and others > 0:
                    ids = [*ids, 2]
                    with self.lock:
                        self.injected += 1
                return {"count": len(ids), "max_model_len": 4096, "tokens": ids}
            return {"usage": {"prompt_tokens": len(ids), "completion_tokens": 1}, "choices": [{"text": "x"}]}
        finally:
            with self.lock:
                self.inflight["all"] -= 1
                self.inflight["tokenize"] -= tok

    def close(self) -> None:
        self.srv.shutdown()


def traces_digest(traces: dict) -> str:
    return H(json.dumps(traces["scenarios"], sort_keys=True))


def run_freeze(count, phase: str = "calA", root: Path | None = None) -> dict:  # noqa: ANN001
    import freeze_x2_traces as fx

    t0 = time.time()
    try:
        if phase == "main":  # the frozen A2 freeze path minus its provenance block (which needs a real RATES.json)
            from quotashift.x2.arrivals_a2 import a2_loader

            with a2_loader():
                sched, traces = fx.freeze(PLAT, "main", count, getattr(count, "identity", {}), root=root)
        else:
            sched, traces = fx.freeze(PLAT, phase, count, getattr(count, "identity", {}))
    except (Exception, SystemExit) as e:  # noqa: BLE001  (a refusal is a result here)
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}", "wall_s": time.time() - t0,
                "calls": getattr(count, "calls", None), "guard_trips": getattr(count, "guard_trips", None)}
    return {"ok": True, "wall_s": time.time() - t0, "calls": getattr(count, "calls", None),
            "guard_trips": getattr(count, "guard_trips", None), "traces_digest": traces_digest(traces),
            "schedule_digest": H(json.dumps(sched["scenarios"], sort_keys=True)),
            "scenario_seeds": sum(len(v["seeds"]) for v in traces["scenarios"].values()),
            "_traces": traces, "_sched": sched}


def conservation(traces: dict, root: Path | None = None, a2: bool = False) -> dict:
    """Calibrated vs raw plan, per scenario-seed and arm: request count, planned token sums, schedule, seeds."""
    import freeze_v5

    import quotashift.scenario as qs
    from quotashift.local import _paired_traces_raw

    ctx = contextlib.nullcontext()
    if a2:
        from quotashift.x2.arrivals_a2 import a2_loader
        ctx = a2_loader()
    bad: list[str] = []
    n = 0
    with ctx:
        for sid, ent in traces["scenarios"].items():
            sc = qs.load_scenario(REPO / ent["file"])  # resolved inside the context: A2 files use the A2 loader
            if ent["seeds"] != list(range(sc.seed, sc.seed + sc.comparison.repetitions)):
                bad.append(f"{sid}: seeds {ent['seeds']}")
            for s in ent["seeds"]:
                n += 1
                atk, ctl, _ = _paired_traces_raw(sc, s)
                for arm, raw in (("attack", atk), ("control", ctl)):
                    r = ent[str(s)][arm]
                    if r["requests"] != len(raw):
                        bad.append(f"{sid} {s} {arm}: requests {r['requests']} != raw {len(raw)}")
                    auth = sum(i.request.input_token_count + i.request.max_output_tokens for i in raw)
                    if r["authorized_tokens"] != auth:
                        bad.append(f"{sid} {s} {arm}: authorized tokens {r['authorized_tokens']} != raw {auth}")
                    planned_in = sum(i.request.input_token_count for i in raw)
                    if r["tokenized_input"] != planned_in:
                        bad.append(f"{sid} {s} {arm}: tokenized input {r['tokenized_input']} != planned {planned_in}")
                    _ = freeze_v5  # schedule equality is enforced inside the frozen freeze (raises on change)
    return {"scenario_seeds_checked": n, "problems": bad, "ok": not bad}


def runtime_presend(frozen: dict, url: str) -> dict:
    """The pre-send loop of quotashift.local.run_matched_pairs, verbatim in effect, with a fresh A3 counter."""
    from quotashift.local import budget_view, check_frozen, paired_traces
    from quotashift.scenario import load_scenario
    from quotashift.workload import tokenize as T

    out: dict = {"scenario_seeds": 0, "verify_ok": 0, "frozen_match": 0, "calls": 0, "guard_trips": 0, "wall_s": 0.0,
                 "counter_class": None, "errors": []}
    t0 = time.time()
    for _sid, ent in frozen["scenarios"].items():
        sc = load_scenario(REPO / ent["file"])
        count = T.VllmTokenizer(url, MODEL)  # resolved at call time, exactly like local.py:153
        out["counter_class"] = type(count).__name__
        for s in ent["seeds"]:
            out["scenario_seeds"] += 1
            try:
                a_tr, c_tr, _ = paired_traces(sc, s, count)
                check_frozen(frozen, sc, s, a_tr, c_tr)
                out["frozen_match"] += 1
                reps = [T.verify_trace(tr, count, max_model_len=sc.model_max_len,
                                       exact=sc.prompt_token_unit == "tokenizer", label=f"{arm} seed {s}")
                        for arm, tr in (("attack", budget_view(sc, a_tr, s)), ("control", c_tr))]
                out["verify_ok"] += all(r["ok"] and r["exact_required"] for r in reps)
            except (Exception, SystemExit) as e:  # noqa: BLE001
                out["errors"].append(f"{sc.scenario_id} {s}: {type(e).__name__}: {str(e)[:200]}")
        out["calls"] += count.calls
        out["guard_trips"] += getattr(count, "guard_trips", 0)
    out["wall_s"] = time.time() - t0
    return out


def tokenization_only(root: Path, url: str) -> dict:
    """Every A2 main scenario-seed under root: frozen calibrate + exact verify_trace with the A3 counter, NO other gate.
    Used only where the frozen freeze refused on a non-tokenization gate, to show tokenization alone is exact."""
    import freeze_x2_traces as fx

    import quotashift.scenario as qs
    from quotashift.local import budget_view, paired_traces
    from quotashift.workload import tokenize as T
    from quotashift.x2.arrivals_a2 import a2_loader

    out: dict = {"scenario_seeds": 0, "verify_ok": 0, "errors": [], "calls": 0, "guard_trips": 0}
    count = T.VllmTokenizer(url, MODEL)
    with a2_loader():
        for f in fx.phase_files(PLAT, "main", root):
            sc = qs.load_scenario(f)
            for s in range(sc.seed, sc.seed + sc.comparison.repetitions):
                out["scenario_seeds"] += 1
                try:
                    a_tr, c_tr, _ = paired_traces(sc, s, count)
                    out["verify_ok"] += all(T.verify_trace(tr, count, max_model_len=sc.model_max_len, exact=True)["ok"]
                                            for tr in (budget_view(sc, a_tr, s), c_tr))
                except (Exception, SystemExit) as e:  # noqa: BLE001
                    out["errors"].append(f"{sc.scenario_id} {s}: {type(e).__name__}: {str(e)[:200]}")
    out["calls"], out["guard_trips"] = count.calls, count.guard_trips
    out["ok"] = out["verify_ok"] == out["scenario_seeds"] and not out["errors"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sp-model", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    import sentencepiece as spm

    spb = Path(a.sp_model).read_bytes()
    if hashlib.sha256(spb).hexdigest() != SP_SHA256:
        print("REFUSED: SentencePiece model is not the pinned tokenizer.model.v3", file=sys.stderr)
        return 3
    sp = spm.SentencePieceProcessor(model_file=a.sp_model)
    assert (sp.bos_id(), sp.eos_id()) == (1, 2)
    from quotashift.workload import tokenize as T
    from quotashift.workload import tokenize_a3 as A3

    A3.uninstall()
    R: dict = {"label": "X2-A3 OFFLINE VALIDATION (mock server backed by the pinned tokenizer; not a live result)",
               "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                                          text=True).stdout.strip(),
               "git_dirty_paths": subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True,
                                                 text=True).stdout.splitlines(),
               "python": sys.version.split()[0], "sentencepiece": spm.__version__,
               "sp_model_sha256": SP_SHA256, "model": MODEL, "rows": {}}
    rows = R["rows"]

    def with_mock(fault: str, fn, delay: float = 0.0005):  # noqa: ANN001, ANN202
        m = Mock(sp, fault, delay)
        t0 = time.time()
        try:
            r = fn(m)
        finally:
            m.close()
        print(f"[{time.strftime('%H:%M:%S')}] row done: fault={fault} ok={r.get('ok', r.get('verify_ok'))} "
              f"{time.time() - t0:.0f}s calls={r.get('calls')}", file=sys.stderr, flush=True)
        return r | {"mock": {"fault": fault, "injected": m.injected, "max_tokenize_inflight": m.max_tok_inflight,
                             "delay_s": delay}}

    rows["F16-fault"] = with_mock("tokenize", lambda m: run_freeze(T.VllmTokenizer(m.url, MODEL)))
    rows["F16-clean"] = with_mock("none", lambda m: run_freeze(T.VllmTokenizer(m.url, MODEL)))
    A3.install()
    rows["A3-fault"] = with_mock("tokenize", lambda m: run_freeze(T.VllmTokenizer(m.url, MODEL)))
    rows["A3-clean"] = with_mock("none", lambda m: run_freeze(T.VllmTokenizer(m.url, MODEL)))
    rows["A3-clean-2"] = with_mock("none", lambda m: run_freeze(T.VllmTokenizer(m.url, MODEL)))

    class SP:
        identity = {"kind": "offline sentencepiece (validation reference)"}
        calls = 0

        def __call__(self, texts):  # noqa: ANN001, ANN204
            self.calls += len(texts)
            return [1 + len(sp.encode(t)) for t in texts]

    rows["SP-direct"] = run_freeze(SP())
    frozen = rows["A3-fault"].get("_traces")
    if frozen is not None:
        rows["CONSERVATION"] = conservation(frozen)
        rows["RT-presend"] = with_mock("tokenize", lambda m: runtime_presend(frozen, m.url))

    def ext(m) -> dict:  # noqa: ANN001
        stop = threading.Event()

        def hammer() -> None:
            import httpx
            c = httpx.Client(timeout=10)
            while not stop.is_set():
                c.post(m.url + "/v1/completions", json={"model": MODEL, "prompt": "background tenant", "max_tokens": 1})

        ths = [threading.Thread(target=hammer, daemon=True) for _ in range(4)]
        for t in ths:
            t.start()
        try:
            return run_freeze(T.VllmTokenizer(m.url, MODEL))
        finally:
            stop.set()
            for t in ths:
                t.join(5)

    rows["A3-ext"] = with_mock("any", ext)
    rows["A3-quiet"] = with_mock("any", lambda m: run_freeze(T.VllmTokenizer(m.url, MODEL)))

    import build_x2_a2

    hyp: dict = {}
    for rate in (5, 10, 25, 55, 95, 140):
        (REPO / "results").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="x2_a3_tmp_", dir=REPO / "results") as td:  # git-ignored
            root = Path(td)
            for rel, text in build_x2_a2.build_main_a2(PLAT, {"low": rate, "low_feasible": True}).items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text)
            r = with_mock("tokenize", lambda m, root=root: run_freeze(T.VllmTokenizer(m.url, MODEL), "main", root))
            if r.get("ok"):
                r["conservation"] = conservation(r["_traces"], a2=True)
            else:  # the freeze stops at its first gate refusal; count every scenario-seed directly (tokenization only)
                r["tokenization_only"] = with_mock("tokenize", lambda m, root=root: tokenization_only(root, m.url))
            hyp[str(rate)] = {k: v for k, v in r.items() if not k.startswith("_")}
    rows["MAIN-hyp"] = hyp
    A3.uninstall()

    for k in list(rows):
        if isinstance(rows[k], dict):
            rows[k] = {x: y for x, y in rows[k].items() if not x.startswith("_")}
    d = {k: rows[k].get("traces_digest") for k in ("A3-fault", "A3-clean", "A3-clean-2", "SP-direct", "F16-clean")}
    ex = {
        "F16-fault refused (reproduces live)": not rows["F16-fault"]["ok"],
        "F16-clean passes": rows["F16-clean"]["ok"],
        "A3-fault passes with 0 guard trips and 0 injected artifacts": rows["A3-fault"]["ok"]
        and rows["A3-fault"]["guard_trips"] == 0 and rows["A3-fault"]["mock"]["injected"] == 0,
        "A3 max /tokenize in flight == 1": rows["A3-fault"]["mock"]["max_tokenize_inflight"] == 1,
        "36 calA scenario-seeds": rows["A3-fault"].get("scenario_seeds") == 36,
        "digests identical: A3-fault == A3-clean == A3-clean-2 == SP-direct == F16-clean": len(set(d.values())) == 1
        and None not in d.values(),
        "schedules identical across counters": len({rows[k].get("schedule_digest") for k in
                                                    ("A3-fault", "A3-clean", "SP-direct", "F16-clean")}) == 1,
        "conservation (requests, authorized tokens, tokenized == planned, seeds)": rows.get("CONSERVATION", {}).get("ok"),
        "runtime pre-send: 36/36 frozen match + exact verify, 0 trips": rows.get("RT-presend", {}).get("verify_ok") == 36
        and rows["RT-presend"]["frozen_match"] == 36 and rows["RT-presend"]["guard_trips"] == 0
        and rows["RT-presend"]["counter_class"] == "SequentialMistralTokenizer",
        "A3-ext fails closed (guard trip, no silent miscount)": not rows["A3-ext"]["ok"]
        and (rows["A3-ext"]["guard_trips"] or 0) > 0,
        "A3-quiet passes": rows["A3-quiet"]["ok"],
        # Corrected after run 1 (reports/x2_a3/A3_OFFLINE_VALIDATION_run1.json): run 1 required the whole frozen A2 main
        # freeze to pass at every grid rate, which conflates tokenization with the A2 arrival-coverage gate; at 5 tok/s
        # (N_D = 2) that gate refuses by design (docs/PROTOCOL_X2_AMENDMENT_A2.md section 5). A3 is judged on tokenization.
        "MAIN-hyp: A3 tokenization exact for every scenario-seed at every grid rate, 0 trips, 0 injections": all(
            v["guard_trips"] == 0 and v["mock"]["injected"] == 0 and (
                (v["ok"] and v["conservation"]["ok"]) or (v.get("tokenization_only") or {}).get("ok", False))
            for v in hyp.values()),
        "MAIN-hyp: any freeze refusal is the documented A2 coverage gate only": all(
            v["ok"] or str(v.get("error", "")).startswith("SystemExit: arrival coverage gate would fail") for v in hyp.values()),
    }
    R["digests"] = d
    R["expectations"] = ex
    R["all_expectations_met"] = all(bool(v) for v in ex.values())
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(R, indent=1, default=str) + "\n")
    for k, v in ex.items():
        print(f"{'PASS' if v else 'FAIL'}  {k}")
    print("ALL EXPECTATIONS MET" if R["all_expectations_met"] else "EXPECTATIONS NOT MET")
    return 0 if R["all_expectations_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
