"""X2 Amendment A3 (DRAFT): sequential Mistral token counting. Offline; loopback mock only, no GPU, no AWS."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
import build_x2  # noqa: E402
import pin_x2_a3  # noqa: E402
import x2_a3  # noqa: E402

from quotashift.workload import tokenize as T  # noqa: E402
from quotashift.workload import tokenize_a3 as A3  # noqa: E402

MISTRAL = "mistralai/Mistral-7B-Instruct-v0.3"
QWEN = "Qwen/Qwen2.5-7B-Instruct"


@pytest.fixture(autouse=True)
def _restore():
    yield
    A3.uninstall()


class _Mock:
    """/tokenize = BOS + one id per whitespace word; optional trailing EOS when another /tokenize is in flight."""

    def __init__(self, *, fault: bool = False, eos_always: bool = False, bad_count: bool = False) -> None:
        self.inflight = self.max_inflight = self.injected = 0
        self.lock = threading.Lock()
        m = self

        class Hd(BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002
                pass

            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with m.lock:
                    m.inflight += 1
                    m.max_inflight = max(m.max_inflight, m.inflight)
                time.sleep(0.003)
                ids = [1] + [100 + i for i, _ in enumerate(body["prompt"].split())]
                with m.lock:
                    conc = m.inflight > 1
                    m.inflight -= 1
                if eos_always or (fault and conc):
                    ids.append(2)
                    with m.lock:
                        m.injected += 1
                b = json.dumps({"count": len(ids) + (1 if bad_count else 0), "tokens": ids}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Hd)
        self.srv.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()


TEXTS = [" ".join(["w"] * n) + f" t{n}" for n in range(1, 41)]


def test_frozen_module_bytes_and_defaults_untouched():
    pins = json.loads((REPO / "experiments" / "v5" / "FROZEN_SHA256.json").read_text())["files"]
    assert pin_x2_a3.pin_x2.sha("src/quotashift/workload/tokenize.py") == pins["src/quotashift/workload/tokenize.py"]
    assert A3.FROZEN_VLLM_TOKENIZER.__init__.__kwdefaults__["workers"] == 16
    assert T.VllmTokenizer is A3.FROZEN_VLLM_TOKENIZER and not A3.active()


def test_hook_is_inert_without_env_and_fails_closed_on_unknown_value():
    env = {k: v for k, v in os.environ.items() if k != A3.ENV}
    code = ("import sys, quotashift.local, quotashift.workload.tokenize as T; "
            "print(T.VllmTokenizer.__name__, 'quotashift.workload.tokenize_a3' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True).stdout
    assert out.split() == ["VllmTokenizer", "False"]
    bad = subprocess.run([sys.executable, "-c", "import quotashift.workload"], env=env | {A3.ENV: "X2-A9"},
                         capture_output=True, text=True)
    assert bad.returncode != 0 and "not a recognised token-counter amendment" in bad.stderr


def test_env_activation_rebinds_the_name_frozen_callers_resolve():
    code = ("import quotashift.local\nfrom quotashift.workload.tokenize import VllmTokenizer as V\n"
            f"print(type(V('http://127.0.0.1:9', '{MISTRAL}')).__name__, type(V('http://127.0.0.1:9', '{QWEN}')).__name__)")
    out = subprocess.run([sys.executable, "-c", code], env=os.environ | {A3.ENV: A3.ENV_VALUE}, capture_output=True,
                         text=True, check=True).stdout
    assert out.split() == ["SequentialMistralTokenizer", "VllmTokenizer"]


def test_qwen_keeps_the_frozen_counter_bit_for_bit():
    A3.install()
    c = T.VllmTokenizer("http://127.0.0.1:9", QWEN)
    assert type(c) is A3.FROZEN_VLLM_TOKENIZER and c._workers == 16 and "amendment" not in c.identity
    with pytest.raises(ValueError):
        A3.SequentialMistralTokenizer("http://127.0.0.1:9", QWEN)


def test_sequential_counter_one_in_flight_exact_and_cached():
    m = _Mock(fault=True)
    try:
        c = A3.a3_counter(m.url, MISTRAL, workers=16)          # a workers argument cannot re-enable fan-out
        n = c(TEXTS)
        assert n == [len(t.split()) + 1 for t in TEXTS]
        assert m.max_inflight == 1 and m.injected == 0 and c.guard_trips == 0
        assert c(TEXTS) == n and c.calls == len(TEXTS)          # cache: no second round of requests
        assert c.identity["amendment"] == "X2-A3" and c.identity["workers"] == 1
    finally:
        m.close()


def test_frozen_counter_reproduces_the_artifact_on_the_fault_mock():
    m = _Mock(fault=True)
    try:
        n = A3.FROZEN_VLLM_TOKENIZER(m.url, MISTRAL)(TEXTS)
        assert m.max_inflight > 1 and any(k == len(t.split()) + 2 for k, t in zip(n, TEXTS, strict=True))
    finally:
        m.close()


@pytest.mark.parametrize("kw", [{"eos_always": True}, {"bad_count": True}])
def test_guards_fail_closed_never_correct(kw):
    m = _Mock(**kw)
    try:
        c = A3.a3_counter(m.url, MISTRAL)
        with pytest.raises(T.TokenizedContextInvalid, match="A3"):
            c(TEXTS[:3])
        assert c.guard_trips == 1
    finally:
        m.close()


def test_calibrate_and_verify_unchanged_with_a3_counter():
    """The frozen calibrate_trace / exact verify_trace run unchanged on the A3 counter and converge exactly."""
    from quotashift.local import budget_view, paired_traces
    from quotashift.scenario import load_scenario

    f = REPO / "experiments" / "x2" / "g1m1" / "calA" / "x2_g1m1_calA_aa_ind_L10_C8.yaml"
    sc = load_scenario(f)
    m = _Mock(fault=True)
    try:
        c = A3.a3_counter(m.url, MISTRAL)
        atk, ctl, _ = paired_traces(sc, sc.seed, c)
        for tr in (budget_view(sc, atk, sc.seed), ctl):
            assert T.verify_trace(tr, c, max_model_len=sc.model_max_len, exact=True)["ok"]
        assert m.injected == 0 and m.max_inflight == 1
    finally:
        m.close()


def test_driver_refuses_qwen_platforms_and_live_without_a3_freeze(capsys):
    assert x2_a3.main(["freeze", "--platform", "g1m0", "--phase", "calA", "--offline", "--out-dir", "/tmp/x"]) == 3
    assert "Mistral platforms only" in capsys.readouterr().err
    if not pin_x2_a3.MANIFEST.exists():
        assert x2_a3.main(["stage", "--platform", "g1m1", "--phase", "calA", "--live"]) == 3
        assert "A3 freeze has not been made" in capsys.readouterr().err


def test_driver_phase_dispatch():
    assert x2_a3.parse(["freeze", "--platform", "g1m1", "--phase", "calA", "--live"])[3] == [
        "--platform", "g1m1", "--live", "--phase", "calA"]
    assert x2_a3.parse(["stage", "--platform", "g1m1", "--phase", "main", "--mock"])[3] == [
        "--platform", "g1m1", "--mock"]
    assert x2_a3.DRIVERS[("freeze", "main")] == "freeze_x2_a2_traces.py"
    assert {p for p, s in build_x2.PLATFORMS.items() if s["model"] in A3.A3_MODELS} == {"g0m1", "g1m1"}


def test_earlier_freezes_verify_and_a3_pins_cover_its_files():
    assert pin_x2_a3.earlier_problems() == []
    assert set(pin_x2_a3.FILES) >= {"src/quotashift/workload/tokenize_a3.py", "src/quotashift/workload/__init__.py",
                                     "scripts/x2_a3.py", "docs/PROTOCOL_X2_AMENDMENT_A3.md"}
    assert all((REPO / f).exists() for f in pin_x2_a3.FILES)


def test_pin_write_requires_owner_token(monkeypatch, capsys):
    monkeypatch.delenv("QUOTASHIFT_APPROVED", raising=False)
    monkeypatch.setattr(sys, "argv", ["pin_x2_a3.py", "--write"])
    assert pin_x2_a3.main() == 3
    assert "x2_amend_a3" in capsys.readouterr().err
