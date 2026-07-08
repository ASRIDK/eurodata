from __future__ import annotations

from eurodata.reference.countries import COUNTRIES
from eurodata.sources.base import BaseFetcher, Record
from eurodata.sources.registry import register

_ISO2_TO_ISO3 = {c["iso2"]: c["iso3"] for c in COUNTRIES}


def normalize_ecb(rows: list[dict], indicator_code: str) -> list[Record]:
    out: list[Record] = []
    for row in rows:
        iso3 = _ISO2_TO_ISO3.get(str(row.get("REF_AREA", "")))
        if iso3 is None:
            continue
        try:
            year = int(str(row["TIME_PERIOD"])[:4])
            value = float(row["OBS_VALUE"])
        except (KeyError, ValueError, TypeError):
            continue
        out.append(Record(iso3=iso3, indicator_code=indicator_code, year=year,
                           value=value, currency=row.get("CURRENCY")))
    return out


@register
class ECBFetcher(BaseFetcher):
    source_name = "ECB"

    def fetch(self, start_year: int) -> list[Record]:
        # ECB SDMX wiring added when specific series keys are finalized.
        return []
