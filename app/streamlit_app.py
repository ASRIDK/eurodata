from __future__ import annotations

import pathlib
import sys

# Make the app runnable via `streamlit run app/streamlit_app.py` from anywhere:
# Streamlit puts only the script's own dir on sys.path, so add the repo root
# (for the `app` package) and `src` (for the `eurodata` package) explicitly.
_ROOT = pathlib.Path(__file__).resolve().parent.parent
for _p in (str(_ROOT), str(_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import plotly.express as px
import streamlit as st

_STRETCH = "stretch"  # st.*(width=…) replacement for the retired use_container_width

from app import components as C
from eurodata.api import EuroData
from eurodata.db import connect

st.set_page_config(page_title="eurodata", layout="wide", page_icon="🇪🇺")

# ---------------------------------------------------------------------------
# Cached data access (shared read-only DuckDB connection so the app coexists
# with ingestion / other readers without fighting over the file lock)
# ---------------------------------------------------------------------------

@st.cache_resource
def get_con():
    return connect(read_only=True)


@st.cache_data(ttl=600)
def countries(_con):
    return C.list_countries(_con)


@st.cache_data(ttl=600)
def indicators(_con):
    return C.list_indicators(_con)


@st.cache_data(ttl=600)
def multi_series(_con, iso3s, indicator):
    return C.multi_country_timeseries(_con, iso3s, indicator)


@st.cache_data(ttl=600)
def latest(_con, indicator):
    return C.latest_by_country(_con, indicator)


@st.cache_data(ttl=600)
def blocs(_con, indicator):
    return C.bloc_rankings(_con, indicator)


@st.cache_data(ttl=600)
def choropleth(_con, indicator):
    return C.choropleth_figure(_con, indicator)


@st.cache_data(ttl=600)
def kpi(_con, iso3, indicator):
    return C.kpi(_con, iso3, indicator)


@st.cache_data(ttl=600)
def network(_con):
    return C.network_figure(_con)


con = get_con()
ED = EuroData.from_connection(con)
cdf = countries(con)
idf = indicators(con)
IND_NAMES = idf["name"].tolist()
ISO3S = cdf["iso3"].tolist()
NAMES = dict(zip(cdf["iso3"], cdf["name"]))
DEFAULT = "DEU" if "DEU" in ISO3S else ISO3S[0]


def _ind_index(name: str) -> int:
    return IND_NAMES.index(name) if name in IND_NAMES else 0


def _fmt(value, unit=""):
    if value is None:
        return "—"
    a = abs(value)
    if a >= 1e9:
        s = f"{value / 1e9:,.2f}B"
    elif a >= 1e6:
        s = f"{value / 1e6:,.2f}M"
    elif a >= 1000:
        s = f"{value:,.0f}"
    else:
        s = f"{value:,.2f}"
    return f"{s} {unit}".strip()


st.title("🇪🇺 eurodata — European Data Intelligence")
st.caption(
    f"{len(idf)} indicators · {len(ISO3S)} countries · "
    "sources: World Bank + Eurostat (CC BY 4.0) · importable: `import eurodata as ed`"
)

(tab_overview, tab_eco, tab_demo, tab_digi, tab_energy, tab_ai, tab_events,
 tab_corr, tab_catalog, tab_graph) = st.tabs(
    ["Overview", "Economy", "Demographics", "Digital", "Energy & Green",
     "AI & Tech", "Events", "Correlations", "Data Catalog", "Graph"])


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
with tab_overview:
    focus = st.selectbox("Focus country", ISO3S,
                         index=ISO3S.index(DEFAULT),
                         format_func=lambda c: f"{NAMES[c]} ({c})")

    headline = [n for n in ["GDP", "Population", "GDP per capita",
                            "Unemployment Rate", "Inflation (HICP)",
                            "Internet Users %"] if n in set(IND_NAMES)]
    cols = st.columns(len(headline))
    for col, headline_ind in zip(cols, headline):
        k = kpi(con, focus, headline_ind)
        delta = None if k["yoy"] is None else f"{k['yoy']:+.1f}% YoY"
        col.metric(headline_ind, _fmt(k["value"], k["unit"]), delta,
                   help=f"Latest year: {k['year']}")

    st.divider()
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Map")
        map_ind = st.selectbox("Indicator (map)", IND_NAMES,
                               index=_ind_index("GDP per capita"), key="map_ind")
        st.plotly_chart(choropleth(con, map_ind), width=_STRETCH)
    with right:
        st.subheader("Bloc rankings")
        bloc_ind = st.selectbox("Indicator (blocs)", IND_NAMES,
                                index=_ind_index("GDP per capita"), key="bloc_ind")
        bdf = blocs(con, bloc_ind)
        bloc_fig = px.bar(bdf, x="mean_value", y="bloc", orientation="h",
                  text="countries", labels={"mean_value": "avg (latest)"})
        bloc_fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0),
                       yaxis=dict(categoryorder="total ascending"))
        st.plotly_chart(bloc_fig, width=_STRETCH)
        st.dataframe(bdf, width=_STRETCH, hide_index=True)


