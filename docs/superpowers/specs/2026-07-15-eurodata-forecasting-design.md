# eurodata Forecasting — Design

**Date:** 2026-07-15
**Status:** Approved for planning

## Goal

Let users project any indicator series into the future with a confidence band,
surfaced as a dashed continuation on the Explore chart **and** as a tool the
Gemini chat agent can call (e.g. "project French unemployment to 2030"). One
core engine powers every surface.

The series are short (annual series often 10–30 points; some monthly/quarterly).
The honest posture is: simple, explainable statistical extrapolation with an
uncertainty band and a **prominent disclaimer** that this is trend
extrapolation, not prediction.

## Non-goals (v1)

- No causal / scenario / what-if modelling (that would build on the correlation
  layer; deferred).
- No heavy dependencies — implemented in pure numpy/pandas. No statsmodels; its
  prediction intervals are not meaningful on 10-point series and it is a heavy
  dep we have deliberately avoided.
- No per-model hyperparameter tuning beyond what the tiny toolkit needs.

## Architecture

Four layers, each independently testable:

1. **Engine** — `src/eurodata/forecast.py`, pure functions over numpy arrays.
2. **Public API** — `EuroData.forecast(...)` in `api.py` + module-level delegate.
3. **Backend route** — `GET /api/forecast` in `web/backend/main.py`.
4. **Surfaces** — Explore chart overlay (frontend) + `forecast` chat tool.

### 1. Engine — `src/eurodata/forecast.py`

Pure numpy/pandas, no DB or web knowledge. Unit-testable in isolation.

```python
@dataclass
class ForecastResult:
    method: str            # winning model name
    freq: int              # 1 annual, 4 quarterly, 12 monthly
    points: list[Point]    # future: t, yhat, lo, hi
    backtest_mae: float | None
    n_obs: int
    fallback: bool         # True when series too short for selection
    disclaimer: str        # human-readable "naive extrapolation" note

def forecast_series(
    t: np.ndarray, y: np.ndarray, *,
    horizon: int, freq: int, level: float = 0.8,
) -> ForecastResult: ...
```

- **Input contract:** caller passes a clean, sorted, deduped series (decimal-year
  `t` and `value` `y`) and the detected `freq`. The engine does not touch the DB.
- **Candidate models** (each a small `fit → predict(horizon)` closure):
  - Non-seasonal, always available: `drift` (last value + mean step),
    `linear` (OLS on level), `log_linear` (OLS on log; skipped if any y ≤ 0),
    `holt` (two-line exponential smoothing with trend).
  - Seasonal, added only when `freq > 1` **and** `n ≥ 2·freq`:
    `seasonal_naive` (last full cycle + drift), `holt_winters` (additive
    level+trend+season).
- **Selection:** rolling-origin backtest over the last `k` origins
  (`k = min(5, n // 3)`), each forecasting `horizon` (capped at available
  held-out length); score by MAE; lowest wins. Ties broken by model simplicity
  order (drift < linear < log_linear < holt < seasonal_naive < holt_winters).
- **Fallback:** `n < 6` (or `n < 2·freq` for seasonal-only needs) → use `drift`,
  set `fallback=True`, and say so in `disclaimer`.
- **Interval:** band from backtest residual std σ: `yhat ± z(level)·σ·√step`,
  widening with the step count into the future. Explicitly an empirical band,
  not a model predictive interval — reflected in the disclaimer wording.
- **Future period generation:** engine returns future `t` values spaced by
  `1/freq`; period *labels* are produced by the API layer (it owns the
  year/quarter/month formatting already used in `_SERIES_SQL`).

### 2. Public API — `EuroData.forecast(...)`

```python
def forecast(self, indicator: str, country: str, *,
             horizon: int = 5, level: float = 0.8) -> pd.DataFrame: ...
```

- Pulls history via existing `series(indicator=, country=)`.
- Detects `freq` from the returned frame (`month`/`quarter` non-null → 12/4,
  else 1). Requires a single country + indicator (no bloc aggregation in v1).
- Validates: enough points, single frequency, numeric. Raises the existing
  `EuroDataLookupError`-style errors on bad indicator/country.
