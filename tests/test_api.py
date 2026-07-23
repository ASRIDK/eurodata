import datetime as dt

import duckdb
import pandas as pd
import pytest

import eurodata as ed
from eurodata.api import EuroData, EuroDataLookupError
from eurodata.db import init_schema
from eurodata.ingest.pipeline import load_records
from eurodata.model.seed import seed_all
from eurodata.sources.base import Record


@pytest.fixture
def db() -> EuroData:
    con = duckdb.connect(":memory:")
    init_schema(con)
    seed_all(con)
    recs = []
    # GDP rising 2010-2020 for DEU/FRA (api_code nama_10_gdp)
    for i, year in enumerate(range(2010, 2021)):
        recs.append(Record("DEU", "nama_10_gdp", year, 100.0 + 10 * i))
        recs.append(Record("FRA", "nama_10_gdp", year, 90.0 + 8 * i))
    # Unemployment: flat 1.0 before 2020, 2.0 from 2020 (event-study target)
    for year in range(2017, 2024):
        recs.append(Record("DEU", "une_rt_a", year, 1.0 if year < 2020 else 2.0))
    # Non-monotonic series a and its exact 2-year lag b
    a_vals = {2010 + i: v for i, v in enumerate([1, 4, 2, 8, 5, 7, 3, 6, 9, 2, 5])}
    for year, v in a_vals.items():
        recs.append(Record("ITA", "GB.XPD.RSDV.GD.ZS", year, float(v)))
        if year + 2 <= 2022:
            recs.append(Record("ITA", "sdg_08_10", year + 2, float(v)))
    # Monthly HICP: 1.0 through 2019, 2.0 through 2020 (month-precision target)
    for year, val in ((2019, 1.0), (2020, 2.0)):
        for m in range(1, 13):
            recs.append(Record("DEU", "prc_hicp_manr", year, val, month=m))
    load_records(con, "World Bank", recs, vintage=dt.date(2026, 1, 1))
    handle = EuroData.from_connection(con)
    yield handle
    con.close()


def test_countries_and_blocs(db):
    c = db.countries()
    assert len(c) == 50 and "FRA" in set(c["iso3"])
    b = db.blocs()
    assert b.set_index("code").loc["EUROZONE", "current_members"] == 21
    members = db.bloc_members("eurozone")
    assert "HRV" in set(members["iso3"])
    with pytest.raises(EuroDataLookupError):
        db.bloc_members("EUROPZONE")


def test_regions_catalog(db):
    r = db.regions()
    assert len(r) == 293 and "FR10" in set(r["code"])
    fr = db.regions(country="FRA")
    assert set(fr["country_iso3"]) == {"FRA"} and "Ile de France" in set(fr["name"])
    # countries() must not leak NUTS rows
    assert len(db.countries()) == 50


def test_series_resolves_nuts_region(db):
    # a NUTS 2 record flows through series() keyed by its region code
    load_records(db.con, "Eurostat",
                 [Record("FR10", "nama_10r_2gdp", 2020, 55000.0)],
                 vintage=dt.date(2026, 1, 1))
    df = db.series(country="FR10", indicator="GDP per capita (NUTS 2 region)")
    assert list(df["iso3"]) == ["FR10"]
    assert list(df["country"]) == ["Ile de France"]
    assert list(df["value"]) == [55000.0]


def test_indicators_and_search(db):
    econ = db.indicators(domain="Economy")
    assert "GDP" in set(econ["name"]) and set(econ["domain"]) == {"Economy"}
    hits = db.search_indicators("artificial intelligence")
    assert "AI Adoption by Enterprises %" in set(hits["name"])


def test_series_filters(db):
    s = db.series(country="DEU", indicator="GDP")
    assert len(s) == 11 and s["value"].iloc[0] == 100.0
    s = db.series(country="deu", indicator="nama_10_gdp", start=2015, end=2017)
    assert list(s["year"]) == [2015, 2016, 2017]
    s = db.series(indicator="GDP", bloc="EU")
    assert set(s["iso3"]) == {"DEU", "FRA"}  # ITA has no GDP rows in fixture
    assert {"is_proxy", "source", "unit"} <= set(s.columns)


def test_series_lookup_errors(db):
    with pytest.raises(EuroDataLookupError, match="FRA"):
        db.series(country="FRX", indicator="GDP")
    with pytest.raises(EuroDataLookupError, match="GDP"):
        db.series(country="FRA", indicator="GPD")


