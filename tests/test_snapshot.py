import json
from eurodata.ingest.snapshot import save_snapshot


def test_save_snapshot_writes_file_and_hash(tmp_path):
    payload = json.dumps({"a": 1}).encode()
    path, digest = save_snapshot(tmp_path, "Eurostat", "nama_10_gdp", {"startPeriod": "2000"}, payload)
    assert path.exists()
    assert len(digest) == 64  # sha256 hex
    assert path.read_bytes() == payload
