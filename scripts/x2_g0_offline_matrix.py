"""X2 G0 offline readiness matrix (HYPOTHETICAL inputs; zero cost; no GPU, no AWS, no host access).

    uv run --with sentencepiece python scripts/x2_g0_offline_matrix.py --sp-model reports/x2_a3/ref/tokenizer.model.v3 \
        --out reports/x2_g0/G0_OFFLINE_MATRIX.json

G0 has not been qualified, so its isolated hold time (which fixes the calA grid) and its selected low rate are
unknown. This script never chooses either: it sweeps hold times and evaluates EVERY grid rate those holds produce as a
hypothetical low rate, using only the frozen generators and the frozen offline gates. Nothing it writes is canonical:
files go to a git-ignored temp dir under results/ and are deleted.

  A  analytic, every rate 5..1000 tok/s: decode (D) count, token-matched control (S) count, A/A S count; whether the A2
     stratified law GUARANTEES the frozen coverage gate (min count >= 4); per-arm pass probability otherwise.
  B  calA, per hold in HOLDS and platform: frozen build_x2 calA files + frozen offline calA freeze (whitespace stand-in)
  C  main, per candidate rate and platform: frozen build_x2 main + A2 generator, then per file and seed the A2
     validator's checks (coverage, one-per-stratum, conservation vs original, victims paired, budget matched, A/A
     independent, deterministic) and the frozen offline main freeze on the A2 root (every frozen gate)
  D  g0m1 (Mistral) under A3: sequential counter against the pinned-tokenizer mock with the concurrency artifact injected,
     calA at selected holds and A2 main at selected rates; and the counter class for g0m0 (frozen) vs g0m1 (A3)
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_x2  # noqa: E402  (frozen)
import build_x2_a2  # noqa: E402  (frozen by A2)
import freeze_x2_traces as fx  # noqa: E402  (frozen)
import x2_a2_validate as av  # noqa: E402  (frozen by A2)

PLATS = ("g0m0", "g0m1")
HOLDS = (0.8, 1.0, 1.35, 1.5, 2.0, 2.5, 3.0, 3.3, 3.5, 3.64, 4.0, 5.0)
A3_CALA_HOLDS = (1.35, 2.0, 3.0)
A3_MAIN_RATES = (10, 50, 140, 295)


def analytic() -> list[dict]:
    per_d, per_s = sum(build_x2.SHAPES["D"]), sum(build_x2.SHAPES["S"])
    out = []
    for r in range(5, 1001, 5):
        nd, ns = build_x2.count("D", r), build_x2.count("S", r)
        ntm = max(1, round(nd * per_d / per_s))
        c = {"X2a/c/d attack D": nd, "X2a/c/d control S (token-matched)": ntm, "X2b S": ns}
        out.append({"rate": r, "counts": c, "min_n": min(c.values()), "a2_guarantees_gate": min(c.values()) >= 4,
                    "p_pass_a2_per_arm": {k: round(av.p_gate_strat(n), 4) for k, n in c.items()}})
    return out


@contextlib.contextmanager
def tree():
    (REPO / "results").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="x2_g0_tmp_", dir=REPO / "results") as td:  # git-ignored
        yield Path(td)


def write(files: dict[str, str], root: Path) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)


def freeze(plat: str, phase: str, count, root: Path, *, a2: bool):  # noqa: ANN001, ANN201
    t0 = time.time()
    try:
        if a2:
            from quotashift.x2.arrivals_a2 import a2_loader
            with a2_loader():
                sched, tr = fx.freeze(plat, phase, count, getattr(count, "identity", {}), root=root)
        else:
            sched, tr = fx.freeze(plat, phase, count, getattr(count, "identity", {}), root=root)
        return {"passed": True, "scenarios": len(tr["scenarios"]),
                "scenario_seeds": sum(len(v["seeds"]) for v in tr["scenarios"].values()),
                "calls": getattr(count, "calls", None), "guard_trips": getattr(count, "guard_trips", None),
                "wall_s": round(time.time() - t0, 1)}
    except (Exception, SystemExit) as e:  # noqa: BLE001  (a refusal is a result)
        return {"passed": False, "refusal": f"{type(e).__name__}: {str(e)[:240]}", "wall_s": round(time.time() - t0, 1),
                "guard_trips": getattr(count, "guard_trips", None)}


def cal_a(plat: str, hold: float) -> dict:
    from quotashift.workload.tokenize import WhitespaceTokenizer
    with tree() as root:
        write(build_x2.with_reruns(build_x2.build_cal_a(plat, hold)), root / "x2")
        return {"grid": build_x2.grid(hold), "freeze": freeze(plat, "calA", WhitespaceTokenizer(), root / "x2", a2=False)}


def main_rate(plat: str, rate: int) -> dict:
    from quotashift.workload.tokenize import WhitespaceTokenizer
    tok = WhitespaceTokenizer()
    rates = {"low": rate, "low_feasible": True}
    with tree() as root:
        x2, a2 = root / "x2", root / "x2_a2"
        write(build_x2.with_reruns(build_x2.build_main(plat, rates)), x2)
        write(build_x2_a2.build_main_a2(plat, rates), a2)
        tal: dict[str, list[int]] = {}
        for f in fx.phase_files(plat, "main", a2):
            c = av.check_file(x2 / f.relative_to(a2), f, tok)
            for r in c["rows"]:
                for arm in ("attack", "control"):
                    for k in ("gate_a2", "gate_orig", "one_per_stratum", "count_equal", "tokens_equal",
                              "ids_prompts_shapes_equal", "victims_equal_orig", "deterministic"):
                        t = tal.setdefault(f"{k}/{arm}", [0, 0])
                        t[0] += bool(r[arm][k])
                        t[1] += 1
                for k in ("victims_paired", "budget_matched", "aa_independent"):
                    if k in r:
                        t = tal.setdefault(k, [0, 0])
                        t[0] += bool(r[k])
                        t[1] += 1
        return {"checks": tal, "a2_freeze": freeze(plat, "main", tok, a2, a2=True),
                "original_freeze": freeze(plat, "main", tok, x2, a2=False)}


def a3_rows(sp) -> dict:  # noqa: ANN001
    import x2_a3_validate as v3

    from quotashift.workload import tokenize as T
    from quotashift.workload import tokenize_a3 as A3

    out: dict = {"counter_class": {}}
    A3.install()
    try:
        for plat in PLATS:
            out["counter_class"][plat] = type(T.VllmTokenizer("http://127.0.0.1:9", build_x2.PLATFORMS[plat]["model"])).__name__
        for hold in A3_CALA_HOLDS:
            with tree() as root:
                write(build_x2.with_reruns(build_x2.build_cal_a("g0m1", hold)), root / "x2")
                m = v3.Mock(sp, "tokenize")
                try:
                    r = freeze("g0m1", "calA", T.VllmTokenizer(m.url, v3.MODEL), root / "x2", a2=False)
                finally:
                    m.close()
                out[f"calA hold {hold}"] = r | {"injected": m.injected, "max_tokenize_inflight": m.max_tok_inflight}
                print(f"[{time.strftime('%H:%M:%S')}] A3 g0m1 calA hold {hold}: {r['passed']}", file=sys.stderr, flush=True)
        for rate in A3_MAIN_RATES:
            with tree() as root:
                write(build_x2_a2.build_main_a2("g0m1", {"low": rate, "low_feasible": True}), root / "x2_a2")
                m = v3.Mock(sp, "tokenize")
                try:
                    r = freeze("g0m1", "main", T.VllmTokenizer(m.url, v3.MODEL), root / "x2_a2", a2=True)
                finally:
                    m.close()
                out[f"A2 main rate {rate}"] = r | {"injected": m.injected, "max_tokenize_inflight": m.max_tok_inflight}
                print(f"[{time.strftime('%H:%M:%S')}] A3 g0m1 main {rate}: {r['passed']}", file=sys.stderr, flush=True)
        # the frozen 16-worker counter on the same fault mock: reproduces the refusal class offline (one calA hold)
        A3.uninstall()
        with tree() as root:
            write(build_x2.with_reruns(build_x2.build_cal_a("g0m1", A3_CALA_HOLDS[0])), root / "x2")
            m = v3.Mock(sp, "tokenize")
            try:
                out["frozen 16-worker counter, calA hold 1.35"] = freeze(
                    "g0m1", "calA", T.VllmTokenizer(m.url, v3.MODEL), root / "x2", a2=False) | {"injected": m.injected}
            finally:
                m.close()
    finally:
        A3.uninstall()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sp-model", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    import hashlib

    import sentencepiece as spm
    import x2_a3_validate as v3
    if hashlib.sha256(Path(a.sp_model).read_bytes()).hexdigest() != v3.SP_SHA256:
        print("REFUSED: not the pinned tokenizer.model.v3", file=sys.stderr)
        return 3
    sp = spm.SentencePieceProcessor(model_file=a.sp_model)
    t0 = time.time()
    R: dict = {"label": "X2 G0 OFFLINE READINESS MATRIX (hypothetical holds and rates; not a qualification, not a rate "
                        "selection, not a measurement)", "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "holds": HOLDS, "analytic": analytic(), "calA": {}, "main": {}}
    rates = sorted({r for h in HOLDS for r in build_x2.grid(h)})
    R["candidate_rates"] = rates
    for plat in PLATS:
        R["calA"][plat] = {str(h): cal_a(plat, h) for h in HOLDS}
        R["main"][plat] = {}
        for r in rates:
            R["main"][plat][str(r)] = main_rate(plat, r)
        print(f"[{time.strftime('%H:%M:%S')}] {plat}: calA {len(HOLDS)} holds, main {len(rates)} rates", file=sys.stderr,
              flush=True)
    R["a3"] = a3_rows(sp)
    R["wall_s"] = round(time.time() - t0, 1)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(R, indent=1, default=str) + "\n")
    print(f"wrote {a.out} in {R['wall_s']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
