#!/usr/bin/env bash
# Produces the actual "Proof of Alibaba Cloud Deployment" artifact for the
# submission: runs a real simulation, uploads the resulting log to OSS via
# deploy/alibaba_oss_telemetry.py, and lists the bucket to confirm the
# object actually landed. Run this after deploy/setup.sh has succeeded.
#
# Usage: bash deploy/verify.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
source .venv/bin/activate
set -a
source deploy/env.production
set +a

DEVICE_ID="demo-panel-$(date +%s)"

echo "-- Running edge/cloud demo (400 steps) --"
python3 scripts/run_edge_cloud_demo.py --steps 400 --out outputs/edge_cloud_log.json

echo
echo "-- Uploading run log to Alibaba Cloud OSS --"
python3 deploy/alibaba_oss_telemetry.py outputs/edge_cloud_log.json --device-id "$DEVICE_ID"

echo
echo "-- Verifying the object actually landed in the bucket --"
aliyun oss ls "oss://${ALIBABA_OSS_BUCKET}/runs/${DEVICE_ID}/" || {
  echo "aliyun CLI not installed/configured on this instance -- install it or"
  echo "check the OSS console directly for oss://${ALIBABA_OSS_BUCKET}/runs/${DEVICE_ID}/"
}

echo
echo "== This terminal output (or a console screenshot of the same object) =="
echo "== is your submission's Proof of Alibaba Cloud Deployment.            =="
