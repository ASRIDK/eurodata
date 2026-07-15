import numpy as np
import pytest

from eurodata.forecast import ForecastResult, forecast_values


def test_linear_series_picks_linear_and_extrapolates():
    y = np.arange(1, 21, dtype=float) * 2.0 + 5.0  # perfectly linear, 20 pts
    res = forecast_values(y, horizon=3, freq=1, level=0.8)
    assert isinstance(res, ForecastResult)
    assert res.method == "linear"
    assert res.n_obs == 20
    assert res.fallback is False
    assert len(res.points) == 3
    # next three values continue 2x+5: x=21,22,23 -> 47,49,51
    yhats = [p.yhat for p in res.points]
    assert yhats == pytest.approx([47.0, 49.0, 51.0], abs=1e-6)
    # band brackets the point estimate and widens with horizon
    assert res.points[0].lo <= res.points[0].yhat <= res.points[0].hi
    assert (res.points[2].hi - res.points[2].lo) >= (res.points[0].hi - res.points[0].lo)


def test_short_series_falls_back_to_drift():
    y = np.array([10.0, 11.0, 9.0, 12.0], dtype=float)  # n=4 < 6
    res = forecast_values(y, horizon=2, freq=1)
    assert res.fallback is True
    assert res.method == "drift"
    assert "not a prediction" in res.disclaimer.lower()


def test_points_t_index_continues_series():
    y = np.arange(10, dtype=float)
    res = forecast_values(y, horizon=2, freq=1)
    assert [p.t for p in res.points] == [10.0, 11.0]
