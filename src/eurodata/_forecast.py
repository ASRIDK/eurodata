"""On-demand statistical forecasting for eurodata series.

Pure numpy/pandas. Fits a small toolkit of transparent models, auto-selects
the one with the lowest one-step backtest error, and returns a point forecast
with an empirical uncertainty band. Deliberately simple: these are short
series and this is honest trend extrapolation, not prediction.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

DISCLAIMER = (
    "Trend extrapolation, not a prediction. This projects the historical "
    "pattern forward with a simple statistical model ({method}) and an "
    "empirical uncertainty band; it cannot anticipate future shocks, policy "
    "changes, or turning points."
)

# Minimum observations before we trust model selection; below this we fall back
# to drift and say so.
_MIN_OBS = 6


@dataclass
class ForecastPoint:
    t: float
    yhat: float
    lo: float
    hi: float


@dataclass
class ForecastResult:
    method: str
    freq: int
    points: list[ForecastPoint]
    backtest_mae: float | None
    n_obs: int
    fallback: bool
    disclaimer: str


def _drift(y: np.ndarray, h: int) -> np.ndarray:
    n = len(y)
    slope = (y[-1] - y[0]) / (n - 1) if n > 1 else 0.0
    return y[-1] + slope * np.arange(1, h + 1)


def _linear(y: np.ndarray, h: int) -> np.ndarray:
    n = len(y)
    slope, intercept = np.polyfit(np.arange(n), y, 1)
    return slope * np.arange(n, n + h) + intercept


def _log_linear(y: np.ndarray, h: int) -> np.ndarray:
    n = len(y)
    slope, intercept = np.polyfit(np.arange(n), np.log(y), 1)
    return np.exp(slope * np.arange(n, n + h) + intercept)


def _holt(y: np.ndarray, h: int, alpha: float = 0.5, beta: float = 0.3) -> np.ndarray:
    level = float(y[0])
    trend = float(y[1] - y[0]) if len(y) > 1 else 0.0
    for i in range(1, len(y)):
        prev = level
        level = alpha * y[i] + (1 - alpha) * (level + trend)
        trend = beta * (level - prev) + (1 - beta) * trend
    return level + trend * np.arange(1, h + 1)


def _seasonal_naive(y: np.ndarray, h: int, m: int) -> np.ndarray:
    """Repeat the last full season, plus a linear drift between the last two
    seasons (so a trending-and-seasonal series doesn't flatten out)."""
    season = y[-m:]
    reps = int(np.ceil(h / m))
    base = np.tile(season, reps)[:h]
    drift = float(y[-m:].mean() - y[-2 * m:-m].mean()) if len(y) >= 2 * m else 0.0
    step = ((np.arange(h) // m) + 1) * drift
    return base + step


def _holt_winters(y: np.ndarray, h: int, m: int,
                  alpha: float = 0.4, beta: float = 0.1,
                  gamma: float = 0.3) -> np.ndarray:
    """Additive Holt-Winters: level + trend + seasonal index, updated
    exponentially each step. ``seasons`` grows by one entry per observation
    (indices 0..m-1 seeded from the first season, m..n+m-1 updated in the
    loop), so index ``i`` and index ``i + m`` always refer to the same phase
    of the season."""
    n = len(y)
    level = float(y[:m].mean())
    trend = float((y[m:2 * m].mean() - y[:m].mean()) / m) if n >= 2 * m else 0.0
    seasons = list(np.asarray(y[:m], dtype=float) - level)  # indices 0..m-1
    for i in range(n):
        s = seasons[i]
        prev = level
        level = alpha * (y[i] - s) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev) + (1 - beta) * trend
        seasons.append(gamma * (y[i] - level) + (1 - gamma) * s)  # index i+m
    # seasons now has length m + n; future position p = n+step-1 maps to
    # index n + ((step-1) % m), always valid.
    return np.array([
        level + step * trend + seasons[n + ((step - 1) % m)]
        for step in range(1, h + 1)
    ])


# (name, fn, seasonal), in simplicity order. ``_better()`` uses this order to
# break genuine ties among fitted models, but drift (the naive baseline)
# never wins a near-tie against a fitted model.
_MODELS: list[tuple[str, Callable[..., np.ndarray], bool]] = [
    ("drift", _drift, False),
    ("linear", _linear, False),
    ("log_linear", _log_linear, False),
    ("holt", _holt, False),
]

# Seasonal models take an extra ``m`` (season length) argument, so they can't
# live in ``_MODELS`` directly — ``forecast_values`` binds ``m = freq`` via a
# closure and appends them to the candidate list at selection time.
_SEASONAL_MODELS: list[tuple[str, Callable[..., np.ndarray]]] = [
    ("seasonal_naive", _seasonal_naive),
    ("holt_winters", _holt_winters),
]


def _usable(name: str, y: np.ndarray, freq: int) -> bool:
    """Guard models against inputs they cannot handle."""
    if name == "log_linear":
        return bool(np.all(y > 0))
    return True


def _one_step_errors(fn: Callable[..., np.ndarray], y: np.ndarray, k: int,
                     min_hist: int) -> np.ndarray:
    """One-step-ahead backtest errors over the last ``k`` origins."""
    errs = []
    for o in range(len(y) - k, len(y)):
        if o < min_hist:
            continue
        try:
            pred = float(fn(y[:o], 1)[0])
        except (np.linalg.LinAlgError, ValueError, FloatingPointError):
            return np.array([])  # model unusable on these sub-windows
        if not np.isfinite(pred):
            return np.array([])
        errs.append(abs(float(y[o]) - pred))
    return np.array(errs)


def _z(level: float) -> float:
    return NormalDist().inv_cdf((1 + level) / 2)


def _better(cand: tuple, best: tuple | None) -> bool:
    """Should ``cand`` replace ``best`` as the selected model?

    ``cand``/``best`` are ``(mae, idx, name, fn, errs)``. Lower MAE wins
    outright. Within floating-point noise of each other, the candidates are
    statistically tied: ``drift`` (the naive fallback baseline) never wins a
    tie against a fitted model, since on noiseless/near-linear data its
    endpoint-difference slope can be numerically exact by construction while
    a real regression fit picks up harmless float error — an artifact, not a
    genuine edge. Among non-drift ties, the simpler model (lower index in
    ``_MODELS``) wins, per the module's simplicity-order tie-break.
    """
    if best is None:
        return True
    mae_c, idx_c, name_c = cand[0], cand[1], cand[2]
    mae_b, idx_b, name_b = best[0], best[1], best[2]
    tied = math.isclose(mae_c, mae_b, rel_tol=1e-9, abs_tol=1e-12)
    if not tied:
        return mae_c < mae_b
    if name_b == "drift" and name_c != "drift":
        return True
    if name_c == "drift" and name_b != "drift":
        return False
    return idx_c < idx_b


def forecast_values(y: np.ndarray, *, horizon: int, freq: int = 1,
                    level: float = 0.8) -> ForecastResult:
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n == 0:
        raise ValueError("cannot forecast an empty series")
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    if not 0 < level < 1:
        raise ValueError("level must be in (0, 1)")

    fallback = n < _MIN_OBS
    k = min(5, max(1, n // 3))

    if fallback:
        name, fn = "drift", _drift
        errs = _one_step_errors(_drift, y, k, min_hist=2)
    else:
        candidates: list[tuple[str, Callable[[np.ndarray, int], np.ndarray], bool]] = [
            (name_i, fn_i, seasonal_i) for name_i, fn_i, seasonal_i in _MODELS
        ]
        if freq > 1:
            for name_i, fn_i in _SEASONAL_MODELS:
                candidates.append(
                    (name_i, (lambda f: lambda yy, hh: f(yy, hh, freq))(fn_i), True)
                )

        best = None  # (mae, simplicity_index, name, fn, errs)
        for idx, (name_i, fn_i, seasonal) in enumerate(candidates):
            if seasonal and n < 2 * freq:
                continue
            if not _usable(name_i, y, freq):
                continue
            min_hist = 2 * freq if seasonal else 2
            errs_i = _one_step_errors(fn_i, y, k, min_hist=min_hist)
            if errs_i.size == 0:
                continue
            mae_i = float(errs_i.mean())
            cand = (mae_i, idx, name_i, fn_i, errs_i)
            if _better(cand, best):
                best = cand
        if best is None:  # nothing fit — degrade to drift
            fallback = True
            name, fn = "drift", _drift
            errs = _one_step_errors(_drift, y, k, min_hist=2)
        else:
            _, _, name, fn, errs = best

    backtest_mae = float(errs.mean()) if errs.size else None
    sigma = float(errs.std(ddof=0)) if errs.size else 0.0
    z = _z(level)

    yhat = fn(y, horizon)
    points = [
        ForecastPoint(
            t=float(n + step - 1),
            yhat=float(yhat[step - 1]),
            lo=float(yhat[step - 1] - z * sigma * np.sqrt(step)),
            hi=float(yhat[step - 1] + z * sigma * np.sqrt(step)),
        )
        for step in range(1, horizon + 1)
    ]
    return ForecastResult(
        method=name, freq=freq, points=points, backtest_mae=backtest_mae,
        n_obs=n, fallback=fallback, disclaimer=DISCLAIMER.format(method=name),
    )
