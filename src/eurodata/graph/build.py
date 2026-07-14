from __future__ import annotations

import json

import duckdb

from eurodata.graph.correlate import compute_correlation_edges
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

    def edge(src, dst, etype, weight=1.0, props=None):
        con.execute("INSERT INTO graph_edge (src_node_id, dst_node_id, edge_type, weight, props) "
                    "VALUES (?, ?, ?, ?, ?)", [src, dst, etype, weight, props])

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
            # Borders are a symmetric relation; the graph itself is directed
            # (to represent CORRELATES_WITH lead/lag direction below), so
            # store both directions to keep BORDERS behaving as undirected.
            n1, n2 = country_node[iso3_to_cid[a]], country_node[iso3_to_cid[b]]
            edge(n1, n2, "BORDERS")
            edge(n2, n1, "BORDERS")

    # CORRELATES_WITH: indicator<->indicator, growth-rate correlation pooled
    # across countries, FDR-corrected across all pairs tested. See
    # eurodata.graph.correlate for the full methodology. Edge direction
    # (src -> dst) follows the Granger-style lead/lag verdict when there is
    # one; otherwise it's an arbitrary (indicator_a -> indicator_b) ordering
    # and props["direction"] == "undetermined" says so explicitly.
    for result in compute_correlation_edges(con):
        src, dst = indicator_node[result.indicator_a], indicator_node[result.indicator_b]
        if result.direction == "b_leads_a":
            src, dst = dst, src
        props = json.dumps({
            "q_value": result.q_value,
            "p_value": result.p_value,
            "n_countries": result.n_countries,
            "relationship": result.relationship,
            "direction": result.direction,
            "granger_p_a_to_b": result.granger_p_a_to_b,
            "granger_p_b_to_a": result.granger_p_b_to_a,
            "per_country": result.per_country,
            "method": ("Pearson r on YoY growth rate per country, pooled via a "
                       "Fisher-z-weighted average; tested contemporaneously and at "
                       "a 1-year lag in both directions, the strongest of the three "
                       "wins ('relationship'), Bonferroni-adjusted for the tests "
                       "tried on this pair; direction (when present) additionally "
                       "requires a one-sided per-country lag-1 Granger causality "
                       "result, combined across countries via Fisher's method; "
                       "q_value is Benjamini-Hochberg FDR-corrected across every "
                       "indicator pair tested."),
        })
        edge(src, dst, "CORRELATES_WITH", weight=result.weight, props=props)
