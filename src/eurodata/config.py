from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    duckdb_path: str = "data/eurodata.duckdb"
    raw_snapshot_dir: str = "data/raw"
    release_dir: str = "data/releases"
    ingest_start_year: int = 2000


@lru_cache
def get_settings() -> Settings:
    return Settings()
