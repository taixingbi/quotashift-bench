# Repository Audit (Milestone 0, 2026-11-18)

## What existed before this turn
| Path | Content |
|---|---|
| `CLAUDE_CODE_MLSYS_MASTER_PLAN.md` | Master research plan (Paper A) |
| `CLAUDE_CODE_FIRST_TASK.md` | First-turn instructions |

Nothing else: no source code, Terraform, containers, benchmarks, datasets, licenses, CI, or git history (the
directory was not a git repository; `git init` was run locally, **no commit made**). The parent directory
contains only this project folder.

## Reusable assets inventory
| Asset class | Found | Reuse decision |
|---|---|---|
| Gateway / load-test code | none | built from scratch (`src/risksched`) |
| Metrics / telemetry code | none | built (`instrumentation/`) |
| Terraform | none | built (`infra/terraform/`) |
| Containers | none | built (`docker/`) |
| Code from the earlier hidden-capacity gateway paper | **not present** in this repo; not reused | if it is ever reused it must be independently reproducible and clearly distinguished (master plan §6 M2.3) |
| Employer (JPMorgan) code/traces | none present; none used | — |
| Licenses | no LICENSE file present | `pyproject.toml` declares Apache-2.0 provisionally — **owner must confirm** before publishing |

## External artifacts identified for later milestones (not vendored)
| Artifact | Use | License status |
|---|---|---|
| [VTC-artifact](https://github.com/Ying1123/VTC-artifact) | baseline (M2/M5) | to check |
| [UIUC-MLSys/JITServe](https://github.com/UIUC-MLSys/JITServe) | baseline (M3/M5) | to check |
| [hao-ai-lab/vllm-ltr](https://github.com/hao-ai-lab/vllm-ltr) | predictor baseline (M3) | to check |
| [QLM](https://github.com/QLM-project/QLM) | gateway-level SLO queueing reference | to check |
| Qwen3-1.7B / 4B weights | serving | Apache-2.0 (HF card metadata) |
| Public prompt datasets (e.g. ShareGPT-derived, LMSYS-Chat-1M, BurstGPT/Azure traces) | M2 semantic workloads | **licenses/terms to audit before use** (LMSYS-Chat-1M has a gated license agreement) |
