#!/usr/bin/env bash
# Deploys Nomad Sentinel to Alibaba Cloud Function Compute using Serverless
# Devs (`s`). This is the free-tier path -- no ECS instance, no idle-server
# cost. Run this from your own machine (not inside the repo's Python venv
# necessarily -- `s` is a separate Node-based CLI).
#
# Prerequisites:
#   npm install -g @serverless-devs/s
#   s config add   # paste your (rotated) AccessKey ID/Secret when prompted
#
# Usage:
#   cp deploy/env.production.example deploy/env.production
#   nano deploy/env.production   # fill in real values
#   bash deploy/fc/deploy.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if ! command -v s >/dev/null 2>&1; then
  echo "ERROR: Serverless Devs CLI ('s') not found."
  echo "Install with: npm install -g @serverless-devs/s"
  exit 1
fi

if [ ! -f deploy/env.production ]; then
  echo "ERROR: deploy/env.production not found."
  echo "  cp deploy/env.production.example deploy/env.production"
  echo "  nano deploy/env.production   # fill in real values"
  exit 1
fi

echo "-- Loading deploy/env.production --"
set -a
source deploy/env.production
set +a

if [ -z "${QWEN_API_KEY:-}" ]; then
  echo "ERROR: QWEN_API_KEY is empty in deploy/env.production."
  exit 1
fi

chmod +x deploy/fc/bootstrap

echo "-- Deploying to Function Compute --"
cd deploy/fc
s deploy

echo
echo "== Deployed =="
echo "s CLI prints the HTTP trigger URL above -- that's your dashboard/API endpoint."
echo "Next: bash deploy/verify.sh   (adjust it to hit the FC URL instead of an ECS IP if needed)"
