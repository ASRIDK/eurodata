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

    @abstractmethod
    def fetch(self, start_year: int) -> list[Record]:
        """Return normalized records from the live source."""
        raise NotImplementedError
