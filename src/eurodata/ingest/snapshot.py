from __future__ import annotations

import hashlib
import json
from pathlib import Path


def save_snapshot(base_dir, source: str, endpoint: str, params: dict, payload: bytes):
    base = Path(base_dir) / source
    base.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload).hexdigest()
    slug = endpoint.replace("/", "_")
    path = base / f"{slug}_{digest[:12]}.raw"
    path.write_bytes(payload)
    meta = path.with_suffix(".meta.json")
    meta.write_text(json.dumps({"source": source, "endpoint": endpoint,
                                "params": params, "sha256": digest}))
    return path, digest