def test_latest_and_compare(db):
    latest = db.latest("GDP")
    assert set(latest["iso3"]) == {"DEU", "FRA"}
    assert (latest["year"] == 2020).all()
    wide = db.compare(["DEU", "FRA"], "GDP", start=2018)
    assert list(wide.columns) == ["DEU", "FRA"] and len(wide) == 3


def test_provenance_multi_source(db):
    # DEU GDP 2015 already has a World Bank row (100.0 + 10*5 = 150.0);
    # add a disagreeing Eurostat row for the same period.
    load_records(db.con, "Eurostat",
                 [Record("DEU", "nama_10_gdp", 2015, 999.0)],
                 vintage=dt.date(2026, 1, 1))
    prov = db.provenance("GDP", "DEU")
    row_2015 = prov[prov["period"] == "2015"]
    assert set(row_2015["source"]) == {"World Bank", "Eurostat"}
    # Eurostat (0.95) outranks World Bank (0.90)
    best = row_2015[row_2015["is_best"]]
    assert len(best) == 1 and best.iloc[0]["source"] == "Eurostat"
    assert best.iloc[0]["value"] == 999.0
    # a period with only one source has exactly one (best) row
    row_2010 = prov[prov["period"] == "2010"]
    assert len(row_2010) == 1 and bool(row_2010.iloc[0]["is_best"])


def test_provenance_dedupes_repeat_ingestion(db):
    # Re-ingesting the same source/value on the same vintage date must not
    # create phantom "disagreement" rows.
    load_records(db.con, "World Bank",
                 [Record("DEU", "nama_10_gdp", 2011, 110.0)],
                 vintage=dt.date(2026, 1, 1))
    prov = db.provenance("GDP", "DEU")
    row_2011 = prov[prov["period"] == "2011"]
    assert len(row_2011) == 1


def test_country_blocs(db):
    cb = db.country_blocs("FRA")
    assert {"EU", "EUROZONE", "SCHENGEN", "NATO"} <= set(cb["bloc_code"])
    assert (cb["until_year"].isna()).all()  # all current memberships


def test_country_indicators(db):
    ci = db.country_indicators("DEU")
    names = set(ci["indicator"])
    assert "GDP" in names and "Unemployment Rate" in names
    assert "GDP" not in set(db.country_indicators("ITA")["indicator"])


def test_coverage_includes_empty(db):
    cov = db.coverage()
    assert len(cov) == 48
    medage = cov[cov["indicator"] == "Median Age"].iloc[0]
    assert medage["rows"] == 0


def test_coverage_years_stale(db):
    this_year = dt.date.today().year
    cov = db.coverage()
    assert "years_stale" in cov.columns
    gdp = cov[cov["indicator"] == "GDP"].iloc[0]        # data runs to 2020
    assert gdp["last_year"] == 2020
    assert gdp["years_stale"] == this_year - 2020
    # Empty indicators have no last year, hence no staleness.
    medage = cov[cov["indicator"] == "Median Age"].iloc[0]
    assert pd.isna(medage["years_stale"])


def test_events_filters(db):
    ukr = db.events(country="UKR", since="2020-01-01")
    codes = set(ukr["code"])
    assert "ukr-invasion-2022" in codes
    assert "ai-act-2024" not in codes  # EU-bloc event; UKR is not an EU member
    assert "covid-pandemic-2020" in codes  # global event applies everywhere
    deu = db.events(country="DEU", event_type="ai_regulation")
    assert set(deu["code"]) == {"ai-act-2024"}
    tagged = db.events(tag="brexit")
    assert len(tagged) == 2
    assert not db.events(until="1990-01-01").shape[0]


def test_event_study_before_after(db):
    study = db.event_study(indicator="Unemployment Rate",
                           event_code="covid-pandemic-2020", window_years=3)
    row = study[study["iso3"] == "DEU"].iloc[0]
    assert row["before_mean"] == 1.0 and row["after_mean"] == 2.0
    assert row["delta"] == 1.0 and row["pct_change"] == 100.0
    with pytest.raises(EuroDataLookupError):
        db.event_study(indicator="GDP", event_code="not-an-event")


