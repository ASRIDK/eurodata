from __future__ import annotations

import datetime as dt
import logging

import duckdb

from eurodata.ingest.validate import validate_records
from eurodata.sources.base import Record
from eurodata.sources.registry import get_fetcher, all_sources

logger = logging.getLogger(__name__)


def _lookup(con, table, where_col, where_val):
    row = con.execute(f"SELECT id FROM {table} WHERE {where_col} = ?", [where_val]).fetchone()
    return row[0] if row else None


def load_records(con: duckdb.DuckDBPyConnection, source_name: str,
                 records: list[Record], vintage: dt.date | None = None) -> int:
    started = dt.datetime.now()
    source_id = _lookup(con, "source", "name", source_name)
    if source_id is None:
        raise ValueError(f"Unknown source: {source_name}")

    valid, rejected = validate_records(records)
    geo_ids = {iso3: gid for gid, iso3 in con.execute("SELECT id, iso3 FROM geography").fetchall()}
    ind_ids = {code: iid for iid, code in
               con.execute("SELECT id, api_code FROM indicator WHERE api_code IS NOT NULL").fetchall()}

    count = 0
    for r in valid:
        gid = geo_ids.get(r.iso3)
        iid = ind_ids.get(r.indicator_code)
        if gid is None or iid is None:
            continue
        con.execute(
            "INSERT INTO statistic_record "
            "(geography_id, indicator_id, source_id, year, quarter, month, value, "
            " unit, currency, price_basis, vintage_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            [gid, iid, source_id, r.year, r.quarter, r.month, r.value,
             r.unit, r.currency, r.price_basis, vintage],
        )
        count += 1

    con.execute(
        "INSERT INTO ingestion_run (source, started_at, ended_at, status, records_processed) "
        "VALUES (?, ?, ?, 'completed', ?)",
        [source_name, started, dt.datetime.now(), count],
    )
    logger.info("%s: %d records loaded, %d rejected", source_name, count, len(rejected))
    return count


def run_source(con: duckdb.DuckDBPyConnection, source_name: str, start_year: int) -> int:
    fetcher = get_fetcher(source_name)
    try:
        records = fetcher.fetch(start_year)
    except Exception as exc:  # log failure, keep pipeline alive
        con.execute(
            "INSERT INTO ingestion_run (source, started_at, ended_at, status, error) "
            "VALUES (?, ?, ?, 'failed', ?)",
            [source_name, dt.datetime.now(), dt.datetime.now(), str(exc)],
        )
        logger.error("%s fetch failed: %s", source_name, exc)
        return 0
    return load_records(con, source_name, records, vintage=dt.date.today())


def run_all(con: duckdb.DuckDBPyConnection, start_year: int) -> dict[str, int]:
    return {name: run_source(con, name, start_year) for name in all_sources()}
