from __future__ import annotations

import json

import duckdb
import networkx as nx


def to_networkx(con: duckdb.DuckDBPyConnection) -> nx.DiGraph:
    """Directed so CORRELATES_WITH edges can carry a lead/lag direction.

    BORDERS is stored as both (a, b) and (b, a) rows by `build_graph` to stay
    effectively undirected here; MEMBER_OF/BELONGS_TO/PROVIDES are naturally
    one-directional already.
    """
    g = nx.DiGraph()
    for nid, ntype, label in con.execute(
            "SELECT id, node_type, label FROM graph_node").fetchall():
        g.add_node(nid, node_type=ntype, label=label)
    for src, dst, etype, weight, props in con.execute(
            "SELECT src_node_id, dst_node_id, edge_type, weight, props FROM graph_edge").fetchall():
        attrs = {"edge_type": etype, "weight": weight}
        if props:
            attrs["props"] = json.loads(props)
        g.add_edge(src, dst, **attrs)
    return g


def degree_centrality(g: nx.DiGraph) -> dict[int, float]:
    return nx.degree_centrality(g)


def communities(g: nx.DiGraph) -> list[set[int]]:
    if g.number_of_edges() == 0:
        return [set(g.nodes())] if g.number_of_nodes() else []
    return list(nx.community.louvain_communities(g, seed=42))