def test_correlate_and_lag(db):
    # These use raw levels: the fixture builds GDP per capita as a 2-year-shifted
    # copy of R&D, a level-space relationship.
    r0 = db.correlate("GDP", "GDP", on="levels")
    assert ((r0["correlation"] - 1.0).abs() < 1e-9).all()
    lagged = db.lagged_correlation("R&D Expenditure (% GDP)", "GDP per capita",
                                   lag=2, on="levels")
    ita = lagged[lagged["iso3"] == "ITA"].iloc[0]
    assert ita["correlation"] == pytest.approx(1.0)
    # at lag 0 the series are shifted copies -> correlation clearly below 1
    # (min_years=5: only 9 overlapping years remain at lag 0)
    lag0 = db.lagged_correlation("R&D Expenditure (% GDP)", "GDP per capita",
                                 lag=0, min_years=5, on="levels")
    assert lag0[lag0["iso3"] == "ITA"]["correlation"].iloc[0] < 0.9


def test_correlate_defaults_to_growth(db):
    # Default basis is YoY growth; the transform drops one year per country.
    default = db.correlate("GDP", "GDP")
    levels = db.correlate("GDP", "GDP", on="levels")
    assert default.attrs["basis"] == "growth"
    assert levels.attrs["basis"] == "levels"
    # GDP vs itself is perfectly correlated either way, but growth loses a year.
    assert ((default["correlation"] - 1.0).abs() < 1e-9).all()
    assert int(default["n_years"].iloc[0]) == int(levels["n_years"].iloc[0]) - 1


def test_correlation_stats(db):
    r0 = db.correlate("GDP", "GDP", on="levels")
    row = r0.iloc[0]
    # a perfect correlation over 11 years: p ~ 0, CI hugging 1
    assert row["p_value"] < 1e-6
    assert row["ci_low"] > 0.99 and row["ci_high"] >= row["ci_low"]
    # default (growth, min_years=10) drops the short overlap at lag 0
    lag0 = db.lagged_correlation("R&D Expenditure (% GDP)", "GDP per capita")
    assert "ITA" not in set(lag0["iso3"])


def test_revisions_trail_and_summary(db):
    con = db.con
    # FRA GDP was loaded at vintage 2026-01-01; re-report 2015 at a later
    # vintage with a different value -> exactly one revised period.
    load_records(con, "World Bank", [Record("FRA", "nama_10_gdp", 2015, 999.0)],
                 vintage=dt.date(2027, 1, 1))
    rev = db.revisions("GDP", "FRA")
    assert rev.attrs["n_revised"] == 1
    row_2015 = rev[(rev["period"] == "2015") & (rev["is_latest"])].iloc[0]
    assert row_2015["value"] == 999.0
    assert not pd.isna(row_2015["previous_value"]) and row_2015["delta"] != 0
    assert set(rev.attrs["summary"]["period"]) == {"2015"}

    all_rev = db.revisions_summary()
    assert (all_rev["indicator"] == "GDP").any()
    fra = db.revisions_summary(country="FRA")
    assert set(fra["period"]) >= {"2015"}
    # an un-revised series has an empty trail
    assert db.revisions("GDP", "DEU").attrs["n_revised"] == 0


def test_country_correlations_are_local(db):
    con = db.con
    # Inject one CORRELATES_WITH edge for a pair ITA has both series for, so the
    # walk has a pair to score; the per-country r is computed locally.
    a, b = "R&D Expenditure (% GDP)", "GDP per capita"
    ids = dict(con.execute(
        "SELECT name, id FROM indicator WHERE name IN (?, ?)", [a, b]).fetchall())
    con.execute("INSERT INTO graph_node (id, node_type, ref_id, label) VALUES "
                "(901,'indicator',?,?), (902,'indicator',?,?)",
                [ids[a], a, ids[b], b])
    import json
    props = json.dumps({"relationship": "contemporaneous", "direction": "undetermined",
                        "q_value": 0.01, "n_countries": 5})
    con.execute("INSERT INTO graph_edge (src_node_id, dst_node_id, edge_type, weight, props) "
                "VALUES (901, 902, 'CORRELATES_WITH', 0.9, ?)", [props])
    cc = db.country_correlations("ITA", min_years=3)
    assert list(cc.columns)[:5] == ["indicator_a", "indicator_b", "domain_a",
                                    "domain_b", "correlation"]
    assert len(cc) == 1
    assert cc.iloc[0]["relationship"] == "contemporaneous"
    assert -1.0 <= cc.iloc[0]["correlation"] <= 1.0
    # unknown country still raises the usual lookup error
    with pytest.raises(EuroDataLookupError):
        db.country_correlations("Atlantis")


