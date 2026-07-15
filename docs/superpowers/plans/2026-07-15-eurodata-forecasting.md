# eurodata Forecasting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add on-demand forecasting to eurodata — extend any indicator series into the future with an auto-selected statistical model and an uncertainty band, surfaced on the Explore chart and as a Gemini chat tool.

**Architecture:** A pure-numpy engine (`src/eurodata/forecast.py`) fits a small toolkit of models (drift, linear, log-linear, Holt, plus seasonal-naive and additive Holt-Winters for sub-annual series), auto-selects the lowest one-step backtest MAE, and returns a forecast with an empirical band. `EuroData.forecast()` wraps it over the existing `series()` frame; a `GET /api/forecast` route and a `forecast` chat tool expose it; the Explore page draws the projection as a dashed continuation with a shaded band and a prominent disclaimer.

**Tech Stack:** Python 3, numpy, pandas, DuckDB, FastAPI (backend); Next.js 16 + React + Recharts + Tailwind v4 (frontend). Chat is Google Gemini function-calling.

## Global Constraints

- **No new Python dependencies.** Engine uses only `numpy`, `pandas`, and stdlib (`statistics.NormalDist` for the band quantile). No statsmodels.
- **Read-only.** Nothing in this feature writes to the database.
- **Run tests with:** `source .venv/bin/activate; PYTHONPATH=src python -m pytest -q` (ruff is not installed in `.venv`).
- **DB-dependent tests must skip gracefully** when `data/eurodata.duckdb` is absent, following the `pytestmark = pytest.mark.skipif(not Path("data/eurodata.duckdb").exists(), ...)` pattern in `tests/test_web_api.py`. Engine tests are pure and must NOT depend on the DB.
- **Frontend build/verify:** `cd web/frontend && npm run build`. This Next.js is customized — follow existing patterns in the files you edit; do not introduce new conventions.
- **Disclaimer wording is a single source of truth:** the `DISCLAIMER` template lives in `src/eurodata/forecast.py` and is threaded through every surface. Never re-word it per surface.
- **Backend dev server needs `PYTHONPATH=src`:** `PYTHONPATH=src .venv/bin/python -m uvicorn web.backend.main:app --port 8000 --reload`.

---

### Task 1: Forecast engine — non-seasonal core

**Files:**
- Create: `src/eurodata/forecast.py`
- Test: `tests/test_forecast.py`

**Interfaces:**
- Consumes: nothing (pure numpy).
- Produces:
  - `DISCLAIMER: str` — a `str.format(method=...)` template.
  - `@dataclass ForecastPoint(t: float, yhat: float, lo: float, hi: float)`
  - `@dataclass ForecastResult(method: str, freq: int, points: list[ForecastPoint], backtest_mae: float | None, n_obs: int, fallback: bool, disclaimer: str)`
  - `forecast_values(y: np.ndarray, *, horizon: int, freq: int = 1, level: float = 0.8) -> ForecastResult` — operates on a bare value array assumed regularly spaced by one period; `t` on returned points is a 0-based period index continuing the input (`n, n+1, ...`), which the API layer maps to real decimal years. In this task `freq` is accepted but only the non-seasonal models are registered; seasonal models arrive in Task 2.
  - Model functions `_drift`, `_linear`, `_log_linear`, `_holt` each `(y: np.ndarray, h: int) -> np.ndarray` of length `h`.
  - `_MODELS: list[tuple[str, Callable, bool]]` — `(name, fn, seasonal)` in simplicity order; Task 2 appends seasonal entries.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_forecast.py
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
    # next three values continue 2x+5: x=20,21,22 -> 45,47,49
    yhats = [p.yhat for p in res.points]
    assert yhats == pytest.approx([45.0, 47.0, 49.0], abs=1e-6)
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate; PYTHONPATH=src python -m pytest tests/test_forecast.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'eurodata.forecast'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/eurodata/forecast.py
"""On-demand statistical forecasting for eurodata series.

Pure numpy/pandas. Fits a small toolkit of transparent models, auto-selects
the one with the lowest one-step backtest error, and returns a point forecast
with an empirical uncertainty band. Deliberately simple: these are short
series and this is honest trend extrapolation, not prediction.
"""
from __future__ import annotations

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


