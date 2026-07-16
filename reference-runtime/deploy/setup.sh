#!/usr/bin/env bash
# Run this ON the ECS instance, after SSHing in, from an empty working directory.
# Prerequisites (must already exist -- see deploy/README.md steps 1-3, run from
# your own machine with the aliyun CLI, not from the instance):
#   - the ECS instance itself is up and reachable
#   - an OSS bucket has been created (aliyun oss mb oss://<bucket> --region <region>)
#   - port 8765 is open in the instance's security group
#   - deploy/env.production has been filled in with real values (copy
#     deploy/env.production.example, this script will stop and tell you if
#     it's still just the template)
#
# Usage:
#   git clone <your-repo-url> nomad-sentinel && cd nomad-sentinel
#   bash deploy/setup.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "== Nomad Sentinel ECS setup =="
echo "Repo root: $REPO_ROOT"

if [ ! -f deploy/env.production ]; then
  echo
  echo "ERROR: deploy/env.production not found."
  echo "  cp deploy/env.production.example deploy/env.production"
  echo "  nano deploy/env.production   # fill in QWEN_API_KEY, ALIBABA_OSS_* values"
  echo "then re-run this script."
  exit 1
fi

if grep -q "^QWEN_API_KEY=$" deploy/env.production; then
  echo
  echo "ERROR: deploy/env.production still has an empty QWEN_API_KEY."
  echo "Fill in real values before running this script."
  exit 1
fi

echo "-- Creating virtualenv --"
python3 -m venv .venv
source .venv/bin/activate

echo "-- Installing dependencies --"
pip install --upgrade pip -q
pip install -e . -r requirements.txt -q

echo "-- Installing systemd unit --"
sudo cp deploy/nomad-sentinel.service /etc/systemd/system/nomad-sentinel.service
sudo systemctl daemon-reload
sudo systemctl enable nomad-sentinel
sudo systemctl restart nomad-sentinel

sleep 2
echo
echo "-- Service status --"
sudo systemctl status nomad-sentinel --no-pager -l | head -15

echo
echo "== Done =="
PUBLIC_IP="$(curl -s -4 ifconfig.me || echo '<your-ecs-public-ip>')"
echo "Dashboard should be reachable at: http://${PUBLIC_IP}:8765/dashboard"
echo "If it's not responding, check: sudo journalctl -u nomad-sentinel -n 50 --no-pager"
echo
echo "Next: run deploy/verify.sh to produce your Alibaba Cloud OSS deployment proof."
