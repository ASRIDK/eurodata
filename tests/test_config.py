from eurodata.config import get_settings


def test_defaults(monkeypatch):
    monkeypatch.delenv("DUCKDB_PATH", raising=False)
    get_settings.cache_clear()
    s = get_settings()
    assert s.duckdb_path.endswith("eurodata.duckdb")
    assert s.ingest_start_year == 2000


def test_env_override(monkeypatch):
    monkeypatch.setenv("INGEST_START_YEAR", "1995")
    get_settings.cache_clear()
    assert get_settings().ingest_start_year == 1995
