import datetime as dt

import duckdb
from eurodata.db import init_schema
from eurodata.ingest.pipeline import load_records
from eurodata.model.seed import seed_all
from eurodata.graph.build import build_graph
from eurodata.sources.base import Record


def _seeded():
    con = duckdb.connect(":memory:")
    for seq in ["seq_statistic", "seq_edge", "seq_snapshot", "seq_run"]:
        con.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} START 1")
    init_schema(con)
    seed_all(con)
    return con


def test_build_graph_creates_nodes_and_edges():
    con = _seeded()
    load_records(con, "Eurostat", [Record("DEU", "nama_10_gdp", 2020, 100.0)],
                 vintage=dt.date(2021, 1, 1))
    build_graph(con)
    node_types = dict(con.execute(
        "SELECT node_type, COUNT(*) FROM graph_node GROUP BY node_type").fetchall())
    assert node_types["country"] >= 40
    assert node_types["indicator"] == 48
    assert node_types["domain"] == 9
    edge_types = {r[0] for r in con.execute("SELECT DISTINCT edge_type FROM graph_edge").fetchall()}
    assert {"MEMBER_OF", "BORDERS", "BELONGS_TO", "PROVIDES"} <= edge_types
    # PROVIDES mirrors ingested data: exactly one source/indicator pair here.
    assert con.execute(
        "SELECT COUNT(*) FROM graph_edge WHERE edge_type = 'PROVIDES'").fetchone()[0] == 1


def test_build_graph_is_idempotent():
    con = _seeded()
    build_graph(con)
    first = con.execute("SELECT COUNT(*) FROM graph_edge").fetchone()[0]
    build_graph(con)
    assert con.execute("SELECT COUNT(*) FROM graph_edge").fetchone()[0] == first
