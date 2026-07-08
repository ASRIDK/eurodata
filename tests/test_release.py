import datetime as dt
import duckdb

from eurodata.db import init_schema
from eurodata.model.seed import seed_all
from eurodata.ingest.pipeline import load_records
from eurodata.sources.base import Record
from eurodata.export.release import export_facts


def _db_with_data():
    con = duckdb.connect(":memory:")
    for seq in ["seq_statistic", "seq_edge", "seq_snapshot", "seq_run"]:
        con.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} START 1")
    init_schema(con)
    seed_all(con)
    # Make World Bank non-redistributable to prove filtering.
    con.execute("UPDATE source SET redistributable = FALSE WHERE name = 'World Bank'")
    load_records(con, "Eurostat", [Record("DEU", "nama_10_gdp", 2020, 100.0)], vintage=dt.date(2021, 1, 1))
    load_records(con, "World Bank", [Record("FRA", "nama_10_gdp", 2020, 200.0)], vintage=dt.date(2021, 1, 1))
    return con


def test_export_facts_excludes_non_redistributable(tmp_path):
    con = _db_with_data()
    out = export_facts(con, tmp_path)
    assert out.exists()
    df = duckdb.connect(":memory:").execute(
        f"SELECT * FROM read_parquet('{out}')").fetchdf()
    assert (df["source_name"] == "Eurostat").all()
    assert "World Bank" not in set(df["source_name"])
