import datetime as dt

import duckdb
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


def test_coverage_includes_empty(db):
    cov = db.coverage()
    assert len(cov) == 37
    medage = cov[cov["indicator"] == "Median Age"].iloc[0]
    assert medage["rows"] == 0


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
    r0 = db.correlate("GDP", "GDP")
    assert ((r0["correlation"] - 1.0).abs() < 1e-9).all()
    lagged = db.lagged_correlation("R&D Expenditure (% GDP)", "GDP per capita",
                                   lag=2)
    ita = lagged[lagged["iso3"] == "ITA"].iloc[0]
    assert ita["correlation"] == pytest.approx(1.0)
    # at lag 0 the series are shifted copies -> correlation clearly below 1
    # (min_years=5: only 9 overlapping years remain at lag 0)
    lag0 = db.lagged_correlation("R&D Expenditure (% GDP)", "GDP per capita",
                                 lag=0, min_years=5)
    assert lag0[lag0["iso3"] == "ITA"]["correlation"].iloc[0] < 0.9


def test_correlation_stats(db):
    r0 = db.correlate("GDP", "GDP")
    row = r0.iloc[0]
    # a perfect correlation over 11 years: p ~ 0, CI hugging 1
    assert row["p_value"] < 1e-6
    assert row["ci_low"] > 0.99 and row["ci_high"] >= row["ci_low"]
    # default min_years=10 drops the 9-year overlap at lag 0
    lag0 = db.lagged_correlation("R&D Expenditure (% GDP)", "GDP per capita")
    assert "ITA" not in set(lag0["iso3"])


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
