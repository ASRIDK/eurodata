import datetime as dt
import duckdb

from eurodata.db import init_schema
from eurodata.model.seed import seed_all
from eurodata.sources.base import Record
from eurodata.ingest.pipeline import load_records


def _fresh_db():
    con = duckdb.connect(":memory:")
    for seq in ["seq_statistic", "seq_edge", "seq_snapshot", "seq_run"]:
        con.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} START 1")
    init_schema(con)
    seed_all(con)
    return con


def test_load_records_inserts_and_logs():
    con = _fresh_db()
    recs = [Record("DEU", "nama_10_gdp", 2020, 100.0, unit="EUR")]
    n = load_records(con, "Eurostat", recs, vintage=dt.date(2021, 1, 1))
    assert n == 1
    assert con.execute("SELECT COUNT(*) FROM statistic_record").fetchone()[0] == 1
    assert con.execute("SELECT status FROM ingestion_run").fetchone()[0] == "completed"


def test_new_vintage_preserved_current_view_picks_latest():
    con = _fresh_db()
    load_records(con, "Eurostat", [Record("DEU", "nama_10_gdp", 2020, 100.0)], vintage=dt.date(2021, 1, 1))
    load_records(con, "Eurostat", [Record("DEU", "nama_10_gdp", 2020, 105.0)], vintage=dt.date(2022, 1, 1))
    assert con.execute("SELECT COUNT(*) FROM statistic_record").fetchone()[0] == 2
    val = con.execute("SELECT value FROM statistic_current").fetchone()[0]
    assert val == 105.0