# (name, fn, seasonal). Simplicity order = tie-break order. Task 2 appends
# the seasonal models.
_MODELS: list[tuple[str, Callable[..., np.ndarray], bool]] = [
    ("drift", _drift, False),
    ("linear", _linear, False),
    ("log_linear", _log_linear, False),
    ("holt", _holt, False),
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


def forecast_values(y: np.ndarray, *, horizon: int, freq: int = 1,
                    level: float = 0.8) -> ForecastResult:
    y = np.asarray(y, dtype=float)
    n = len(y)
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
        best = None  # (mae, simplicity_index, name, fn, errs)
        for idx, (name_i, fn_i, seasonal) in enumerate(_MODELS):
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
            if best is None or cand[:2] < best[:2]:
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate; PYTHONPATH=src python -m pytest tests/test_forecast.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/eurodata/forecast.py tests/test_forecast.py
git commit -m "feat(forecast): non-seasonal forecast engine (drift/linear/log-linear/Holt)"
```

---

### Task 2: Forecast engine — seasonal models

**Files:**
- Modify: `src/eurodata/forecast.py`
- Test: `tests/test_forecast.py`

**Interfaces:**
- Consumes: `_MODELS`, `forecast_values` from Task 1.
- Produces: `_seasonal_naive(y, h, m)` and `_holt_winters(y, h, m)` `-> np.ndarray`; both appended to `_MODELS` with `seasonal=True`. The signature of `_one_step_errors` gains awareness that seasonal fns need `m`; wrap them so the backtest can still call `fn(y[:o], 1)`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_forecast.py

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate; PYTHONPATH=src python -m pytest tests/test_forecast.py -q`
Expected: FAIL — `test_seasonal_series_prefers_a_seasonal_model` fails because no seasonal model is registered (method comes back non-seasonal).

- [ ] **Step 3: Write minimal implementation**

Add the two models above the `_MODELS` list, then extend the list. Because the backtest calls `fn(y[:o], 1)`, register **partial-free** wrappers that read `freq` via a closure created in `forecast_values`. Simplest robust approach: give seasonal fns the signature `(y, h, m)` and adapt the backtest to pass `m`. Implement as follows.

Add the model functions:

```python
def _seasonal_naive(y: np.ndarray, h: int, m: int) -> np.ndarray:
    season = y[-m:]
    reps = int(np.ceil(h / m))
    base = np.tile(season, reps)[:h]
    drift = float(y[-m:].mean() - y[-2 * m:-m].mean()) if len(y) >= 2 * m else 0.0
    step = ((np.arange(h) // m) + 1) * drift
    return base + step


def _holt_winters(y: np.ndarray, h: int, m: int,
                  alpha: float = 0.4, beta: float = 0.1,
                  gamma: float = 0.3) -> np.ndarray:
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
```

Register them (seasonal fns take `m`, so wrap so the registry entry is still callable as `fn(y, h)` — bind `m` at selection time). Replace the `_MODELS` list and update `forecast_values`'s model loop and `_one_step_errors` to pass a per-call `m`-bound function:

```python
_SEASONAL_MODELS: list[tuple[str, Callable[..., np.ndarray]]] = [
    ("seasonal_naive", _seasonal_naive),
    ("holt_winters", _holt_winters),
]
```

In `forecast_values`, build the candidate list dynamically so seasonal models are bound to `m = freq`:

```python
    candidates: list[tuple[str, Callable[[np.ndarray, int], np.ndarray], bool]] = [
        (name_i, fn_i, False) for name_i, fn_i, _ in _MODELS
    ]
    if freq > 1:
        for name_i, fn_i in _SEASONAL_MODELS:
            candidates.append((name_i, (lambda f: lambda yy, hh: f(yy, hh, freq))(fn_i), True))
```

Then iterate `candidates` (not `_MODELS`) in the selection loop, keeping the existing `seasonal and n < 2*freq` guard and `min_hist = 2*freq if seasonal else 2`. The fallback `drift` path is unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate; PYTHONPATH=src python -m pytest tests/test_forecast.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/eurodata/forecast.py tests/test_forecast.py
git commit -m "feat(forecast): seasonal-naive + additive Holt-Winters for sub-annual series"
```

---

### Task 3: Public API — `EuroData.forecast()`

**Files:**
- Modify: `src/eurodata/api.py` (add method to `EuroData`, add module-level delegate + `__all__` entry)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `forecast_values`, `ForecastResult`, `DISCLAIMER` from `eurodata.forecast`; existing `EuroData.series`, `_resolve_country`, `_resolve_indicator`.
- Produces:
  - `EuroData.forecast(indicator: str, country: str, *, horizon: int = 5, level: float = 0.8) -> pd.DataFrame` with columns `t, period, value, kind, lo, hi` (`kind` is `"history"` or `"forecast"`; `lo`/`hi` are null on history rows) and `df.attrs` carrying `method`, `freq`, `backtest_mae`, `fallback`, `n_obs`, `disclaimer`, `unit`, `indicator`, `country`.
  - Module-level `eurodata.forecast = _delegate("forecast")`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_api.py (follow the file's existing DB-skip pattern if present;
# if the file has no skip guard, add one mirroring tests/test_web_api.py)

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
```

If `tests/test_api.py` has no `ed` fixture, add one to `tests/conftest.py`:

```python
import pytest
from pathlib import Path
import eurodata as ed_mod

@pytest.fixture(scope="session")
def ed():
    if not Path("data/eurodata.duckdb").exists():
        pytest.skip("requires the built database")
    return ed_mod.open()
```

(Skip adding if an equivalent fixture already exists — check `tests/conftest.py` first.)

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate; PYTHONPATH=src python -m pytest tests/test_api.py -k forecast -q`
Expected: FAIL with `AttributeError: 'EuroData' object has no attribute 'forecast'`.

- [ ] **Step 3: Write minimal implementation**

Add the import near the top of `src/eurodata/api.py` (with the other `from eurodata...` imports):

```python
from eurodata.forecast import forecast_values
```

Add the method to the `EuroData` class (place it after `compare`, before `coverage`):

```python
    def forecast(self, indicator: str, country: str, *, horizon: int = 5,
                 level: float = 0.8) -> pd.DataFrame:
        """Project one indicator/country series ``horizon`` periods forward.

        Auto-selects a simple model (drift / linear / log-linear / Holt, plus
        seasonal models for sub-annual series) by one-step backtest error and
        returns history + forecast rows with an empirical ``lo``/``hi`` band.
        This is trend extrapolation, not prediction — see ``df.attrs['disclaimer']``.
        """
        hist = self.series(indicator=indicator, country=country)
        hist = hist[hist["value"].notna()].sort_values("t").reset_index(drop=True)
        if hist.empty:
            raise EuroDataLookupError(
                f"No data to forecast for {indicator!r} in {country!r}.")
        # single frequency: infer from the sub-annual columns
        if hist["month"].notna().any():
            freq, step = 12, 1.0 / 12.0
        elif hist["quarter"].notna().any():
            freq, step = 4, 0.25
        else:
            freq, step = 1, 1.0

        res = forecast_values(hist["value"].to_numpy(), horizon=horizon,
                              freq=freq, level=level)

        last_t = float(hist["t"].iloc[-1])
        unit = hist["unit"].iloc[0] if "unit" in hist else None
        fc_rows = []
        for i, p in enumerate(res.points, start=1):
            t = last_t + step * i
            year = int(np.floor(t + 1e-9))
            if freq == 12:
                period = f"{year}-{int(round((t - year) * 12)) + 1:02d}"
            elif freq == 4:
                period = f"{year}-Q{int(round((t - year) * 4)) + 1}"
            else:
                period = str(year)
            fc_rows.append({"t": t, "period": period, "value": p.yhat,
                            "kind": "forecast", "lo": p.lo, "hi": p.hi})

        hist_out = hist[["t", "period", "value"]].copy()
        hist_out["kind"] = "history"
        hist_out["lo"] = pd.NA
        hist_out["hi"] = pd.NA
        out = pd.concat([hist_out, pd.DataFrame(fc_rows)], ignore_index=True)
        out.attrs.update({
            "method": res.method, "freq": res.freq,
            "backtest_mae": res.backtest_mae, "fallback": res.fallback,
            "n_obs": res.n_obs, "disclaimer": res.disclaimer,
            "unit": unit, "indicator": indicator, "country": country,
        })
        return out
```

Add `import numpy as np` to the imports at the top of `api.py` if not already present (it currently imports `math`, `pandas`; add numpy).

Register the delegate — add after the `compare = _delegate("compare")` line:

```python
forecast = _delegate("forecast")
```

And add `"forecast"` to the `__all__` list.

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate; PYTHONPATH=src python -m pytest tests/test_api.py -k forecast -q`
Expected: PASS (skips only if the DB is absent).

- [ ] **Step 5: Commit**

```bash
git add src/eurodata/api.py tests/test_api.py tests/conftest.py
git commit -m "feat(forecast): EuroData.forecast() over the series frame"
```

---

### Task 4: Backend route — `GET /api/forecast`

**Files:**
- Modify: `web/backend/main.py`
- Test: `tests/test_web_api.py`

**Interfaces:**
- Consumes: `EuroData.forecast` (Task 3), the existing `_query` helper and `df_records`.
- Produces: `GET /api/forecast?indicator=&country=&horizon=5&level=0.8` returning
  `{ "history": [...], "forecast": [...], "method", "freq", "backtest_mae", "fallback", "disclaimer", "unit" }`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_web_api.py

def test_forecast_route():
    r = client.get("/api/forecast",
                   params={"indicator": "GDP per capita", "country": "FRA",
                           "horizon": 3})
    assert r.status_code == 200
    body = r.json()
    assert len(body["forecast"]) == 3
    assert body["history"]
    assert body["method"] in (
        "drift", "linear", "log_linear", "holt", "seasonal_naive", "holt_winters")
    assert "not a prediction" in body["disclaimer"].lower()
    fc0 = body["forecast"][0]
    assert {"t", "period", "value", "lo", "hi"} <= set(fc0)


def test_forecast_route_rejects_bad_horizon():
    r = client.get("/api/forecast",
                   params={"indicator": "GDP per capita", "country": "FRA",
                           "horizon": 0})
    assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate; PYTHONPATH=src python -m pytest tests/test_web_api.py -k forecast -q`
Expected: FAIL with 404 (route not defined).

- [ ] **Step 3: Write minimal implementation**

Add to `web/backend/main.py` after the `series` route:

```python
@app.get("/api/forecast")
def forecast(indicator: str, country: str, horizon: int = 5,
             level: float = 0.8) -> dict:
    if not 1 <= horizon <= 30:
        raise HTTPException(422, "horizon must be between 1 and 30")
    if not 0 < level < 1:
        raise HTTPException(422, "level must be between 0 and 1 (exclusive)")
    df = _query("forecast", indicator=indicator, country=country,
                horizon=horizon, level=level)
    hist = df[df["kind"] == "history"]
    fc = df[df["kind"] == "forecast"]
    return {
        "history": df_records(hist[["t", "period", "value"]]),
        "forecast": df_records(fc[["t", "period", "value", "lo", "hi"]]),
        "method": df.attrs["method"],
        "freq": df.attrs["freq"],
        "backtest_mae": df.attrs["backtest_mae"],
        "fallback": df.attrs["fallback"],
        "disclaimer": df.attrs["disclaimer"],
        "unit": df.attrs["unit"],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate; PYTHONPATH=src python -m pytest tests/test_web_api.py -k forecast -q`
Expected: PASS (skips if DB absent).

- [ ] **Step 5: Commit**

```bash
git add web/backend/main.py tests/test_web_api.py
git commit -m "feat(forecast): GET /api/forecast route"
```

---

### Task 5: Frontend — chart supports dashed series + confidence band

**Files:**
- Modify: `web/frontend/src/lib/api.ts` (extend `ChartSpec` series type)
- Modify: `web/frontend/src/components/block-chart.tsx` (render dashed lines + band in the line branch)

**Interfaces:**
- Consumes: existing `ChartSpec`, `BlockChart`.
- Produces:
  - `ChartSpec.series[].dashed?: boolean` — render the line dashed.
  - `ChartSpec.series[].color?: string` — force a specific stroke color (so a forecast line matches its history line).
  - `ChartSpec.series[].band?: { x: number | string; lo: number; hi: number }[]` — a shaded uncertainty band drawn behind the line.

This task is verified by the type-check/build, not a unit test (the frontend has no JS test runner).

- [ ] **Step 1: Extend the type**

In `web/frontend/src/lib/api.ts`, change the `ChartSpec` series shape to:

```ts
export type ChartSpec = {
  kind: "line" | "bar" | "area" | "scatter" | "pie";
  unit: string | null;
  title?: string | null;
  series: {
    name: string;
    points: { x: number | string; y: number | null }[];
    dashed?: boolean;
    color?: string;
    band?: { x: number | string; lo: number; hi: number }[];
  }[];
};
```

- [ ] **Step 2: Render dashed lines and the band**

In `web/frontend/src/components/block-chart.tsx`, in the line/area branch (the part after the `byX` map is built), fold band bounds into the row map and render an `Area` range behind the lines. Replace the `byX` construction and the `<Chart>` body with:

```tsx
  const byX = new Map<number | string, Record<string, number | string | null | [number, number]>>();
  for (const s of spec.series) {
    for (const p of s.points) {
      const row = byX.get(p.x) ?? { x: p.x };
      row[s.name] = p.y;
      byX.set(p.x, row);
    }
    for (const b of s.band ?? []) {
      const row = byX.get(b.x) ?? { x: b.x };
      row[`${s.name}__band`] = [b.lo, b.hi];
      byX.set(b.x, row);
    }
  }
  const data = [...byX.values()].sort((a, b) =>
    String(a.x).localeCompare(String(b.x), "en", { numeric: true }),
  );

  const Chart = spec.kind === "area" ? AreaChart : LineChart;
  return (
    <ChartFrame unit={spec.unit} title={spec.title}>
      <Chart data={data} margin={{ left: 8, right: 8 }}>
        <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.3} />
        <XAxis dataKey="x" fontSize={11} />
        <YAxis fontSize={11} tickFormatter={compactNumber} width={55} />
        <Tooltip formatter={(v, name) => [compactNumber(v), <FlagName key="n" value={name} />]} />
        <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v) => <FlagName value={v} />} />
        {spec.series.map((s, i) =>
          s.band ? (
            <Area
              key={`${s.name}__band`}
              dataKey={`${s.name}__band`}
              stroke="none"
              fill={s.color ?? COLORS[i % COLORS.length]}
              fillOpacity={0.12}
              legendType="none"
              tooltipType="none"
              connectNulls
              isAnimationActive={false}
            />
          ) : null,
        )}
        {spec.series.map((s, i) =>
          spec.kind === "area" ? (
            <Area
              key={s.name}
              dataKey={s.name}
              stroke={s.color ?? COLORS[i % COLORS.length]}
              fill={s.color ?? COLORS[i % COLORS.length]}
              fillOpacity={0.15}
              strokeWidth={2}
              strokeDasharray={s.dashed ? "5 4" : undefined}
              connectNulls
            />
          ) : (
            <Line
              key={s.name}
              dataKey={s.name}
              stroke={s.color ?? COLORS[i % COLORS.length]}
              dot={false}
              strokeWidth={2}
              strokeDasharray={s.dashed ? "5 4" : undefined}
              connectNulls
            />
          ),
        )}
      </Chart>
    </ChartFrame>
  );
