"""Export API: zips a generated project for download (constitution 13,
`GET /api/projects/{project_id}/download`)."""
from __future__ import annotations

import os
import zipfile

_MAX_ZIP_BYTES = int(os.environ.get("BDS_MAX_ZIP_BYTES", str(50 * 1024 * 1024)))  # 50 MB cap


def make_zip(output_dir: str, zip_path: str, root_name: str) -> str:
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    if os.path.exists(zip_path):
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(output_dir):
            for fname in files:
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, output_dir)
                arcname = os.path.join(root_name, rel_path)
                zf.write(full_path, arcname)

    size = os.path.getsize(zip_path)
    if size > _MAX_ZIP_BYTES:
        os.remove(zip_path)
        raise ValueError(f"generated ZIP exceeds size limit ({size} > {_MAX_ZIP_BYTES} bytes)")
    return zip_path
