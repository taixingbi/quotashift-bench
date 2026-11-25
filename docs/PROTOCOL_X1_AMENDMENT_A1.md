<!-- Text below the rule is copied verbatim from docs/X1_AMENDMENT_A1_SAMPLER_EQUIVALENCE.md §3 (reviewed at 02eafae). -->
**Status:** approved by the owner (`x1_amend_a1`, 2026-11-25) exactly as specified in the reviewed proposal at commit `02eafae`; pinned in `experiments/x1/AMENDMENT_A1_SHA256.json`. Justification, sample size, sensitivity and threats to validity: `docs/X1_AMENDMENT_A1_SAMPLER_EQUIVALENCE.md`.

---

**Protocol X1, Amendment A1: sampler on/off equivalence (post hoc, 2026-11-25).**
This amendment was written after two g0m0 Phase 1 attempts failed under the rev 4 point-estimate rule. Both FAIL
verdicts stand. A1 replaces, for every X1 Phase 1 preflight run that starts after A1 is pinned
(`experiments/x1/AMENDMENT_A1_SHA256.json`), the §9.1 row "Sampler on/off equivalence". It applies identically to all
four platforms. Everything else in rev 4 is unchanged.

**A1.1 Question and tolerance.** Is the median idle TTFT with the host sampler running within ±δ of the median with
it stopped? δ = max(1 ms, 2% × the nearest-rank median of all measured OFF requests). This is the rev 4 tolerance,
unchanged.

**A1.2 Design (fixed sample size).**
- **Pairs:** K = 24 pairs of segments, 48 segments in all. Pair k (0-based) runs OFF then ON if k is even, and ON then OFF if k is odd. Each arm comes first in 12 pairs, and both arms have the same mean position, so a linear drift cancels.
- **Each segment, in order:**
  1. Set the sampler state and verify it. ON: the frozen `scripts/x1_host_sampler.py` is running in daemon mode, unchanged, at 1 Hz and nice 19. OFF: no sampler process.
  2. Verified `/reset_prefix_cache`, i.e. the frozen `reset_and_verify` probe shows warm hits before the reset and zero after.
  3. W = 3 warm-up requests on dedicated prompts (seeds 900–902). These are recorded but never analysed.
  4. M = 80 measured requests on one fixed prompt list (`prompt_of(60, seed)`, seeds 200–279, `max_tokens` 8, temperature 0, `ignore_eos`, streamed). The list is **identical in every segment**.
  5. ON only: verify the sampler is still running, then stop it and verify that no sampler process remains.
- **Request discipline:** one request in flight, sent back-to-back, with a fresh HTTP connection each.
- **Timing:** TTFT is measured on the runner (monotonic clock, send to first non-empty text chunk), independently of the GPU-host sampler.
- **Recorded per request:** wall-clock send time, TTFT, end time, segment, arm and prompt seed.
- **Recorded per segment, for the record only:** the server's `vllm:time_to_first_token_seconds` histogram sum and count, before and after.

**A1.3 Statistic.** For each pair, d_k = p50(ON_k) − p50(OFF_k), using the frozen nearest-rank `pctl` over the 80
measured requests. D̄ = mean d_k; SE = sd(d_k)/√K; df = K − 1 = 23.

**A1.4 Decision (TOST, α = 0.05).** PASS iff the 90% two-sided interval D̄ ± t₀.₉₅,₂₃ · SE (t = 1.713872) lies strictly
inside (−δ, +δ). Otherwise FAIL. Also FAIL if any of the following holds; there is no flag outcome:
- a segment is missing, or does not have exactly 80 finite measured TTFTs;
- a reset was not verified;
- the sampler state was not verified.

The 95% interval and the rev 4 point rule (applied to the pooled requests) are reported alongside, and do not decide.

**A1.5 Unchanged.**
- `sampler_overhead` stays exactly as frozen: the sampler's own CPU must be < 1% of a core. It is measured, as in attempt 2, by a dedicated finite 65 s sampler run that writes its summary.
- Every other Phase 1 and Phase 2 gate, threshold, seed, hypothesis, family, prediction and analysis rule in rev 4 is unchanged.
- The idle TTFT floor remains descriptive. It is reported as the nearest-rank median of the measured OFF requests.

**A1.6 One run, no retries.** The first amended run per platform is final. On g0m0, one amended Phase 1 run needs its
own owner token. If A1 or any other Phase 1 gate fails, the platform is not admissible and the stage stops; there is
no further attempt.