# ---------------------------------------------------------------------------
# Domain tabs (compare countries on one indicator)
# ---------------------------------------------------------------------------
def render_domain(domain_name: str):
    inds = C.indicators_in_domain(con, domain_name)
    if not inds:
        st.info(f"No populated indicators in {domain_name} yet.")
        return
    c1, c2 = st.columns([2, 3])
    domain_indicator = c1.selectbox("Indicator", inds, key=f"ind_{domain_name}")
    meta = C.indicator_meta(con, domain_indicator)
    if meta["is_proxy"]:
        st.warning(f"⚠️ Proxy indicator — {meta['proxy_note']}")
    if meta["definition"]:
        st.caption(meta["definition"])
    picks = c2.multiselect(
        "Countries", ISO3S,
        default=[c for c in [DEFAULT, "FRA", "ITA", "ESP", "POL"]
                 if c in ISO3S][:5],
        format_func=lambda c: NAMES[c], key=f"cty_{domain_name}")

    ts = multi_series(con, picks, domain_indicator)
    if ts.empty:
        st.info("Pick at least one country with data.")
    else:
        ts = ts.assign(country=ts["iso3"].map(NAMES))
        series_fig = px.line(ts, x="year", y="value", color="country", markers=True,
                             labels={"value": C.indicator_unit(con, domain_indicator)})
        series_fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(series_fig, width=_STRETCH)

    st.subheader(f"Latest ranking — {domain_indicator}")
    ldf = latest(con, domain_indicator).assign(country=lambda d: d["iso3"].map(NAMES))
    st.dataframe(ldf[["country", "iso3", "year", "value"]],
                 width=_STRETCH, hide_index=True)


with tab_eco:
    render_domain("Economy")
with tab_demo:
    render_domain("Demographics")
with tab_digi:
    render_domain("Digital & Connectivity")
with tab_energy:
    render_domain("Energy & Green")
with tab_ai:
    render_domain("AI & Technology")


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600)
def events(_con):
    return C.events_table(_con)


with tab_events:
    edf = events(con)
    st.subheader("European events")
    st.caption("Curated, dated events with primary sources — memberships, "
               "crises, policy milestones. Use them for before/after analysis.")
    type_pick = st.multiselect("Event type", sorted(edf["event_type"].unique()),
                               key="ev_types")
    show = edf if not type_pick else edf[edf["event_type"].isin(type_pick)]
    st.plotly_chart(C.event_timeline_figure(show), width=_STRETCH)
    st.dataframe(
        show[["start_date", "title", "event_type", "iso3", "bloc_code",
              "confidence", "source", "source_url"]],
        width=_STRETCH, hide_index=True,
        column_config={"source_url": st.column_config.LinkColumn("source_url")})

    st.divider()
    st.subheader("Event study")
    ecol1, ecol2, ecol3 = st.columns([3, 3, 1])
    study_event = ecol1.selectbox(
        "Event", edf["code"],
        format_func=lambda c: edf.set_index("code").loc[c, "title"])
    study_ind = ecol2.selectbox("Indicator", IND_NAMES,
                                index=_ind_index("Inflation (HICP)"),
                                key="es_ind")
    window = ecol3.number_input("± years", 1, 10, 3)
    meta = C.indicator_meta(con, study_ind)
    if meta["is_proxy"]:
        st.warning(f"⚠️ Proxy indicator — {meta['proxy_note']}")
    study = ED.event_study(indicator=study_ind, event_code=study_event,
                           window_years=int(window))
    if study.empty:
        st.info("No indicator data overlapping this event window.")
    else:
        st.plotly_chart(
            C.event_study_figure(study, meta["unit"]), width=_STRETCH)
        st.dataframe(study, width=_STRETCH, hide_index=True)


