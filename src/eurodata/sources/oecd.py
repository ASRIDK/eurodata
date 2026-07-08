from __future__ import annotations

from eurodata.reference.countries import COUNTRIES
from eurodata.sources.base import BaseFetcher, Record
from eurodata.sources.registry import register

_EUROPE_ISO3 = {c["iso3"] for c in COUNTRIES}


def normalize_oecd(rows: list[dict], indicator_code: str) -> list[Record]:
    out: list[Record] = []
    for row in rows:
        iso3 = str(row.get("LOCATION", ""))
        if iso3 not in _EUROPE_ISO3:
            continue
        try:
            year = int(str(row["TIME_PERIOD"])[:4])
            value = float(row["ObsValue"])
        except (KeyError, ValueError, TypeError):
            continue
        out.append(Record(iso3=iso3, indicator_code=indicator_code, year=year, value=value))
    return out


@register
class OECDFetcher(BaseFetcher):
    source_name = "OECD"

    def fetch(self, start_year: int) -> list[Record]:
        # OECD SDMX wiring added when specific dataflow keys are finalized.
        return []