```

Note: Recharts renders a range `Area` when its `dataKey` resolves to a two-element `[lo, hi]` array — that is why band values are stored as tuples. The band `Area`s are rendered first so the lines sit on top. `Area` is already imported in this file.

- [ ] **Step 3: Verify the build**

Run: `cd web/frontend && npm run build`
Expected: build succeeds with no type errors.

- [ ] **Step 4: Commit**

```bash
git add web/frontend/src/lib/api.ts web/frontend/src/components/block-chart.tsx
git commit -m "feat(forecast): dashed series + confidence band support in BlockChart"
```

---

### Task 6: Frontend — Explore forecast overlay + disclaimer

**Files:**
- Modify: `web/frontend/src/app/explore/page.tsx`

**Interfaces:**
- Consumes: `/api/forecast`, the extended `ChartSpec` (Task 5), existing `api`, `BlockChart`.
- Produces: a "Forecast →" toggle + horizon control; when on, each country's line gains a dashed forecast continuation + band, and the returned disclaimer renders under the chart.

This task is verified by the build + a manual smoke check.

- [ ] **Step 1: Add state and a fetch**

Near the other `useState` hooks in `Explore`, add:

```tsx
  const [showForecast, setShowForecast] = useState(false);
  const [horizon, setHorizon] = useState(5);
  const [forecasts, setForecasts] = useState<
    Record<string, { forecast: { t: number; period: string; value: number; lo: number; hi: number }[]; disclaimer: string; method: string }>
  >({});