def test_sub_annual_series_periods(db):
    s = db.series(country="DEU", indicator="Inflation (HICP, monthly)")
    assert len(s) == 24
    first = s.iloc[0]
    assert first["period"] == "2019-01" and first["month"] == 1
    assert first["t"] == pytest.approx(2019.0)
    assert list(s["t"]) == sorted(s["t"])


def test_event_study_month_precision(db):
    # covid-pandemic-2020 starts 2020-03-11: with monthly data, Jan/Feb 2020
    # belong to the BEFORE window and March 2020 to the AFTER window.
    study = db.event_study(indicator="Inflation (HICP, monthly)",
                           event_code="covid-pandemic-2020", window_years=1)
    row = study[study["iso3"] == "DEU"].iloc[0]
    assert row["n_before"] == 12   # 2019-03 .. 2020-02
    assert row["n_after"] == 10    # 2020-03 .. 2020-12
    assert row["after_mean"] == 2.0
    assert row["before_mean"] == pytest.approx((10 * 1.0 + 2 * 2.0) / 12)


def test_series_rebase(db):
    s = db.series(indicator="GDP", rebase=2010)
    deu_2020 = s[(s["iso3"] == "DEU") & (s["year"] == 2020)]["value"].iloc[0]
    assert deu_2020 == pytest.approx(200.0)  # 200 vs base 100
    assert set(s["unit"]) == {"index (2010=100)"}


def test_series_yoy(db):
    s = db.series(country="DEU", indicator="GDP", yoy=True)
    assert len(s) == 10  # first year has no prior-year base
    assert s[s["year"] == 2011]["value"].iloc[0] == pytest.approx(10.0)
    assert set(s["unit"]) == {"% y/y"}


def test_rebase_yoy_mutually_exclusive(db):
    with pytest.raises(ValueError):
        db.series(indicator="GDP", rebase=2010, yoy=True)


def test_query_and_relation(db):
    df = db.query("SELECT COUNT(*) AS n FROM statistic_record")
    assert df["n"].iloc[0] > 0
    rel = db.relation("SELECT 1 AS one")
    assert rel.fetchall() == [(1,)]


def test_module_level_delegation_docs():
    # Module-level wrappers exist and carry the method docstrings.
    assert ed.series.__doc__ and "Time series" in ed.series.__doc__
    assert ed.event_study.__name__ == "event_study"


def test_forecast_extends_annual_series(ed):
    df = ed.forecast("GDP per capita", "FRA", horizon=3)
    hist = df[df["kind"] == "history"]
    fc = df[df["kind"] == "forecast"]
    assert len(fc) == 3
    assert len(hist) > 0
    # forecast t values continue past the last history t
    assert fc["t"].min() > hist["t"].max()
    # band present on forecast rows, absent on history
    assert fc["lo"].notna().all() and fc["hi"].notna().all()
    assert hist["lo"].isna().all()
    # metadata
    assert df.attrs["method"] in (
        "drift", "linear", "log_linear", "holt", "seasonal_naive", "holt_winters")
    assert "not a prediction" in df.attrs["disclaimer"].lower()
    assert df.attrs["country"] == "FRA"


def test_forecast_extends_monthly_series(ed):
    df = ed.forecast("Inflation (HICP, monthly)", "FRA", horizon=3)
    hist = df[df["kind"] == "history"]
    fc = df[df["kind"] == "forecast"]
    assert len(fc) == 3
    assert df.attrs["freq"] == 12
    # period labels look like YYYY-MM with a valid month, and continue
    # chronologically past the last history period (covers year rollover)
    assert fc["period"].str.match(r"^\d{4}-\d{2}$").all()
    months = fc["period"].str.slice(5, 7).astype(int)
    assert months.between(1, 12).all()
    assert fc["t"].min() > hist["t"].max()
    assert fc["period"].min() > hist["period"].max()


def test_module_level_forecast_delegate():
    import eurodata as ed_pkg
    from pathlib import Path
    if not Path("data/eurodata.duckdb").exists():
        import pytest; pytest.skip("requires the built database")
    df = ed_pkg.forecast("GDP per capita", "FRA", horizon=2)
    assert callable(ed_pkg.forecast)
    assert (df["kind"] == "forecast").sum() == 2


# --- catalog surfaces ------------------------------------------------------

