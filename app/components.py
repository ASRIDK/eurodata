"""Data-access + figure helpers for the eurodata dashboard.

Kept free of any Streamlit import so they stay unit-testable; the app layer
adds caching. Every function takes an open DuckDB connection.
"""
from __future__ import annotations

import duckdb
import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from eurodata.graph.metrics import communities, degree_centrality, to_networkx

# ---------------------------------------------------------------------------
# Reference lists
# ---------------------------------------------------------------------------

def list_countries(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        "SELECT iso3, name FROM geography WHERE level='country' "
        "AND iso3 IS NOT NULL ORDER BY name"
    ).fetchdf()


def list_indicators(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Indicators that actually have at least one fact, with domain + unit."""
    return con.execute(
        "SELECT i.name, d.name AS domain, i.unit, "
        "       count(b.geography_id) AS rows "
        "FROM indicator i JOIN domain d ON d.id = i.domain_id "
        "LEFT JOIN statistic_best b ON b.indicator_id = i.id "
        "GROUP BY 1, 2, 3 HAVING count(b.geography_id) > 0 "
        "ORDER BY d.name, i.name"
    ).fetchdf()


def indicators_in_domain(con: duckdb.DuckDBPyConnection, domain: str) -> list[str]:
    df = list_indicators(con)
    return df[df["domain"] == domain]["name"].tolist()


def indicator_unit(con: duckdb.DuckDBPyConnection, indicator_name: str) -> str:
    row = con.execute(
        "SELECT unit FROM indicator WHERE name = ?", [indicator_name]
    ).fetchone()
    return (row[0] if row and row[0] else "") or ""


def indicator_meta(con: duckdb.DuckDBPyConnection, indicator_name: str) -> dict:
    """Unit / definition / proxy status for one indicator."""
    row = con.execute(
        "SELECT i.unit, i.definition, i.is_proxy, i.proxy_note, d.name, i.api_code "
        "FROM indicator i JOIN domain d ON d.id = i.domain_id WHERE i.name = ?",
        [indicator_name]).fetchone()
    if row is None:
        return {"unit": "", "definition": None, "is_proxy": False,
                "proxy_note": None, "domain": None, "api_code": None}
    return {"unit": row[0] or "", "definition": row[1], "is_proxy": bool(row[2]),
            "proxy_note": row[3], "domain": row[4], "api_code": row[5]}


def catalog_table(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Full indicator catalog with provenance and coverage (incl. empty ones)."""
    return con.execute(
        """
        SELECT i.name AS indicator, d.name AS domain, i.unit, i.api_code,
               i.definition, i.is_proxy, i.proxy_note,
               count(s.value) AS rows, count(DISTINCT s.geography_id) AS countries,
               min(s.year) AS first_year, max(s.year) AS last_year
        FROM indicator i
        JOIN domain d ON d.id = i.domain_id
        LEFT JOIN statistic_best s ON s.indicator_id = i.id
        GROUP BY i.name, d.name, i.unit, i.api_code, i.definition,
                 i.is_proxy, i.proxy_note, d.id, i.id
        ORDER BY d.id, i.id
        """).fetchdf()


def sources_table(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        "SELECT name, organization, url, license, redistributable, "
        "update_frequency FROM source ORDER BY id").fetchdf()


def ingestion_runs(con: duckdb.DuckDBPyConnection, limit: int = 20) -> pd.DataFrame:
    return con.execute(
        "SELECT source, started_at, status, records_processed, error "
        "FROM ingestion_run ORDER BY started_at DESC LIMIT ?", [limit]).fetchdf()


def full_extract(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Tidy dataset extract (for CSV download)."""
    return con.execute(
        """
        SELECT g.iso3, g.name AS country, d.name AS domain, i.name AS indicator,
               s.year, s.value, coalesce(s.unit, i.unit) AS unit,
               src.name AS source, i.is_proxy
        FROM statistic_best s
        JOIN geography g ON g.id = s.geography_id
        JOIN indicator i ON i.id = s.indicator_id
        JOIN domain d ON d.id = i.domain_id
        JOIN source src ON src.id = s.source_id
        ORDER BY d.name, i.name, g.iso3, s.year
        """).fetchdf()


def coverage_heatmap_figure(con: duckdb.DuckDBPyConnection) -> go.Figure:
    """Countries-with-data per indicator x year."""
    df = con.execute(
        """
        SELECT i.name AS indicator, s.year,
               count(DISTINCT s.geography_id) AS countries
        FROM statistic_best s JOIN indicator i ON i.id = s.indicator_id
        GROUP BY 1, 2
        """).fetchdf()
    pivot = df.pivot_table(index="indicator", columns="year", values="countries")
    fig = px.imshow(pivot, aspect="auto", color_continuous_scale="Blues",
                    labels=dict(color="countries"))
    fig.update_layout(height=520, margin=dict(l=0, r=0, t=10, b=0))
    return fig


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def events_table(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        "SELECT code, title, event_type, iso3, bloc_code, start_date, end_date, "
        "source, source_url, confidence, tags, affected_domains, description "
        "FROM event ORDER BY start_date").fetchdf()


def event_timeline_figure(events: pd.DataFrame) -> go.Figure:
    df = events.assign(scope=events["iso3"].fillna(events["bloc_code"]).fillna("Europe"))
    fig = px.scatter(df, x="start_date", y="event_type", color="event_type",
                     hover_name="title",
                     hover_data={"scope": True, "event_type": False,
                                 "start_date": True})
    fig.update_traces(marker=dict(size=11, line=dict(width=1, color="white")))
    fig.update_layout(height=420, showlegend=False,
                      margin=dict(l=0, r=0, t=10, b=0),
                      xaxis_title=None, yaxis_title=None)
    return fig


def event_study_figure(study: pd.DataFrame, unit: str, top_n: int = 20) -> go.Figure:
    """Before/after means per country for one event study result."""
    df = study.reindex(study["delta"].abs().sort_values(ascending=False).index)
    df = df.head(top_n)
    fig = go.Figure([
        go.Bar(name="before", x=df["iso3"], y=df["before_mean"]),
        go.Bar(name="after", x=df["iso3"], y=df["after_mean"]),
    ])
    fig.update_layout(barmode="group", height=420,
                      margin=dict(l=0, r=0, t=10, b=0),
                      yaxis_title=unit or "value")
    return fig


# ---------------------------------------------------------------------------
# Correlations
# ---------------------------------------------------------------------------

def observation_matrix(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """(iso3, year) x indicator wide matrix of values."""
    df = con.execute(
        """
        SELECT g.iso3, s.year, i.name AS indicator, s.value
        FROM statistic_best s
        JOIN geography g ON g.id = s.geography_id
        JOIN indicator i ON i.id = s.indicator_id
        """).fetchdf()
    return df.pivot_table(index=["iso3", "year"], columns="indicator",
                          values="value")


def correlation_matrix_figure(con: duckdb.DuckDBPyConnection,
                              min_pairs: int = 30) -> go.Figure:
    """Pairwise Pearson correlation across all (country, year) observations."""
    wide = observation_matrix(con)
    corr = wide.corr(min_periods=min_pairs)
    fig = px.imshow(corr, zmin=-1, zmax=1, color_continuous_scale="RdBu_r",
                    aspect="auto")
    fig.update_layout(height=620, margin=dict(l=0, r=0, t=10, b=0))
    return fig


# ---------------------------------------------------------------------------
# Time series
# ---------------------------------------------------------------------------

_TS_QUERY = """
SELECT s.year, s.value
FROM statistic_best s
JOIN geography g ON g.id = s.geography_id
JOIN indicator i ON i.id = s.indicator_id
WHERE g.iso3 = ? AND i.name = ?
ORDER BY s.year
"""


def indicator_timeseries(con: duckdb.DuckDBPyConnection, iso3: str,
                         indicator_name: str) -> pd.DataFrame:
    """Single country/indicator series as (year, value). Stable public API."""
    return con.execute(_TS_QUERY, [iso3, indicator_name]).fetchdf()


def multi_country_timeseries(con: duckdb.DuckDBPyConnection, iso3s: list[str],
                             indicator_name: str) -> pd.DataFrame:
    """Long-form (year, iso3, value) for several countries at once."""
    if not iso3s:
        return pd.DataFrame(columns=["year", "iso3", "value"])
    placeholders = ", ".join("?" for _ in iso3s)
    q = f"""
        SELECT s.year, g.iso3, s.value
        FROM statistic_best s
        JOIN geography g ON g.id = s.geography_id
        JOIN indicator i ON i.id = s.indicator_id
        WHERE i.name = ? AND g.iso3 IN ({placeholders})
        ORDER BY s.year
    """
    return con.execute(q, [indicator_name, *iso3s]).fetchdf()


def kpi(con: duckdb.DuckDBPyConnection, iso3: str,
        indicator_name: str) -> dict:
    """Latest value, its year, and YoY % change for one country/indicator."""
    df = indicator_timeseries(con, iso3, indicator_name)
    out = {"value": None, "year": None, "yoy": None,
           "unit": indicator_unit(con, indicator_name)}
    if df.empty:
        return out
    last = df.iloc[-1]
    out["value"], out["year"] = float(last["value"]), int(last["year"])
    if len(df) >= 2:
        prev = float(df.iloc[-2]["value"])
        if prev:
            out["yoy"] = (out["value"] - prev) / abs(prev) * 100.0
    return out


# ---------------------------------------------------------------------------
# Cross-country / bloc analytics
# ---------------------------------------------------------------------------

def latest_by_country(con: duckdb.DuckDBPyConnection,
                      indicator_name: str) -> pd.DataFrame:
    """Most recent available value per country for an indicator."""
    return con.execute(
        """
        SELECT g.iso3, g.name, s.year, s.value
        FROM statistic_best s
        JOIN geography g ON g.id = s.geography_id
        JOIN indicator i ON i.id = s.indicator_id
        WHERE i.name = ?
        QUALIFY row_number() OVER (
            PARTITION BY s.geography_id ORDER BY s.year DESC) = 1
        ORDER BY s.value DESC
        """,
        [indicator_name],
    ).fetchdf()


def bloc_rankings(con: duckdb.DuckDBPyConnection,
                  indicator_name: str) -> pd.DataFrame:
    """Average of each country's latest value, grouped by bloc."""
    return con.execute(
        """
        WITH latest AS (
            SELECT s.geography_id, s.value
            FROM statistic_best s
            JOIN indicator i ON i.id = s.indicator_id
            WHERE i.name = ?
            QUALIFY row_number() OVER (
                PARTITION BY s.geography_id ORDER BY s.year DESC) = 1
        )
        SELECT bl.name AS bloc, avg(l.value) AS mean_value, count(*) AS countries
        FROM latest l
        JOIN geography_bloc gb ON gb.geography_id = l.geography_id
        JOIN bloc bl ON bl.id = gb.bloc_id
        GROUP BY 1 ORDER BY 2 DESC
        """,
        [indicator_name],
    ).fetchdf()


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def choropleth_figure(con: duckdb.DuckDBPyConnection,
                      indicator_name: str) -> go.Figure:
    df = latest_by_country(con, indicator_name)
    unit = indicator_unit(con, indicator_name)
    fig = px.choropleth(
        df, locations="iso3", locationmode="ISO-3", color="value",
        scope="europe", hover_name="name",
        hover_data={"iso3": False, "value": ":,.1f", "year": True},
        color_continuous_scale="Viridis",
        labels={"value": unit or "value"},
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=520,
                      coloraxis_colorbar_title_text=unit or "value")
    return fig


_NODE_COLORS = {
    "country": "#4C78A8", "indicator": "#F58518", "source": "#E45756",
    "domain": "#54A24B", "bloc": "#B279A2",
}


def network_figure(con: duckdb.DuckDBPyConnection) -> tuple[go.Figure, pd.DataFrame]:
    """Structural graph as a plotly network + a top-centrality table."""
    g = to_networkx(con)
    cent = degree_centrality(g)
    comm = communities(g)
    comm_of = {n: i for i, c in enumerate(comm) for n in c}
    pos = nx.spring_layout(g, seed=42, k=0.6, iterations=60)

    edge_x, edge_y = [], []
    for u, v in g.edges():
        edge_x += [pos[u][0], pos[v][0], None]
        edge_y += [pos[u][1], pos[v][1], None]
    edge_trace = go.Scatter(
        x=edge_x, y=edge_y, mode="lines", hoverinfo="none",
        line=dict(width=0.4, color="rgba(150,150,150,0.4)"))

    traces = [edge_trace]
    for ntype, color in _NODE_COLORS.items():
        nodes = [n for n, d in g.nodes(data=True) if d["node_type"] == ntype]
        if not nodes:
            continue
        traces.append(go.Scatter(
            x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes],
            mode="markers", name=ntype, hoverinfo="text",
            text=[f"{g.nodes[n]['label']} ({ntype})<br>"
                  f"centrality {cent[n]:.3f} · community {comm_of.get(n, '-')}"
                  for n in nodes],
            marker=dict(
                size=[8 + 60 * cent[n] for n in nodes],
                color=color, line=dict(width=0.5, color="white")),
        ))
    fig = go.Figure(traces)
    fig.update_layout(
        showlegend=True, height=560, margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.0),
    )

    top = sorted(cent.items(), key=lambda kv: kv[1], reverse=True)[:12]
    labels = {n: (d["label"], d["node_type"]) for n, d in g.nodes(data=True)}
    cent_df = pd.DataFrame(
        [{"node": labels[n][0], "type": labels[n][1],
          "centrality": round(c, 3), "community": comm_of.get(n)}
         for n, c in top])
    return fig, cent_df
