import duckdb
from eurodata.db import init_schema
from eurodata.model.seed import seed_all
from eurodata.graph.build import build_graph


def _seeded():
    con = duckdb.connect(":memory:")
    for seq in ["seq_statistic", "seq_edge", "seq_snapshot", "seq_run"]:
        con.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} START 1")
    init_schema(con)
    seed_all(con)
    return con


def test_build_graph_creates_nodes_and_edges():
    con = _seeded()
    build_graph(con)
    node_types = dict(con.execute(
        "SELECT node_type, COUNT(*) FROM graph_node GROUP BY node_type").fetchall())
    assert node_types["country"] >= 40
    assert node_types["indicator"] == 26
    assert node_types["domain"] == 6
    edge_types = {r[0] for r in con.execute("SELECT DISTINCT edge_type FROM graph_edge").fetchall()}
    assert {"MEMBER_OF", "BORDERS", "BELONGS_TO", "PROVIDES"} <= edge_types


def test_build_graph_is_idempotent():
    con = _seeded()
    build_graph(con)
    first = con.execute("SELECT COUNT(*) FROM graph_edge").fetchone()[0]
    build_graph(con)
    assert con.execute("SELECT COUNT(*) FROM graph_edge").fetchone()[0] == first
