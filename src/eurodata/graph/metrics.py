from __future__ import annotations

import duckdb
import networkx as nx


def to_networkx(con: duckdb.DuckDBPyConnection) -> nx.Graph:
    g = nx.Graph()
    for nid, ntype, label in con.execute(
            "SELECT id, node_type, label FROM graph_node").fetchall():
        g.add_node(nid, node_type=ntype, label=label)
    for src, dst, etype, weight in con.execute(
            "SELECT src_node_id, dst_node_id, edge_type, weight FROM graph_edge").fetchall():
        g.add_edge(src, dst, edge_type=etype, weight=weight)
    return g


def degree_centrality(g: nx.Graph) -> dict[int, float]:
    return nx.degree_centrality(g)


def communities(g: nx.Graph) -> list[set[int]]:
    if g.number_of_edges() == 0:
        return [set(g.nodes())] if g.number_of_nodes() else []
    return list(nx.community.louvain_communities(g, seed=42))
