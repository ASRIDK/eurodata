from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

_PERIOD_RE = re.compile(r"^(\d{4})(?:-(Q([1-4])|(\d{2})))?$")


def parse_period(time_period: str) -> tuple[int, int | None, int | None] | None:
    """SDMX TIME_PERIOD -> (year, quarter, month).

    Accepts '2020' (annual), '2020-Q3' (quarterly), '2020-07' (monthly);
    returns None for anything else (weekly/daily periods are not modeled).
    """
    m = _PERIOD_RE.match(str(time_period).strip())
    if not m:
        return None
    year = int(m.group(1))
    if m.group(3):
        return year, int(m.group(3)), None
    if m.group(4):
        month = int(m.group(4))
        return (year, None, month) if 1 <= month <= 12 else None
    return year, None, None


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
