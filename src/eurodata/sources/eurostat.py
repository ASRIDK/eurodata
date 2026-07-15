from __future__ import annotations

import logging
import time

from eurodata.config import get_settings
from eurodata.ingest.snapshot import save_snapshot
from eurodata.reference.countries import COUNTRIES
from eurodata.sources.base import BaseFetcher, Record, parse_period
from eurodata.sources.registry import register

logger = logging.getLogger(__name__)

# Eurostat uses a few non-ISO geo codes.
_EUROSTAT_GEO_FIX = {"EL": "GRC", "UK": "GBR"}
_ISO2_TO_ISO3 = {c["iso2"]: c["iso3"] for c in COUNTRIES}

_API_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
_CONNECT_TIMEOUT, _READ_TIMEOUT = 10, 60
_RETRIES = 3

# api_code (= Eurostat dataset id) -> dimension filters that pin the query to
# exactly one series per country/year. Verified against the live JSON API.
SERIES_PARAMS: dict[str, dict[str, str]] = {
    # Median age of population on 1 January, years
    "demo_pjanind": {"indic_de": "MEDAGEPOP"},
    # HICP all-items, annual average rate of change, %
    "prc_hicp_aind": {"unit": "RCH_A_AVG", "coicop": "CP00"},
    # Enterprises (10+ employees, business economy) using any AI technology, %
    "isoc_eb_ai": {"indic_is": "E_AI_TANY", "unit": "PC_ENT",
                   "size_emp": "GE10", "nace_r2": "C10-S951_X_K"},
    # ICT specialists, % of total employment
    "isoc_sks_itspt": {"unit": "PC_EMP"},
    # Enterprise birth rate, % of active enterprises (business economy
    # except holding companies); dataset ends 2020
    "bd_9bd_sz_cl_r2": {"indic_sb": "V97020", "sizeclas": "TOTAL",
                        "nace_r2": "B-S_X_K642"},
    # High-growth enterprises (employment definition), % of active
    # enterprises with 10+ employees; dataset ends 2020
    "bd_9pm_r2": {"indic_sb": "V97460", "nace_r2": "B-N_X_K642"},
    # HICP all-items, MONTHLY annual rate of change, %
    "prc_hicp_manr": {"unit": "RCH_A", "coicop": "CP00"},
    # GDP QUARTERLY, chain-linked volume % change vs same quarter of the
    # previous year, seasonally and calendar adjusted
    "namq_10_gdp": {"unit": "CLV_PCH_SM", "s_adj": "SCA", "na_item": "B1GQ"},
    # 2026-07-15: Social Media (usage)
    # Individuals participating in social networks, % of all individuals
    "isoc_ci_ac_i": {"indic_is": "I_IUSNET", "unit": "PC_IND",
                     "ind_type": "IND_TOTAL"},
    # Same series for the 16-24 age group; shares the dataset via #-suffix
    "isoc_ci_ac_i#Y16_24": {"indic_is": "I_IUSNET", "unit": "PC_IND",
                            "ind_type": "Y16_24"},
    # Enterprises (10+ employed) using any social media, % of enterprises;
    # biennial coverage (2014, 2015, 2017, 2019, 2021, 2023, 2025)
    "isoc_cismt": {"indic_is": "E_SM1_ANY", "unit": "PC_ENT",
                   "size_emp": "GE10", "nace_r2": "C10-S951_X_K"},
}


def _to_iso3(geo: str) -> str | None:
    if geo in _EUROSTAT_GEO_FIX:
        return _EUROSTAT_GEO_FIX[geo]
    return _ISO2_TO_ISO3.get(geo)


def dataset_id(api_code: str) -> str:
    """Eurostat dataset id for a catalog api_code. A ``#suffix`` disambiguates
    multiple catalog indicators drawn from one dataset (e.g.
    ``isoc_ci_ac_i#Y16_24``); it is stripped for the HTTP call but kept as the
    record's indicator_code so it matches the catalog row."""
    return api_code.split("#", 1)[0]


