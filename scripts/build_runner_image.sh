#!/usr/bin/env bash
# X1 runner image: build from a CLEAN tree with the commit baked in, then (separately approved) push to the project ECR.
#   scripts/build_runner_image.sh --dry-run                  # print what would happen; touches nothing
#   QUOTASHIFT_APPROVED=build_image scripts/build_runner_image.sh build          # local docker build only
#   QUOTASHIFT_APPROVED=push_image  scripts/build_runner_image.sh push <ecr-url> # push + print the digest for tfvars
# Building or pushing is never automatic; X1-E prepared this script but did not run it.
set -euo pipefail
cd "$(dirname "$0")/.."
MODE="${1:---dry-run}"
SHA="$(git rev-parse HEAD)"
if [[ -n "$(git status --porcelain)" ]]; then echo "REFUSED: git tree not clean (provenance must be a commit)" >&2; exit 3; fi
TAG="quotashift-runner:${SHA:0:12}"
CMD=(docker build --platform linux/amd64 --build-arg "GIT_SHA=$SHA" --build-arg GIT_DIRTY=false -f docker/Dockerfile -t "$TAG" .)
case "$MODE" in
  --dry-run) echo "would run: ${CMD[*]}"; echo "then: push to <ecr>/quotashift-research-runner:${SHA:0:12} and pin runner_image = <ecr>@sha256:<digest>" ;;
  build) [[ "${QUOTASHIFT_APPROVED:-}" == build_image ]] || { echo "REFUSED: build_image not approved" >&2; exit 3; }
         "${CMD[@]}" ;;
  push)  [[ "${QUOTASHIFT_APPROVED:-}" == push_image ]] || { echo "REFUSED: push_image not approved" >&2; exit 3; }
         ECR="${2:?ecr repository url}"
         docker tag "$TAG" "$ECR:${SHA:0:12}" && docker push "$ECR:${SHA:0:12}"
         docker inspect --format '{{index .RepoDigests 0}}' "$ECR:${SHA:0:12}" ;;
  *) echo "usage: $0 [--dry-run|build|push <ecr-url>]" >&2; exit 2 ;;
esac
