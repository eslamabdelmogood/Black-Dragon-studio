#!/usr/bin/env python3
"""
Nomad Sentinel — Alibaba Cloud OSS Telemetry Sink
═══════════════════════════════════════════════════════════════════════
This is the code file referenced in the submission as proof of Alibaba
Cloud deployment. It's a real client against Alibaba Cloud Object
Storage Service (OSS) using the official `oss2` SDK -- not a mock.

Role in the architecture
-------------------------
The edge device (or, for the simulation-first digital twin, the demo
script) runs entirely locally: sensing, reflex, and Guardian-mode
cognition never touch the network. When ModeSwitcher escalates to
STALLION and Qwen Cloud produces a decision, this module is what
persists that decision (and periodic device/panel telemetry snapshots)
to Alibaba Cloud, so:
  1. the dashboard (served from the same Alibaba Cloud ECS instance,
     see deploy/README.md) can show cross-session history without the
     edge device needing to stay online, and
  2. there's a durable, off-device audit trail of every action the
     system took and why -- important for a safety-relevant system,
     and required by the "Proof of Alibaba Cloud Deployment" rule.

This module is intentionally decoupled from bhs/cloud_cognition.py:
it's an optional sink, not a dependency of the control loop. If OSS is
unreachable, upload_event() logs a warning and returns False -- it
never raises into the simulation/control path.

Setup
-----
  pip install oss2
  export ALIBABA_OSS_ACCESS_KEY_ID=...
  export ALIBABA_OSS_ACCESS_KEY_SECRET=...
  export ALIBABA_OSS_ENDPOINT=https://oss-ap-southeast-1.aliyuncs.com
  export ALIBABA_OSS_BUCKET=nomad-sentinel-telemetry
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

try:
    import oss2
except ImportError:  # pragma: no cover
    oss2 = None


OSS_ACCESS_KEY_ID     = os.getenv("ALIBABA_OSS_ACCESS_KEY_ID", "")
OSS_ACCESS_KEY_SECRET = os.getenv("ALIBABA_OSS_ACCESS_KEY_SECRET", "")
OSS_ENDPOINT           = os.getenv("ALIBABA_OSS_ENDPOINT", "https://oss-ap-southeast-1.aliyuncs.com")
OSS_BUCKET_NAME         = os.getenv("ALIBABA_OSS_BUCKET", "nomad-sentinel-telemetry")


class AlibabaTelemetrySink:
    """Thin wrapper around oss2.Bucket for writing/reading Nomad Sentinel events."""

    def __init__(self, bucket_name: str = OSS_BUCKET_NAME, endpoint: str = OSS_ENDPOINT):
        self._bucket = None
        self._enabled = bool(oss2 and OSS_ACCESS_KEY_ID and OSS_ACCESS_KEY_SECRET)
        if self._enabled:
            auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
            self._bucket = oss2.Bucket(auth, endpoint, bucket_name)
        else:
            print("[alibaba_oss_telemetry] disabled -- oss2 not installed or "
                  "ALIBABA_OSS_ACCESS_KEY_ID/SECRET not set. Events will be "
                  "logged locally only.")

    def upload_event(self, device_id: str, event: dict) -> bool:
        """
        Upload one decision/telemetry event. Object key layout:
          events/<device_id>/<unix_ts>.json
        Chosen so the dashboard can cheaply list a device's recent history
        via oss2.Bucket.list_objects(prefix=f"events/{device_id}/").
        """
        if not self._enabled:
            return False
        key = f"events/{device_id}/{int(time.time() * 1000)}.json"
        try:
            self._bucket.put_object(key, json.dumps(event).encode("utf-8"))
            return True
        except Exception as e:
            print(f"[alibaba_oss_telemetry] upload failed (non-fatal): {e}")
            return False

    def upload_run_log(self, device_id: str, run_name: str, log_path: str) -> bool:
        """Upload a full run log (e.g. outputs/edge_cloud_log.json) as one object."""
        if not self._enabled:
            return False
        key = f"runs/{device_id}/{run_name}.json"
        try:
            self._bucket.put_object_from_file(key, log_path)
            print(f"[alibaba_oss_telemetry] uploaded {log_path} -> oss://{OSS_BUCKET_NAME}/{key}")
            return True
        except Exception as e:
            print(f"[alibaba_oss_telemetry] run-log upload failed (non-fatal): {e}")
            return False

    def recent_events(self, device_id: str, limit: int = 50) -> list[dict]:
        """Read back the most recent events for a device, newest first."""
        if not self._enabled:
            return []
        prefix = f"events/{device_id}/"
        try:
            keys = sorted(
                (obj.key for obj in oss2.ObjectIterator(self._bucket, prefix=prefix)),
                reverse=True,
            )[:limit]
            events = []
            for key in keys:
                content = self._bucket.get_object(key).read()
                events.append(json.loads(content))
            return events
        except Exception as e:
            print(f"[alibaba_oss_telemetry] read failed: {e}")
            return []


# ═══════════════════════════════════════════════════════════════════════════
#  CLI: upload a run log produced by scripts/run_edge_cloud_demo.py
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Upload a Nomad Sentinel run log to Alibaba Cloud OSS")
    ap.add_argument("log_path", help="Path to outputs/edge_cloud_log.json")
    ap.add_argument("--device-id", default="sim-panel-01")
    ap.add_argument("--run-name", default=f"run-{int(time.time())}")
    args = ap.parse_args()

    sink = AlibabaTelemetrySink()
    ok = sink.upload_run_log(args.device_id, args.run_name, args.log_path)
    print("Upload succeeded." if ok else "Upload skipped/failed -- see message above.")
