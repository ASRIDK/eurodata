from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Record:
    iso3: str
    indicator_code: str
    year: int
    value: float
    unit: str | None = None
    currency: str | None = None
    price_basis: str | None = None
    quarter: int | None = None
    month: int | None = None
    vintage_date: str | None = None  # ISO 'YYYY-MM-DD'


class BaseFetcher(ABC):
    source_name: str = "base"
    # A disabled fetcher is skipped by the pipeline, which records the reason
    # in ingestion_run instead of silently reporting 0 records.
    enabled: bool = True
    disabled_reason: str | None = None

    def __init__(self) -> None:
        # (series_key, error message) for per-series failures; the pipeline
        # persists these to ingestion_error so partial fetches stay visible.
        self.errors: list[tuple[str, str]] = []

    @abstractmethod
    def fetch(self, start_year: int) -> list[Record]:
        """Return normalized records from the live source."""
        raise NotImplementedError
