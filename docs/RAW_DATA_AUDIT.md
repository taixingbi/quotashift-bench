# Raw-data audit and storage proposal (2026-11-22)

This covers what the committed raw data exposes and how future raw data should be stored.
- **Scope:** `reports/` and `results/` as committed in `c11decc`: 5,025 files, about 236 MB.
- **Visibility:** the GitHub repository is **public**, so everything below is already published.

## 1. Audit findings

| Category | Found | Where | Severity |
|---|---|---|---|
| Credentials: private keys, cloud access keys, GitHub tokens, Hugging Face tokens, `sk-` keys, passwords | **none** | regex scan of every file | — |
| Owner email or GitHub account name | **none** | — | — |
| Absolute local paths `/Users/h/...` (local username `h`) | 213 files | run-report `manifest.json` `run_dirs`, generated summaries | low |
| GPU-host path `/home/tb/...` (host username `tb`) | 1 file | `reports/v4/server_info_preflight.json` (`vllm_env` cache roots) | low |
| Private LAN address `192.168.86.173` (RFC1918, not routable from the internet) | 1,210 files | run manifests, target snapshots | low |
| GPU device identifiers (UUID, VBIOS, PCI bus id, driver) | 405 files | per-run `manifest.json` `gpu` block | low (device fingerprint) |
| Client platform and package lists (macOS arm64, Python and package versions) | every run manifest | `manifest.json` | informational (needed for reproducibility) |
| vLLM server environment dump | 1 file | `server_info_preflight.json` (`vllm_env`, `system_env`) | low; it lists only `VLLM_*` settings and cache paths, with no token variables |
| Prompt text | every `trace.jsonl` | deterministic synthetic word templates with request tags | none (benign, synthetic) |
| Wall-clock timestamps and git SHAs | everywhere | manifests | informational (needed for provenance) |

**Conclusion.**
- **No secrets** were found in the committed data.
- **Some identifying metadata was published:** two local usernames, a private LAN IP and a GPU fingerprint. None of
  it is exploitable from outside the LAN.
- **The only full remedy is rewriting history** (`git filter-repo`) and force-pushing. That is destructive for anyone
  who has cloned the repo, so the owner must decide on it.
- **Recommendation: no history rewrite.** Sanitize all future raw-data exports (§3).

## 2. Proposal: Git LFS vs immutable release artifacts

| | Git LFS | Immutable release artifacts plus a SHA-256 manifest (recommended) |
|---|---|---|
| Storage and bandwidth | GitHub free tier: 1 GB storage and 1 GB/month bandwidth; a public repo's clones count against the owner's quota | GitHub Release assets: up to 2 GB per file, no bandwidth quota. Zenodo: DOI, citable, up to 50 GB |
| Immutability | LFS objects can be rewritten or deleted | Release assets plus a Zenodo DOI are effectively immutable; hashes are pinned in the repo |
| Clone cost | `git lfs install` needed; full history pulls pointers only | Repo stays small; data fetched on demand |
| Fit with frozen protocols | Weak: data and code versions mix in one history | Strong: one tarball per stage, hash referenced from `experiments/PLAN.md` |

**Recommended policy for future raw data (owner decision):**
1. **Keep in git:** `reports/**` summaries (`summary.csv`/`.md`, `manifest.json` after sanitizing, analysis CSVs) and
   a `RAW_DATA_MANIFEST.json` per stage. Each manifest lists every file's path, size and SHA-256, plus the release
   asset URL and its SHA-256.
2. **Do not keep in git:** `results/**` raw runs (`trace.jsonl`, `*.parquet`, figures). Package them per stage as
   `quotashift-<stage>-<date>.tar.zst` and attach to a GitHub Release, optionally mirrored to Zenodo.
3. **Verify:** a `scripts/verify_raw_data.py` step downloads the asset, checks the SHA-256 and lists any mismatch. It
   would extend the checksum test that already exists for the Suite S archive (`docs/HISTORICAL_ARCHIVE.md`).
4. **Already-committed `results/`:** leave them (no rewrite). Stop adding new raw runs to git once the owner approves
   this policy, by restoring `results/*` in `.gitignore` for future runs.

## 3. Sanitization at export (proposal; nothing implemented yet)

- Rewrite absolute paths to paths relative to the repo: `run_dirs`, cache roots.
- Replace `192.168.86.173` with the target profile name (`selfhost`) in exported copies; the target config keeps the
  real value.
- Hash the GPU UUID and PCI bus id with a per-project salt. That keeps "same device" comparisons possible.
- Exclude `vllm_env.*_CACHE*` and the `system_env.pip_packages` details from public exports; keep them in the
  private archive.

Each export is checked by a regex gate that fails on `/Users/`, `/home/`, private keys and token patterns before
packaging.
