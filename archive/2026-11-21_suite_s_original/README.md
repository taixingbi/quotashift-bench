# Original data archive — 2026-11-21 (before the Suite S corrections)

Snapshot of every file under `results/` and `reports/` taken 2026-11-21 20:56 EST, after Suite S (A7–A9 v3)
and the forensic audit, before any code fix or reanalysis (ADR-Q16/Q17). Nothing in it is modified.

- `FILES.txt` — the 2,942 archived paths (sorted).
- `SHA256SUMS.txt` — `shasum -a 256` of each file; verify with `shasum -a 256 -c SHA256SUMS.txt` from the repo root.
- `results_reports.tar.gz` — the files themselves (local only, gitignored, read-only); its digest is in
  `TARBALL.sha256` (`c8c1222b…5fce60`).

Historical measurements and pre-registered classifications in these files are never overwritten. Corrected outputs
are written to new directories (`reports/corrected/2026-11-21_adr_q16/`, `reports/v3_1/`).
