from __future__ import annotations

import duckdb

from eurodata.reference.borders import BORDERS


def _node_id(con, node_type: str, ref_id: int, label: str, counter: list[int]) -> int:
    existing = con.execute(
        "SELECT id FROM graph_node WHERE node_type = ? AND ref_id = ?",
        [node_type, ref_id]).fetchone()
    if existing:
        return existing[0]
    counter[0] += 1
    nid = counter[0]
    con.execute("INSERT INTO graph_node (id, node_type, ref_id, label) VALUES (?, ?, ?, ?)",
                [nid, node_type, ref_id, label])
    return nid


def build_graph(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("DELETE FROM graph_edge")
    con.execute("DELETE FROM graph_node")
    counter = [0]

    countries = con.execute("SELECT id, iso3, name FROM geography WHERE level='country'").fetchall()
    indicators = con.execute("SELECT id, name, domain_id FROM indicator").fetchall()
    domains = con.execute("SELECT id, name FROM domain").fetchall()
    sources = con.execute("SELECT id, name FROM source").fetchall()
    blocs = con.execute("SELECT id, name FROM bloc").fetchall()

    country_node = {cid: _node_id(con, "country", cid, name, counter) for cid, iso3, name in countries}
    iso3_to_cid = {iso3: cid for cid, iso3, _ in countries}
    domain_node = {did: _node_id(con, "domain", did, name, counter) for did, name in domains}
    indicator_node = {iid: _node_id(con, "indicator", iid, name, counter) for iid, name, _ in indicators}
    source_node = {sid: _node_id(con, "source", sid, name, counter) for sid, name in sources}
    bloc_node = {bid: _node_id(con, "bloc", bid, name, counter) for bid, name in blocs}

    def edge(src, dst, etype, weight=1.0):
        con.execute("INSERT INTO graph_edge (src_node_id, dst_node_id, edge_type, weight) "
                    "VALUES (?, ?, ?, ?)", [src, dst, etype, weight])

    for iid, _, did in indicators:
        edge(indicator_node[iid], domain_node[did], "BELONGS_TO")
    # PROVIDES reflects what was actually ingested, not the full source catalog.
    for sid, iid in con.execute(
            "SELECT DISTINCT source_id, indicator_id FROM statistic_record").fetchall():
        if sid in source_node and iid in indicator_node:
            edge(source_node[sid], indicator_node[iid], "PROVIDES")
    for cid, bid in con.execute(
            "SELECT geography_id, bloc_id FROM geography_bloc").fetchall():
        if cid in country_node and bid in bloc_node:
            edge(country_node[cid], bloc_node[bid], "MEMBER_OF")
    for a, b in BORDERS:
        if a in iso3_to_cid and b in iso3_to_cid:
            edge(country_node[iso3_to_cid[a]], country_node[iso3_to_cid[b]], "BORDERS")