```

Add an effect that loads forecasts for the selected countries when the toggle is on:

```tsx
  useEffect(() => {
    if (!showForecast || !indicator || !selected.length) {
      setForecasts({});
      return;
    }
    let cancelled = false;
    Promise.all(
      selected.map((iso) =>
        api<{ forecast: { t: number; period: string; value: number; lo: number; hi: number }[]; disclaimer: string; method: string }>(
          `/api/forecast?indicator=${encodeURIComponent(indicator)}&country=${iso}&horizon=${horizon}`,
        )
          .then((r) => [iso, r] as const)
          .catch(() => [iso, null] as const),
      ),
    ).then((entries) => {
      if (cancelled) return;
      const map: typeof forecasts = {};
      for (const [iso, r] of entries) if (r) map[iso] = r;
      setForecasts(map);
    });
    return () => {
      cancelled = true;
    };
  }, [showForecast, indicator, selected, horizon]);
```

- [ ] **Step 2: Fold forecasts into the chart spec**

Where `spec` is built (the `const spec: ChartSpec | null = ...` block), after constructing the base per-country series, extend each series with its forecast continuation. Replace the `.map((iso) => ({...}))` series builder so each series also carries `dashed`/`band` for the forecast, and add a **separate** dashed forecast series per country. Concretely, after the existing `spec` is computed, add:

```tsx
  const COLORS = [
    "#2563eb", "#dc2626", "#16a34a", "#9333ea",
    "#ea580c", "#0891b2", "#ca8a04", "#db2777",
  ];
  const specWithForecast: ChartSpec | null =
    spec && showForecast
      ? {
          ...spec,
          series: [
            ...spec.series.map((s, i) => ({ ...s, color: COLORS[i % COLORS.length] })),
            ...selected.flatMap((iso, i) => {
              const f = forecasts[iso];
              if (!f) return [];
              const hist = rows.filter((r) => r.iso3 === iso && r.value !== null);
              const lastX = hist.length ? (hist[hist.length - 1].year as number) : null;
              const lastY = hist.length ? (hist[hist.length - 1].value as number) : null;
              const color = COLORS[i % COLORS.length];
              // include the last history point so the dashed line connects
              const points = [
                ...(lastX !== null ? [{ x: lastX, y: lastY }] : []),
                ...f.forecast.map((p) => ({ x: p.t, y: p.value })),
              ];
              const band = f.forecast.map((p) => ({ x: p.t, lo: p.lo, hi: p.hi }));
              return [{ name: `${iso} forecast`, points, dashed: true, color, band }];
            }),
          ],
        }
      : spec;
