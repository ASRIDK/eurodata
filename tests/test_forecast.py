import numpy as np
import pytest

from eurodata.forecast import ForecastResult, _better, forecast_values


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


def test_flat_series_drift_loses_near_tie_to_fitted_model():
    # On perfectly flat data every model backtests to ~0 MAE, so this is a
    # near-tie. _better() specifically forbids drift from winning a near-tie
    # against a fitted model, so a fitted model (e.g. linear) should be
    # selected instead of drift, even though drift is the simplest model.
    y = np.array([10.0] * 10)
    res = forecast_values(y, horizon=2, freq=1)
    assert res.method != "drift"
    assert res.fallback is False


def test_better_lets_drift_win_when_it_clearly_beats_fitted_models():
    # Directly exercise _better() with synthetic (mae, idx, name, fn, errs)
    # candidates matching its real signature: when drift's backtest MAE is
    # strictly and non-negligibly lower than a fitted model's, it is not a
    # near-tie, so drift should win outright.
    drift_cand = (1.0, 0, "drift", None, None)
    fitted_best = (5.0, 1, "linear", None, None)
    assert _better(drift_cand, fitted_best) is True

    # And the reverse near-tie case, pinned directly against the helper:
    # a fitted model within floating-point noise of drift's MAE still beats
    # it, because drift never wins a near-tie against a fitted model.
    tied_fitted_cand = (1.0 + 1e-13, 1, "linear", None, None)
    drift_best = (1.0, 0, "drift", None, None)
    assert _better(tied_fitted_cand, drift_best) is True


def test_empty_series_raises():
    with pytest.raises(ValueError):
        forecast_values(np.array([]), horizon=2)


def test_seasonal_series_prefers_a_seasonal_model():
    # 6 years of monthly data: linear trend + strong 12-month season
    n = 72
    t = np.arange(n)
    season = 10.0 * np.sin(2 * np.pi * t / 12.0)
    y = 100.0 + 0.5 * t + season
    res = forecast_values(y, horizon=12, freq=12, level=0.8)
    assert res.method in ("seasonal_naive", "holt_winters")
    assert len(res.points) == 12
    # forecast should reproduce the seasonal swing, not a flat line
    yhats = np.array([p.yhat for p in res.points])
    assert yhats.max() - yhats.min() > 8.0


def test_seasonal_models_skipped_when_too_short():
    # only 1.5 seasons of monthly data -> seasonal models ineligible
    y = 100.0 + np.arange(18, dtype=float)
    res = forecast_values(y, horizon=3, freq=12)
    assert res.method in ("drift", "linear", "log_linear", "holt")
