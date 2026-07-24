"""Tests for EuroData.convergence() — beta- and sigma-convergence.

The fixture builds a *fully determined* panel so every reported statistic has
a known closed-form value:

For each country the annual log-growth of GDP per capita is an exact linear
function of its (log) initial level,

    g_i = 0.10 - 0.02 * ln(y_i0),

with values laid out on an exponential path y_i(t) = y_i0 * exp(g_i * t).
That construction gives, by design:

- a perfect beta-convergence regression: annualized growth (in %/yr) =
  10 - 2 * ln(y0), so the slope is exactly -2.0 %/yr per log-unit and R^2 = 1;
- an implied convergence speed lambda solving -(1 - e^{-lambda T})/T = -0.02
  with T = 10, i.e. lambda = -ln(0.8)/10 = 0.0223144, half-life ln2/lambda;
- sigma-convergence: the cross-country SD of ln(y) shrinks linearly from
  SD0 at t=0 to 0.8*SD0 at t=10, so the dispersion trend slope is negative.
"""
import datetime as dt
import math

import duckdb
import numpy as np
import pandas as pd
import pytest

from eurodata.api import EuroData, EuroDataLookupError
from eurodata.db import init_schema
from eurodata.ingest.pipeline import load_records
from eurodata.model.seed import seed_all
from eurodata.sources.base import Record

# country iso3 -> initial GDP-per-capita level (log-spaced, rich -> poor)
_INITIAL = {"DEU": 80.0, "FRA": 40.0, "ITA": 20.0, "ESP": 10.0}
_START, _END = 2000, 2010
_T = _END - _START


def _growth(y0: float) -> float:
    """Annual log-growth rate as a decimal, by construction."""
    return 0.10 - 0.02 * math.log(y0)


@pytest.fixture
def db() -> EuroData:
    con = duckdb.connect(":memory:")
    init_schema(con)
    seed_all(con)
    recs = []
    for iso3, y0 in _INITIAL.items():
        g = _growth(y0)
        for year in range(_START, _END + 1):
            value = y0 * math.exp(g * (year - _START))
            recs.append(Record(iso3, "sdg_08_10", year, value))  # GDP per capita
    load_records(con, "World Bank", recs, vintage=dt.date(2026, 1, 1))
    handle = EuroData.from_connection(con)
    yield handle
    con.close()


def test_beta_scatter_shape(db):
    out = db.convergence("GDP per capita")
    assert set(out["iso3"]) == set(_INITIAL)
    assert list(out.columns) == [
        "iso3", "country", "initial_year", "initial_value", "final_year",
        "final_value", "annualized_growth", "log_initial",
    ]
    # sorted by starting level (poorest first) for a readable scatter
    assert list(out["iso3"]) == ["ESP", "ITA", "FRA", "DEU"]
    row = out.set_index("iso3").loc["ESP"]
    assert row["initial_year"] == _START and row["final_year"] == _END
    assert row["initial_value"] == pytest.approx(10.0)
    # annualized growth is reported in %/yr and equals 100 * g_i
    assert row["annualized_growth"] == pytest.approx(100 * _growth(10.0))
    assert row["log_initial"] == pytest.approx(math.log(10.0))


def test_beta_regression_stats(db):
    out = db.convergence("GDP per capita")
    beta = out.attrs["beta"]
    # growth% = 10 - 2*ln(y0): slope exactly -2.0 %/yr per log-unit, R^2 = 1
    assert beta["coefficient"] == pytest.approx(-2.0, abs=1e-9)
    assert beta["intercept"] == pytest.approx(10.0, abs=1e-9)
    assert beta["r_squared"] == pytest.approx(1.0, abs=1e-9)
    assert beta["n"] == 4
    assert beta["converging"] is True
    assert beta["p_value"] is not None and beta["p_value"] < 0.01
    # speed lambda = -ln(0.8)/10 ; half-life = ln2 / lambda
    lam = -math.log(0.8) / _T
    assert beta["speed"] == pytest.approx(lam, rel=1e-6)
    assert beta["half_life"] == pytest.approx(math.log(2) / lam, rel=1e-6)


def test_sigma_series_and_trend(db):
    out = db.convergence("GDP per capita")
    sigma = out.attrs["sigma"]
    assert list(sigma["year"]) == list(range(_START, _END + 1))
    assert (sigma["n"] == 4).all()

    # SD of ln(y) at t: (1 - 0.02 t) * SD0  (sample SD, ddof=1)
    logs0 = np.array([math.log(v) for v in _INITIAL.values()])
    sd0 = logs0.std(ddof=1)
    first = sigma.iloc[0]["sd_log"]
    last = sigma.iloc[-1]["sd_log"]
    assert first == pytest.approx(sd0, rel=1e-9)
    assert last == pytest.approx(0.8 * sd0, rel=1e-9)

    trend = out.attrs["sigma_trend"]
    assert trend["converging"] is True
    assert trend["slope"] == pytest.approx(-0.02 * sd0, rel=1e-6)
    assert trend["p_value"] is not None and trend["p_value"] < 0.01
    assert trend["start_dispersion"] == pytest.approx(sd0, rel=1e-9)
    assert trend["end_dispersion"] == pytest.approx(0.8 * sd0, rel=1e-9)


def test_bloc_and_range_filters(db):
    # restrict window: initial/final years follow start/end
    out = db.convergence("GDP per capita", start=2002, end=2008)
    assert set(out["initial_year"]) == {2002}
    assert set(out["final_year"]) == {2008}
    # a bloc filter is accepted and narrows the unit set
    eu = db.convergence("GDP per capita", bloc="EU")
    assert set(eu["iso3"]).issubset(set(_INITIAL))


def test_unknown_indicator_raises(db):
    with pytest.raises(EuroDataLookupError):
        db.convergence("Not An Indicator")


def test_module_level_export():
    import eurodata as ed
    from eurodata import api
    assert hasattr(ed, "convergence")
    assert "convergence" in api.__all__