```

Note: history x-values are `year` (numbers) and forecast x-values are `t` (decimal years); for annual series these coincide, so the axis stays numeric and continuous. (Sub-annual Explore charts already key on `period`; if `indicator` is sub-annual, forecast points use `t` — acceptable for v1 since Explore's default indicators are annual. A follow-up can align the x-domain for sub-annual overlays.)

Render `specWithForecast` instead of `spec` in the `<BlockChart spec={spec} />` call:

```tsx
          <BlockChart spec={specWithForecast ?? spec} />
```

- [ ] **Step 3: Add the toggle, horizon control, and disclaimer**

In the controls row (next to the country picker), add:

```tsx
        <label className="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showForecast}
            onChange={(e) => setShowForecast(e.target.checked)}
          />
          Forecast →
        </label>
        {showForecast ? (
          <select
            value={horizon}
            onChange={(e) => setHorizon(Number(e.target.value))}
            className="rounded-xl border border-black/15 bg-transparent px-3 py-2 text-sm dark:border-white/20 dark:bg-black"
          >
            {[3, 5, 10].map((h) => (
              <option key={h} value={h}>
                +{h}
              </option>
            ))}
          </select>
        ) : null}
```

Under the chart (near the existing "Source:" line), render the disclaimer prominently when a forecast is shown:

```tsx
          {showForecast && Object.keys(forecasts).length ? (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-800 dark:text-amber-200">
              {Object.values(forecasts)[0].disclaimer}
              {" "}Methods:{" "}
              {selected
                .filter((iso) => forecasts[iso])
                .map((iso) => `${iso}: ${forecasts[iso].method}`)
                .join(", ")}
              .
            </div>
          ) : null}
