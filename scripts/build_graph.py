"""Rebuild the structural graph from current data."""
from _bootstrap import ensure_paths

ensure_paths()

from eurodata.db import connect
from eurodata.graph.build import build_graph
from eurodata.graph.metrics import to_networkx, degree_centrality

if __name__ == "__main__":
    con = connect()
    try:
        build_graph(con)
        g = to_networkx(con)
        top = sorted(degree_centrality(g).items(), key=lambda kv: kv[1], reverse=True)[:5]
        print(f"Graph: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges")
        for nid, score in top:
            print(f"  {g.nodes[nid]['label']}: {score:.3f}")
    finally:
        con.close()