def test_domains_and_sources_catalogs(db):
    domains = db.domains()
    assert {"Economy", "Demographics"} <= set(domains["name"])
    assert domains["description"].notna().all()

    sources = db.sources()
    # sources() promises reliability order, which is what statistic_best relies
    # on to pick a winner — assert the ordering, not just the membership.
    assert list(sources["reliability_score"]) == sorted(
        sources["reliability_score"], reverse=True)
    assert sources.iloc[0]["reliability_score"] == 0.95
    assert set(sources["name"]) >= {"Eurostat", "World Bank", "OECD", "ECB"}


def test_years_spans_every_frequency(db):
    # 2010 is the earliest annual GDP row; 2023 the latest unemployment row.
    # years() reads statistic_record, so sub-annual rows count too.
    assert db.years() == (2010, 2023)
    assert all(isinstance(y, int) for y in db.years())


def test_event_types_are_grouped_and_ordered(db):
    types = db.event_types()
    assert types["events"].sum() == 43          # every seeded event is counted
    assert len(types) == 12                     # one row per distinct type
    assert list(types["events"]) == sorted(types["events"], reverse=True)


def test_ingestion_summary_attributes_errors_to_their_run(db):
    # The fixture's load_records() already recorded one completed run.
    summary = db.ingestion_summary()
    assert list(summary["source"]) == ["World Bank"]
    assert summary.iloc[0]["records_processed"] > 0
    assert summary.iloc[0]["series_errors"] == 0

    # An error inside the run's window is attributed to it; one outside is not.
    run = db.query("SELECT source, started_at, ended_at FROM ingestion_run").iloc[0]
    mid = run["started_at"] + (run["ended_at"] - run["started_at"]) / 2
    db.con.execute(
        "INSERT INTO ingestion_error (source, series, error, occurred_at) "
        "VALUES (?, ?, ?, ?)", ["World Bank", "NY.GDP.MKTP.CD", "boom", mid])
    db.con.execute(
        "INSERT INTO ingestion_error (source, series, error, occurred_at) "
        "VALUES (?, ?, ?, ?)",
        ["World Bank", "SP.POP.TOTL", "later", run["ended_at"] + dt.timedelta(days=1)])
    assert db.ingestion_summary().iloc[0]["series_errors"] == 1


# --- indicator_trends ------------------------------------------------------

def test_indicator_trends_rebases_both_series_to_100(db):
    # GDP (DEU/FRA) and R&D (ITA) both span 2010-2020, so 2010 is the shared
    # base year and each indicator must start at exactly 100 despite carrying
    # completely different units.
    out = db.indicator_trends(["GDP", "R&D Expenditure (% GDP)"])
    assert set(out["indicator"]) == {"GDP", "R&D Expenditure (% GDP)"}
    assert (out["base_year"] == 2010).all()
    base = out[out["year"] == 2010]
    assert len(base) == 2
    assert base["value"].round(6).eq(100.0).all()
    # GDP rises monotonically in the fixture, so its index must too.
    gdp = out[out["indicator"] == "GDP"].sort_values("year")["value"]
    assert gdp.is_monotonic_increasing


def test_indicator_trends_without_rebase_keeps_raw_medians(db):
    raw = db.indicator_trends(["GDP"], rebase=False)
    first = raw[raw["year"] == 2010].iloc[0]
    # cross-country median of DEU 100.0 and FRA 90.0
    assert first["value"] == pytest.approx(95.0)
    assert first["n_countries"] == 2


def test_indicator_trends_empty_when_an_indicator_has_no_data(db):
    # Median Age is seeded in the catalog but carries no rows in the fixture,
    # so the whole result is empty rather than a half-populated chart.
    out = db.indicator_trends(["GDP", "Median Age"])
    assert out.empty
    assert list(out.columns) == [
        "indicator", "year", "value", "n_countries", "base_year"]


def test_indicator_trends_respects_the_year_window(db):
    out = db.indicator_trends(["GDP", "R&D Expenditure (% GDP)"], start=2015, end=2018)
    assert out["year"].min() == 2015 and out["year"].max() == 2018
    assert (out["base_year"] == 2015).all()


# --- correlation_graph -----------------------------------------------------

def test_correlation_graph_is_empty_until_the_graph_is_built(db):
    # scripts/build_graph.py has not run against this fixture; the accessor must
    # return an empty frame with its documented columns rather than raising.
    edges = db.correlation_graph()
    assert edges.empty
    for col in ("indicator_a", "indicator_b", "weight"):
        assert col in edges.columns


