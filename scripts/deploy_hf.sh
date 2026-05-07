#!/usr/bin/env bash
# Deploy current branch to HF Spaces via orphan commit (avoids binary file rejection).
# Usage: bash scripts/deploy_hf.sh
set -euo pipefail

CURRENT=$(git branch --show-current)
TMP="hf-deploy-tmp"

echo "Deploying $CURRENT → space/main ..."
git checkout --orphan "$TMP"
git add -A
git commit -q -m "Deploy: $(date -u '+%Y-%m-%d %H:%M') from $CURRENT"
git push space "$TMP:main" --force
git checkout "$CURRENT"
git branch -D "$TMP"
echo "Done."
