from __future__ import annotations

from eurodata.reference.countries import COUNTRIES
from eurodata.sources.base import BaseFetcher, Record
from eurodata.sources.registry import register

_EUROPE_ISO3 = {c["iso3"] for c in COUNTRIES}


def normalize_world_bank(rows: list[dict], indicator_code: str) -> list[Record]:
    out: list[Record] = []
    for row in rows:
        iso3 = row.get("countryiso3code")
        if iso3 not in _EUROPE_ISO3 or row.get("value") is None:
            continue
        try:
            year = int(str(row["date"])[:4])
            value = float(row["value"])
        except (KeyError, ValueError, TypeError):
            continue
        out.append(Record(iso3=iso3, indicator_code=indicator_code, year=year, value=value))
    return out


@register
class WorldBankFetcher(BaseFetcher):
    source_name = "World Bank"
    # Eurostat api_code -> World Bank series (fallback coverage).
    WB_CODES = {"nama_10_gdp": "NY.GDP.MKTP.CD", "demo_pjan": "SP.POP.TOTL"}

    def fetch(self, start_year: int) -> list[Record]:
        import wbgapi as wb  # lazy import

        records: list[Record] = []
        economies = [c["iso3"] for c in COUNTRIES]
        for eu_code, wb_code in self.WB_CODES.items():
            try:
                df = wb.data.DataFrame(wb_code, economies, range(start_year, 2025),
                                       labels=False).reset_index()
                rows = []
                for _, r in df.iterrows():
                    for col in df.columns:
                        if str(col).startswith("YR"):
                            rows.append({"countryiso3code": r["economy"],
                                         "date": str(col)[2:], "value": r[col]})
                records.extend(normalize_world_bank(rows, eu_code))
            except Exception:
                continue
        return records