```

- [ ] **Step 4: Verify the build**

Run: `cd web/frontend && npm run build`
Expected: build succeeds, no type errors.

- [ ] **Step 5: Manual smoke check**

Start backend (`PYTHONPATH=src .venv/bin/python -m uvicorn web.backend.main:app --port 8000`) and frontend (`cd web/frontend && npm run dev`); open `http://localhost:3000/explore`, toggle **Forecast →**. Expected: each line gains a dashed continuation with a shaded band, and the amber disclaimer appears naming the method per country.

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/app/explore/page.tsx
git commit -m "feat(forecast): Explore forecast overlay with band + disclaimer"
```

---

### Task 7: Chat tool — `forecast`

**Files:**
- Modify: `web/backend/tools.py` (tool declaration + dispatch)
- Modify: `web/backend/chat.py` (system-prompt guidance — locate the SYSTEM_PROMPT text)
- Test: `tests/test_web_chat.py`

**Interfaces:**
- Consumes: `EuroData.forecast` (Task 3), `_long_chart`, `ToolOutcome`, `df_records`.
- Produces: a `forecast` tool in `TOOLS` (the declarations list) and a `_dispatch` branch returning a `ToolOutcome` whose `payload` includes `method`, `fallback`, `disclaimer`, and forecast rows, plus a chart of history + forecast.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_web_chat.py (mirror its existing execute_tool test style)

def test_forecast_tool_returns_method_and_disclaimer(ed):
    from web.backend.tools import execute_tool
    out = execute_tool(ed, "forecast",
                       {"indicator": "GDP per capita", "country": "FRA",
                        "horizon": 3})
    assert "error" not in out.payload
    assert out.payload["method"] in (
        "drift", "linear", "log_linear", "holt", "seasonal_naive", "holt_winters")
    assert "not a prediction" in out.payload["disclaimer"].lower()
    assert len(out.payload["forecast"]) == 3
```

