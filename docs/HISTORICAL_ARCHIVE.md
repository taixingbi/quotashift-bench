# Historical results archive (A1–A5 + sweeps, pre-protocol-v2)

`results/` and `reports/` are git-ignored, so the historical self-hosted measurements exist only on local disk.
Before any protocol-v2 / gateway-consolidation change they were archived (2026-11-21, Phase 0):

- **Location (outside the repo, read-only):**
  `/Users/h/Documents/paper/paper13-quotashift-bench/quotashift_historical_archive/20261121T042816Z/`
- **Archive:** `quotashift_historical_20261121T042816Z.tar.gz` (18,914,417 bytes)
  SHA-256 `cc0d12b2578eaf672e1876160898e298b2141caed0da3c8f43a1273da1f8630e`
- **Contents (original relative paths preserved):** `results/`, `reports/`, `experiments/`, `configs/`,
  `multitenant/` (partial, pre-consolidation), `docs/{RESULTS_selfhost,KNOWN_LIMITATIONS,DECISIONS}.md`,
  `IMPLEMENTATION_STATUS.md` — 1,457 files.
- **Sidecar files:** `files.sha256` (per-file SHA-256, 1,457 entries; sha `5d72f740…`), `git_metadata.txt`
  (HEAD `2a6a6b1`, log, porcelain status, and the run-manifest git SHAs: 3d4c40f ×42, 4a829d7 ×50,
  680a0ff ×38, fc1d155 ×40, 615c3cb ×10, 02a8444 ×1), `uncommitted_tracked_changes.patch`, `ARCHIVE.sha256`.
- **Verification (2026-11-21T04:28Z):** `shasum -c ARCHIVE.sha256` OK; extracted to a temp dir, all 1,457
  per-file checksums OK, extracted file list identical to the manifest; originals re-checked unchanged.
- **Second copy:** not made — only one disk (`Macintosh HD`) was mounted. Copy the directory to an external
  disk or another host when available and re-run `shasum -a 256 -c ARCHIVE.sha256`.

Restore: `tar -xzf quotashift_historical_20261121T042816Z.tar.gz -C <dir>` then
`(cd <dir> && shasum -a 256 -c <archive>/files.sha256)`.

`tests/unit/test_historical_preservation.py` checks local historical files against
`tests/fixtures/historical_results.sha256` (a copy of the results/reports subset) and the historical scenario
YAML + schedule hashes, so accidental modification fails the test suite.
