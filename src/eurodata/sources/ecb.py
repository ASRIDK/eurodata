"""ECB Data Portal fetcher (SDMX 2.1 REST, CSV format).

Monthly series wired:
- IRS  — long-term interest rates (10y government bond yields, Maastricht
         convergence criterion), one series per EU country (REF_AREA).
- EXR  — ECB reference exchange rates against the euro, one series per
         currency; mapped to the issuing country, so euro-area countries
         have no rows by construction.
"""
from __future__ import annotations

import csv
import io
import logging
import time

from eurodata.config import get_settings
from eurodata.ingest.snapshot import save_snapshot
from eurodata.reference.countries import COUNTRIES
from eurodata.sources.base import BaseFetcher, Record, parse_period
from eurodata.sources.registry import register

logger = logging.getLogger(__name__)

_ISO2_TO_ISO3 = {c["iso2"]: c["iso3"] for c in COUNTRIES}

# Non-euro European currencies published in the ECB reference rates -> country.
# RUB was suspended in March 2022; its historical rows are still valid data.
_CURRENCY_TO_ISO3 = {
    "GBP": "GBR", "SEK": "SWE", "NOK": "NOR", "DKK": "DNK", "CHF": "CHE",
    "PLN": "POL", "CZK": "CZE", "HUF": "HUN", "RON": "ROU", "BGN": "BGR",
    "ISK": "ISL", "TRY": "TUR", "RUB": "RUS",
}

_API_BASE = "https://data-api.ecb.europa.eu/service/data/"
_CONNECT_TIMEOUT, _READ_TIMEOUT = 10, 120
_RETRIES = 3

# api_code (matches indicator.api_code in the catalog) -> (dataflow, series
# key with the REF_AREA / CURRENCY dimension left empty = all members).
SERIES_KEYS: dict[str, tuple[str, str]] = {
    "IRS": ("IRS", "M..L.L40.CI.0000.EUR.N.Z"),
    "EXR": ("EXR", "M..EUR.SP00.A"),
}


def normalize_ecb(rows: list[dict], indicator_code: str) -> list[Record]:
    """Rows keyed by REF_AREA (ISO2 country), e.g. the IRS dataflow."""
    out: list[Record] = []
    for row in rows:
        iso3 = _ISO2_TO_ISO3.get(str(row.get("REF_AREA", "")))
        if iso3 is None:
            continue
        period = parse_period(str(row.get("TIME_PERIOD", "")))
        if period is None:
            continue
        year, quarter, month = period
        try:
            value = float(row["OBS_VALUE"])
        except (KeyError, ValueError, TypeError):
            continue
        out.append(Record(iso3=iso3, indicator_code=indicator_code, year=year,
                          value=value, quarter=quarter, month=month,
                          currency=row.get("CURRENCY")))
    return out


def normalize_ecb_exr(rows: list[dict], indicator_code: str) -> list[Record]:
    """EXR rows are keyed by CURRENCY, not country; map to the issuer."""
    out: list[Record] = []
    for row in rows:
        currency = str(row.get("CURRENCY", ""))
        iso3 = _CURRENCY_TO_ISO3.get(currency)
        if iso3 is None:
            continue
        period = parse_period(str(row.get("TIME_PERIOD", "")))
        if period is None:
            continue
        year, quarter, month = period
        try:
            value = float(row["OBS_VALUE"])
        except (KeyError, ValueError, TypeError):
            continue
        out.append(Record(iso3=iso3, indicator_code=indicator_code, year=year,
                          value=value, quarter=quarter, month=month,
                          currency=currency, unit=f"{currency} per EUR"))
    return out


@register
class ECBFetcher(BaseFetcher):
    source_name = "ECB"

    def _get_csv(self, flow: str, key: str, start_year: int) -> list[dict]:
        import requests  # lazy import so unit tests need no network stack

        url = f"{_API_BASE}{flow}/{key}"
        params = {"startPeriod": str(start_year), "format": "csvdata"}
        last_exc: Exception | None = None
        for attempt in range(_RETRIES):
            try:
                resp = requests.get(url, params=params,
                                    timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT))
                resp.raise_for_status()
                try:  # keep the raw payload for reproducibility; never fail the fetch
                    save_snapshot(get_settings().raw_snapshot_dir, self.source_name,
                                  f"{flow}/{key}", params, resp.content)
                except OSError as snap_exc:
                    logger.warning("snapshot for %s not saved: %s", flow, snap_exc)
                return list(csv.DictReader(io.StringIO(resp.text)))
            except Exception as exc:  # noqa: BLE001 — retried, then surfaced
                last_exc = exc
                if attempt < _RETRIES - 1:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"{flow}/{key}: {last_exc}") from last_exc

    def fetch(self, start_year: int) -> list[Record]:
        records: list[Record] = []
        for api_code, (flow, key) in SERIES_KEYS.items():
            try:
                rows = self._get_csv(flow, key, start_year)
            except Exception as exc:  # noqa: BLE001 — recorded, not swallowed
                self.errors.append((api_code, str(exc)))
                logger.warning("ECB %s failed: %s", api_code, exc)
                continue
            normalize = normalize_ecb_exr if api_code == "EXR" else normalize_ecb
            series = normalize(rows, api_code)
            logger.info("ECB %s: %d records", api_code, len(series))
            records.extend(series)
        return records
