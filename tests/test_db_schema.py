from eurodata.db import init_schema


def test_schema_creates_core_tables(memdb):
    init_schema(memdb)
    tables = {r[0] for r in memdb.execute(
        "SELECT table_name FROM information_schema.tables"
    ).fetchall()}
    for t in ["geography", "bloc", "geography_bloc", "domain", "indicator",
              "source", "statistic_record", "graph_node", "graph_edge",
              "raw_snapshot", "ingestion_run"]:
        assert t in tables


def test_statistic_vintage_uniqueness(memdb):
    init_schema(memdb)
    memdb.execute("INSERT INTO geography (id, code, level, name, iso3) "
                  "VALUES (1, 'DE', 'country', 'Germany', 'DEU')")
    memdb.execute("INSERT INTO domain (id, name) VALUES (1, 'Economy')")
    memdb.execute("INSERT INTO indicator (id, domain_id, name) VALUES (1, 1, 'GDP')")
    memdb.execute("INSERT INTO source (id, name, redistributable) VALUES (1, 'Eurostat', TRUE)")
    row = ("INSERT INTO statistic_record "
           "(geography_id, indicator_id, source_id, year, value, vintage_date) "
           "VALUES (1, 1, 1, 2020, 100, DATE '2021-01-01')")
    memdb.execute(row)
    # same series, NEW vintage -> allowed (revision history)
    memdb.execute(row.replace("2021-01-01", "2022-01-01").replace("100", "105"))
    count = memdb.execute("SELECT COUNT(*) FROM statistic_record").fetchone()[0]
    assert count == 2