- Calls `forecast_series`, then builds a tidy long frame:
  `t, period, value, kind ('history'|'forecast'), lo, hi`, with
  `method`, `freq`, `backtest_mae`, `fallback`, `disclaimer` attached via
  `df.attrs`.
- Module-level `eurodata.forecast(...)` delegate, matching the existing
  `_delegate` pattern.

### 3. Backend route — `GET /api/forecast`

`?indicator=&country=&horizon=5&level=0.8` →

```json
{
  "history":  [{ "t": 2019, "period": "2019", "value": 8.5 }, ...],
  "forecast": [{ "t": 2024, "period": "2024", "value": 8.1, "lo": 7.2, "hi": 9.0 }, ...],
  "method": "holt",
  "freq": 1,
  "backtest_mae": 0.34,
  "fallback": false,
  "disclaimer": "Trend extrapolation, not a prediction. ..."
}
```

Read-only, same shape/pattern as `/api/series`. Reuses the shared `_query`
helper and `EuroDataLookupError` handler.

### 4a. Frontend — Explore chart overlay

- A **"Forecast →"** toggle plus a small horizon stepper near the chart on
  `web/frontend/src/app/explore/page.tsx`.
- When enabled, for each selected country the Explore page calls
  `/api/forecast` and extends the existing `ChartSpec`: the historical line
  continues as a **dashed** projection, with a shaded `lo/hi` band.
- **Prominent disclaimer:** the returned `disclaimer` renders as a visible note
  attached to the chart whenever a forecast is shown (not buried in a tooltip).
- Minimal extra chrome otherwise — band + dashes carry the visual.
- `BlockChart` / `ChartSpec` gains the minimum it needs to render a dashed
  series and a band (e.g. per-series `kind`/`dashed` flag and optional
  `band: {lo, hi}` points). Kept additive so existing charts are unaffected.

### 4b. Chat tool — `forecast`

- New `FunctionDeclaration` in `web/backend/tools.py` and a `_dispatch` branch:
  `forecast(indicator, country, horizon?)`.
- Returns history + forecast points and, critically, the `method`, `fallback`,
  and `disclaimer`. The tool result and system-prompt guidance instruct the
  model to state the method and lead with the disclaimer so forecasts are never
  presented as certainty.
- Can drive `render_chart` for a visual, or the existing auto-chart path.

## Data flow

```
series() history ──► detect freq ──► forecast_series() ──► ForecastResult
      │                                                          │
      └──────────────── EuroData.forecast() tidy frame ◄─────────┘
                              │
             ┌────────────────┼─────────────────┐
       /api/forecast     ed.forecast()      forecast chat tool
             │                                    │
      Explore overlay                        Gemini answer
      (dashed + band + disclaimer)      (method + disclaimer + chart)
```

## Error handling

- Unknown indicator/country → existing lookup errors → 400 via the FastAPI
  handler (unchanged pattern).
- Too few points → still returns a `drift` forecast with `fallback=true` and a
  stronger disclaimer, rather than erroring (a forecast the UI can show + warn).
- `level` outside (0,1) or non-positive `horizon` → 400.
- Non-numeric / all-null series → 400 with a clear message.

## Testing

- **Engine (unit):** each model fits a known synthetic series (pure linear →
  `linear` wins with ~0 MAE; seasonal sine → `holt_winters`/`seasonal_naive`
  wins; short series → `drift` + `fallback`). Band monotonic in horizon.
  Deterministic — no network, no DB.
- **API:** `ed.forecast()` on a real annual indicator and a real
  monthly/quarterly one; asserts frame schema, `attrs`, freq detection,
  history+forecast continuity.
- **Backend:** `/api/forecast` happy path + validation errors, mirroring
  existing `tests/test_web_api.py` style.
- **Chat tool:** `execute_tool(ed, "forecast", ...)` returns a payload carrying
  method + disclaimer.
- Update hardcoded catalog/route counts if any test asserts route inventory.

## Open questions / deferred

- Bloc / multi-country aggregate forecasts — deferred (v1 is single series).
- Scenario / correlation-driven what-if — separate future spec.
- Persisting/caching forecasts — not needed; cheap to compute on demand.
