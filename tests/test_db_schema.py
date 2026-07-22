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


def _seed_refs(con):
    con.execute("INSERT INTO geography (id, code, level, name, iso3) "
                "VALUES (1, 'DE', 'country', 'Germany', 'DEU')")
    con.execute("INSERT INTO domain (id, name) VALUES (1, 'Economy')")
    con.execute("INSERT INTO indicator (id, domain_id, name) VALUES (1, 1, 'GDP')")
    con.execute("INSERT INTO source (id, name, redistributable) VALUES (1, 'Eurostat', TRUE)")


def test_absent_subannual_defaults_to_zero_not_null(memdb):
    """Annual rows omit quarter/month; the NOT NULL sentinel fills them with 0."""
    init_schema(memdb)
    _seed_refs(memdb)
    memdb.execute("INSERT INTO statistic_record "
                  "(geography_id, indicator_id, source_id, year, value, vintage_date) "
                  "VALUES (1, 1, 1, 2020, 100, DATE '2021-01-01')")
    q, m = memdb.execute("SELECT quarter, month FROM statistic_record").fetchone()
    assert (q, m) == (0, 0)


def test_reingesting_identical_row_is_deduped(memdb):
    """The whole point of the sentinel: ON CONFLICT DO NOTHING now fires for an
    identical annual row (quarter/month 0, not NULL), so re-ingestion is a no-op
    instead of silently accumulating exact duplicates."""
    init_schema(memdb)
    _seed_refs(memdb)
    insert = ("INSERT INTO statistic_record "
              "(geography_id, indicator_id, source_id, year, quarter, month, value, vintage_date) "
              "VALUES (1, 1, 1, 2020, 0, 0, 100, DATE '2021-01-01') "
              "ON CONFLICT DO NOTHING RETURNING id")
    first = memdb.execute(insert).fetchall()
    second = memdb.execute(insert).fetchall()  # same key, same vintage
    count = memdb.execute("SELECT COUNT(*) FROM statistic_record").fetchone()[0]
    assert len(first) == 1      # first insert returns the new id
    assert len(second) == 0     # conflict -> nothing inserted, nothing returned
    assert count == 1           # exactly one row survives
