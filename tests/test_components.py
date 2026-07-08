import datetime as dt
import duckdb

from eurodata.db import init_schema
from eurodata.model.seed import seed_all
from eurodata.ingest.pipeline import load_records
from eurodata.sources.base import Record
from app.components import indicator_timeseries


def _db():
    con = duckdb.connect(":memory:")
    for seq in ["seq_statistic", "seq_edge", "seq_snapshot", "seq_run"]:
        con.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} START 1")
    init_schema(con)
    seed_all(con)
    load_records(con, "Eurostat",
                 [Record("DEU", "nama_10_gdp", 2019, 90.0),
                  Record("DEU", "nama_10_gdp", 2020, 100.0)],
                 vintage=dt.date(2021, 1, 1))
    return con


def test_indicator_timeseries_returns_sorted_rows():
    con = _db()
    df = indicator_timeseries(con, iso3="DEU", indicator_name="GDP")
    assert list(df["year"]) == [2019, 2020]
    assert list(df["value"]) == [90.0, 100.0]
