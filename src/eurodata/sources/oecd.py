"""OECD fetcher (sdmx.oecd.org REST API, SDMX-CSV format).

Series wired:
- DF_IALFS_UNE_M — monthly unemployment rate, % of the labour force,
  seasonally adjusted, 15+ (dataflow OECD.SDD.TPS:DSD_LFS@DF_IALFS_UNE_M).
  Covers OECD members only; non-OECD European countries have no rows.
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

_EUROPE_ISO3 = {c["iso3"] for c in COUNTRIES}

_API_BASE = "https://sdmx.oecd.org/public/rest/data/"
_CONNECT_TIMEOUT, _READ_TIMEOUT = 10, 120
_RETRIES = 3

# api_code -> (dataflow reference, series key, unit). REF_AREA is left empty
# (= all countries); aggregates (EA, EU, G7, OECD) and non-European members
# are dropped in normalize_oecd.
SERIES_KEYS: dict[str, tuple[str, str, str]] = {
    "DF_IALFS_UNE_M": (
        "OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0",
        ".UNE_LF_M...Y._T.Y_GE15..M",
        "%",
    ),
}


def normalize_oecd(rows: list[dict], indicator_code: str,
                   unit: str | None = None) -> list[Record]:
    """SDMX-CSV rows: REF_AREA is ISO3; aggregates and non-Europe dropped."""
    out: list[Record] = []
    for row in rows:
        iso3 = str(row.get("REF_AREA", ""))
        if iso3 not in _EUROPE_ISO3:
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
                          value=value, quarter=quarter, month=month, unit=unit))
    return out


@register
class OECDFetcher(BaseFetcher):
    source_name = "OECD"

    def _get_csv(self, dataflow: str, key: str, start_year: int) -> list[dict]:
        import requests  # lazy import so unit tests need no network stack

        url = f"{_API_BASE}{dataflow}/{key}"
        params = {"startPeriod": f"{start_year}-01"}
        headers = {"Accept": "application/vnd.sdmx.data+csv"}
        last_exc: Exception | None = None
        for attempt in range(_RETRIES):
            try:
                resp = requests.get(url, params=params, headers=headers,
                                    timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT))
                resp.raise_for_status()
                try:  # keep the raw payload for reproducibility; never fail the fetch
                    save_snapshot(get_settings().raw_snapshot_dir, self.source_name,
                                  dataflow, params, resp.content)
                except OSError as snap_exc:
                    logger.warning("snapshot for %s not saved: %s", dataflow, snap_exc)
                return list(csv.DictReader(io.StringIO(resp.text)))
            except Exception as exc:  # noqa: BLE001 — retried, then surfaced
                last_exc = exc
                if attempt < _RETRIES - 1:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"{dataflow}: {last_exc}") from last_exc

    def fetch(self, start_year: int) -> list[Record]:
        records: list[Record] = []
        for api_code, (dataflow, key, unit) in SERIES_KEYS.items():
            try:
                rows = self._get_csv(dataflow, key, start_year)
            except Exception as exc:  # noqa: BLE001 — recorded, not swallowed
                self.errors.append((api_code, str(exc)))
                logger.warning("OECD %s failed: %s", api_code, exc)
                continue
            series = normalize_oecd(rows, api_code, unit=unit)
            logger.info("OECD %s: %d records", api_code, len(series))
            records.extend(series)
        return records