(If `tests/test_web_chat.py` lacks an `ed` fixture, reuse the session `ed` fixture from `tests/conftest.py` added in Task 3.)

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate; PYTHONPATH=src python -m pytest tests/test_web_chat.py -k forecast -q`
Expected: FAIL — dispatch returns an error payload (`Tool forecast failed` / unknown tool).

- [ ] **Step 3: Add the tool declaration**

In `web/backend/tools.py`, add to the `TOOLS` declarations list (the list that ends near line 190, after the `correlate` entry):

```python
    {
        "name": "forecast",
        "description": "Project one indicator's series for a single country a few periods into the future, with an uncertainty band. Uses simple auto-selected statistical models (trend/exponential-smoothing; seasonal for monthly/quarterly). This is trend extrapolation, NOT a prediction — always relay the returned disclaimer and name the method. Do not forecast further than a few years.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicator": {"type": "string"},
                "country": {"type": "string", "description": "ISO-3, ISO-2, or name"},
                "horizon": {"type": "integer", "default": 5, "description": "periods ahead (1-15)"},
            },
            "required": ["indicator", "country"],
        },
    },
```

- [ ] **Step 4: Add the dispatch branch**

In `_dispatch` (in `web/backend/tools.py`), add a branch alongside the others:

```python
    if name == "forecast":
        horizon = int(args.get("horizon") or 5)
        horizon = max(1, min(horizon, 15))
        df = ed.forecast(args["indicator"], args["country"], horizon=horizon)
        hist = df[df["kind"] == "history"]
        fc = df[df["kind"] == "forecast"]
        unit = df.attrs.get("unit")
        chart = {
            "kind": "line",
            "unit": unit,
            "title": f"{args['indicator']} — {args['country']} (forecast)",
            "series": [
                {"name": args["country"],
                 "points": [{"x": r["period"], "y": r["value"]}
                            for r in df_records(hist)]},
                {"name": f"{args['country']} forecast",
                 "dashed": True,
                 "points": [{"x": r["period"], "y": r["value"]}
                            for r in df_records(fc)],
                 "band": [{"x": r["period"], "lo": r["lo"], "hi": r["hi"]}
                          for r in df_records(fc)]},
            ],
        }
        return ToolOutcome(
            payload={
                "method": df.attrs["method"],
                "fallback": df.attrs["fallback"],
                "backtest_mae": df.attrs["backtest_mae"],
                "disclaimer": df.attrs["disclaimer"],
                "unit": unit,
                "forecast": [{k: r.get(k) for k in ("period", "value", "lo", "hi")}
                             for r in df_records(fc)],
            },
            chart=chart,
            warnings=[df.attrs["disclaimer"]],
        )