# --- propagation ------------------------------------------------------------

def _seed_edges(db, rows):
    """Insert CORRELATES_WITH edges directly, so propagation can be tested
    without running the full graph builder.

    graph_node.id is an INTEGER PRIMARY KEY with no sequence default, so ids
    must be assigned explicitly — the same thing scripts/build_graph.py does
    with its counter. correlation_graph() parses props as JSON and reads
    relationship/direction/q_value/n_countries, so all four must be present.
    """
    def node_id(name):
        ind_id = db.con.execute(
            "SELECT id FROM indicator WHERE name = ?", [name]).fetchone()[0]
        existing = db.con.execute(
            "SELECT id FROM graph_node WHERE node_type='indicator' AND ref_id = ?",
            [ind_id]).fetchone()
        if existing:
            return existing[0]
        nid = db.con.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 FROM graph_node").fetchone()[0]
        db.con.execute(
            "INSERT INTO graph_node (id, node_type, ref_id, label) "
            "VALUES (?, 'indicator', ?, ?)", [nid, ind_id, name])
        return nid

    for a, b, weight, direction in rows:
        props = ('{"direction": "%s", "q_value": 0.01, '
                 '"relationship": "contemporaneous", "n_countries": 5}' % direction)
        db.con.execute(
            "INSERT INTO graph_edge (src_node_id, dst_node_id, edge_type, weight, props) "
            "VALUES (?, ?, 'CORRELATES_WITH', ?, ?)",
            [node_id(a), node_id(b), weight, props])


def test_propagate_ripples_across_indicators(db):
    _seed_edges(db, [
        ("Unemployment Rate", "Government Debt (% GDP)", 0.6, "undetermined"),
        ("Government Debt (% GDP)", "R&D Expenditure (% GDP)", -0.6, "undetermined"),
    ])
    out = db.propagate("Unemployment Rate", edge_floor=0.3, threshold=0.05)
    rows = {r["node"]: r for _, r in out.iterrows()}
    assert set(rows) == {"Government Debt (% GDP)", "R&D Expenditure (% GDP)"}
    assert rows["Government Debt (% GDP)"]["hop"] == 1
    assert rows["Government Debt (% GDP)"]["activation"] > 0
    # positive shock -> debt up -> R&D down, two hops out
    assert rows["R&D Expenditure (% GDP)"]["hop"] == 2
    assert rows["R&D Expenditure (% GDP)"]["activation"] < 0
    assert rows["R&D Expenditure (% GDP)"]["via"] == "Government Debt (% GDP)"
    assert list(out.columns) == ["node", "hop", "activation", "via", "path", "directed"]


def test_propagate_rejects_an_unknown_node(db):
    with pytest.raises(EuroDataLookupError):
        db.propagate("Unemploymnet Rate")


def test_propagate_returns_empty_frame_when_the_graph_is_unbuilt(db):
    out = db.propagate("GDP")
    assert out.empty
    assert list(out.columns) == ["node", "hop", "activation", "via", "path", "directed"]


def test_propagate_accepts_an_indicator_api_code(db):
    _seed_edges(db, [("Unemployment Rate", "Government Debt (% GDP)", 0.6,
                      "undetermined")])
    # une_rt_a is Unemployment Rate's api_code; _resolve_indicator accepts either
    out = db.propagate("une_rt_a", edge_floor=0.3)
    assert "Government Debt (% GDP)" in set(out["node"])


def test_propagate_walks_this_countrys_own_correlations(db):
    # The country branch reads country_correlations, which names its weight
    # column `correlation` and carries no `direction` column at all -- every
    # per-country edge is therefore symmetric, so nothing can come back
    # directed. ITA has 9 overlapping years of these two series in the fixture,
    # which clears country_correlations' 8-year minimum; with fewer, that call
    # returns nothing and this test would pass while asserting nothing.
    _seed_edges(db, [("R&D Expenditure (% GDP)", "GDP per capita", 0.9,
                      "undetermined")])
    out = db.propagate("R&D Expenditure (% GDP)", country="ITA", edge_floor=0.3)
    assert list(out["node"]) == ["GDP per capita"]
    assert out.iloc[0]["hop"] == 1
    assert out.iloc[0]["activation"] > 0
    assert bool(out.iloc[0]["directed"]) is False
    assert list(out.columns) == ["node", "hop", "activation", "via", "path", "directed"]
