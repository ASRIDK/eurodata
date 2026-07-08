import duckdb
from eurodata.db import init_schema
from eurodata.model.seed import seed_all
from eurodata.graph.build import build_graph
from eurodata.graph.metrics import to_networkx, degree_centrality, communities


def _graph_db():
    con = duckdb.connect(":memory:")
    for seq in ["seq_statistic", "seq_edge", "seq_snapshot", "seq_run"]:
        con.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} START 1")
    init_schema(con)
    seed_all(con)
    build_graph(con)
    return con


def test_to_networkx_and_metrics():
    con = _graph_db()
    g = to_networkx(con)
    assert g.number_of_nodes() > 0 and g.number_of_edges() > 0
    dc = degree_centrality(g)
    assert abs(sum(dc.values()) - sum(dc.values())) < 1e-9  # all floats
    comms = communities(g)
    covered = set().union(*comms) if comms else set()
    assert covered == set(g.nodes())