# ---------------------------------------------------------------------------
# Correlations
# ---------------------------------------------------------------------------
with tab_corr:
    st.subheader("Correlation explorer")
    st.caption("Pearson correlation across countries' time series "
               "(statistic_best view). Correlation ≠ causation.")
    ccol1, ccol2, ccol3 = st.columns([3, 3, 1])
    ind_a = ccol1.selectbox("Indicator A", IND_NAMES,
                            index=_ind_index("GDP per capita"), key="corr_a")
    ind_b = ccol2.selectbox("Indicator B", IND_NAMES,
                            index=_ind_index("Internet Users %"), key="corr_b")
    lag = ccol3.number_input("Lag (years)", -10, 10, 0,
                             help="lag > 0: A leads B by n years")
    lc = ED.lagged_correlation(ind_a, ind_b, lag=int(lag))
    if lc.empty:
        st.info("Not enough overlapping data for this pair.")
    else:
        corr_fig = px.bar(lc, x="iso3", y="correlation")
        corr_fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0),
                               yaxis_range=[-1, 1])
        st.plotly_chart(corr_fig, width=_STRETCH)
        st.caption(f"median r = {lc['correlation'].median():.2f} across "
                   f"{len(lc)} countries")

    st.divider()
    st.subheader("Correlation matrix (all indicators)")
    st.plotly_chart(C.correlation_matrix_figure(con), width=_STRETCH)


# ---------------------------------------------------------------------------
# Data Catalog
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600)
def catalog(_con):
    return C.catalog_table(_con)


with tab_catalog:
    st.subheader("Indicator catalog")
    cat = catalog(con)
    st.dataframe(cat, width=_STRETCH, hide_index=True)
    proxies = cat[cat["is_proxy"] == True]  # noqa: E712
    if not proxies.empty:
        st.warning("⚠️ Proxy indicators: " + ", ".join(proxies["indicator"]))

    st.subheader("Sources & licenses")
    st.dataframe(C.sources_table(con), width=_STRETCH, hide_index=True,
                 column_config={"url": st.column_config.LinkColumn("url")})

    st.subheader("Coverage heatmap")
    st.plotly_chart(C.coverage_heatmap_figure(con), width=_STRETCH)

    st.subheader("Ingestion runs")
    st.dataframe(C.ingestion_runs(con), width=_STRETCH, hide_index=True)

    st.subheader("Download & query")
    st.download_button("Download full dataset (CSV)",
                       C.full_extract(con).to_csv(index=False),
                       file_name="eurodata_extract.csv", mime="text/csv")
    sql = st.text_area("SQL explorer (read-only)",
                       "SELECT * FROM statistic_best LIMIT 10")
    if st.button("Run query"):
        try:
            st.dataframe(con.execute(sql).fetchdf(), width=_STRETCH,
                         hide_index=True)
        except Exception as exc:  # noqa: BLE001 — surfaced to the user
            st.error(f"Query failed: {exc}")


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------
with tab_graph:
    st.subheader("Structural graph")
    st.caption("Countries, indicators, sources, domains and blocs as nodes; "
               "borders, memberships and provenance as edges. Node size ∝ degree "
               "centrality; colour ∝ node type.")
    fig, cent_df = network(con)
    gcol, tcol = st.columns([3, 1])
    gcol.plotly_chart(fig, width=_STRETCH)
    tcol.markdown("**Top centrality**")
    tcol.dataframe(cent_df, width=_STRETCH, hide_index=True)
