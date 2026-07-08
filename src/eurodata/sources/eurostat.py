from __future__ import annotations

from eurodata.reference.countries import COUNTRIES
from eurodata.sources.base import BaseFetcher, Record
from eurodata.sources.registry import register

# Eurostat uses a few non-ISO geo codes.
_EUROSTAT_GEO_FIX = {"EL": "GRC", "UK": "GBR"}
_ISO2_TO_ISO3 = {c["iso2"]: c["iso3"] for c in COUNTRIES}


def _to_iso3(geo: str) -> str | None:
    if geo in _EUROSTAT_GEO_FIX:
        return _EUROSTAT_GEO_FIX[geo]
    return _ISO2_TO_ISO3.get(geo)


def normalize_eurostat(rows: list[dict], indicator_code: str) -> list[Record]:
    out: list[Record] = []
    for row in rows:
        iso3 = _to_iso3(str(row.get("geo", "")))
        if iso3 is None:
            continue
        try:
            year = int(str(row["TIME_PERIOD"])[:4])
            value = float(row["value"])
        except (KeyError, ValueError, TypeError):
            continue
        out.append(Record(iso3=iso3, indicator_code=indicator_code, year=year,
                           value=value, unit=row.get("unit")))
    return out


@register
class EurostatFetcher(BaseFetcher):
    source_name = "Eurostat"

    def fetch(self, start_year: int) -> list[Record]:
        import sdmx  # imported lazily so tests need no network

        from eurodata.reference.catalog import INDICATORS
        client = sdmx.Request("ESTAT")
        records: list[Record] = []
        for ind in INDICATORS:
            try:
                resp = client.data(ind["api_code"], params={"startPeriod": str(start_year)})
                df = resp.to_pandas().reset_index()
                df = df.rename(columns={0: "value", "value": "value"})
                rows = df.to_dict("records")
                records.extend(normalize_eurostat(rows, ind["api_code"]))
            except Exception:
                continue
        return records