```

Note: the frontend chat chart renderer is the same `ChartSpec`/`BlockChart` extended in Task 5, so `dashed` and `band` render in chat too.

- [ ] **Step 5: Nudge the system prompt**

In `web/backend/chat.py`, find the `SYSTEM_PROMPT` string and add one sentence to its tool guidance:

```
When you use the forecast tool, always state which method it chose and lead with its disclaimer — never present a forecast as a certain prediction.
```

- [ ] **Step 6: Run test to verify it passes**

Run: `source .venv/bin/activate; PYTHONPATH=src python -m pytest tests/test_web_chat.py -k forecast -q`
Expected: PASS (skips if DB absent).

- [ ] **Step 7: Full suite + commit**

Run: `source .venv/bin/activate; PYTHONPATH=src python -m pytest -q`
Expected: all pass (DB-dependent tests skip only if the DB is absent).

```bash
git add web/backend/tools.py web/backend/chat.py tests/test_web_chat.py
git commit -m "feat(forecast): forecast chat tool with method + disclaimer"
```

---

## Self-Review Notes

- **Spec coverage:** Engine (T1–T2) ↔ spec §1; `ed.forecast` (T3) ↔ §2; route (T4) ↔ §3; Explore overlay + disclaimer (T5–T6) ↔ §4a + Framing; chat tool (T7) ↔ §4b. Seasonality (§ sub-annual) is in T2; prominent disclaimer is a first-class field threaded T1→T7.
- **Frequency detection** lives in `EuroData.forecast` (T3), matching the spec's decision that the API layer owns period-label formatting while the engine works in index space.
- **Band** is the empirical `±z·σ·√step` from the spec, using `statistics.NormalDist` (stdlib, honors the no-new-deps constraint).
- **Type consistency:** `ChartSpec` series fields `dashed`/`color`/`band` defined in T5 are the exact names consumed in T6 and produced in T7. `df.attrs` keys set in T3 are the exact keys read in T4 and T7. Model name set `{drift, linear, log_linear, holt, seasonal_naive, holt_winters}` is identical across T1–T7 assertions.
- **Deferred (from spec):** bloc/multi-country aggregate forecasts; sub-annual x-domain alignment in the Explore overlay (noted inline in T6); scenario/what-if.