def normalize_eurostat(rows: list[dict], indicator_code: str) -> list[Record]:
    out: list[Record] = []
    for row in rows:
        iso3 = _to_iso3(str(row.get("geo", "")))
        if iso3 is None:
            continue
        period = parse_period(str(row.get("TIME_PERIOD", "")))
        if period is None:
            continue
        year, quarter, month = period
        try:
            value = float(row["value"])
        except (KeyError, ValueError, TypeError):
            continue
        out.append(Record(iso3=iso3, indicator_code=indicator_code, year=year,
                           value=value, quarter=quarter, month=month,
                           unit=row.get("unit")))
    return out


def _category_codes(dimension: dict) -> list[str]:
    """Category codes of a JSON-stat dimension, in index order."""
    index = dimension["category"]["index"]
    if isinstance(index, dict):
        return [code for code, _ in sorted(index.items(), key=lambda kv: kv[1])]
    return list(index)


def jsonstat_rows(data: dict) -> list[dict]:
    """Flatten a Eurostat JSON-stat 2.0 response into geo/TIME_PERIOD/value rows."""
    dims: list[str] = data["id"]
    sizes: list[int] = data["size"]
    codes = {d: _category_codes(data["dimension"][d]) for d in dims}
    rows: list[dict] = []
    for flat, value in data.get("value", {}).items():
        idx = int(flat)
        coords: dict[str, str] = {}
        for d, size in zip(reversed(dims), reversed(sizes)):
            coords[d] = codes[d][idx % size]
            idx //= size
        rows.append({"geo": coords.get("geo"), "TIME_PERIOD": coords.get("time"),
                     "value": value})
    return rows


@register
class EurostatFetcher(BaseFetcher):
    source_name = "Eurostat"

    def _get(self, dataset: str, params: dict[str, str]) -> dict:
        import requests  # lazy import so unit tests need no network stack

        last_exc: Exception | None = None
        for attempt in range(_RETRIES):
            try:
                resp = requests.get(_API_BASE + dataset, params=params,
                                    timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT))
                resp.raise_for_status()
                if "sorry.ec.europa.eu" in str(resp.url):
                    # Throttled: the API 307-redirects to an HTML "sorry" page
                    # with status 200; without this check it surfaces as a
                    # confusing JSON decode error.
                    raise RuntimeError(
                        "Eurostat is throttling requests (sorry service); "
                        "retry later or lower the request rate")
                data = resp.json()
                if "error" in data:
                    raise RuntimeError(f"Eurostat API error: {str(data['error'])[:200]}")
                try:  # keep the raw payload for reproducibility; never fail the fetch
                    save_snapshot(get_settings().raw_snapshot_dir, self.source_name,
                                  dataset, params, resp.content)
                except OSError as snap_exc:
                    logger.warning("snapshot for %s not saved: %s", dataset, snap_exc)
                return data
            except Exception as exc:  # noqa: BLE001 — retried, then surfaced
                last_exc = exc
                if attempt < _RETRIES - 1:
                    # throttling needs a much longer pause than a blip
                    base = 30 if "throttling" in str(exc) else 2
                    time.sleep(base * (attempt + 1))
        raise RuntimeError(f"{dataset}: {last_exc}") from last_exc

    def fetch(self, start_year: int) -> list[Record]:
        records: list[Record] = []
        for api_code, filters in SERIES_PARAMS.items():
            params = {"format": "JSON", "lang": "EN",
                      "sinceTimePeriod": str(start_year), **filters}
            try:
                data = self._get(dataset_id(api_code), params)
            except Exception as exc:  # noqa: BLE001 — recorded, not swallowed
                self.errors.append((api_code, str(exc)))
                logger.warning("Eurostat %s failed: %s", api_code, exc)
                continue
            series = normalize_eurostat(jsonstat_rows(data), api_code)
            logger.info("Eurostat %s: %d records", api_code, len(series))
            records.extend(series)
        return records
