# Task Handoff: Correlation Graph (v2 feature) — everything done so far

## Goal
Build and ship the deferred v2 "Correlation Graph" feature — indicator↔indicator correlation pairs with statistical rigour, served via a FastAPI endpoint and a Next.js page.

## What has been built (complete)

### Data layer (`src/eurodata/graph/correlate.py`)
- Computes `CORRELATES_WITH` edges between all indicator pairs that share ≥5 countries and ≥10 combined country-years of overlapping growth-rate data.
- Transform: each indicator per country is converted to year-over-year log growth rates.
- Three lag tests per pair: contemporaneous, A-leads-B (lag 1), B-leads-A (lag 1). Per-country Pearson r + Fisher-z weighted average. Bonferroni penalty ×3 per pair.
- Benjamini-Hochberg FDR correction (q<0.05) across all pairs tested.
- Granger causality (lag 1, per country, Fisher's method combined p) used only when a lag test wins; confirms direction.
- If no lag test wins but one direction's Granger p < 0.05, that lag test is accepted anyway (catches lagged relationships not visible as simple Pearson at lag 1).
- Stored as directed edges in `graph_edge` with edge_type `CORRELATES_WITH`. Props JSON: `relationship`, `direction`, `q_value`, `n_countries`, `granger_p_combined`, `per_country` array.

### Graph build (`src/eurodata/graph/build.py`)
- `build_graph()` inserts `CORRELATES_WITH` edges after `BORDERS`/`COUNTRY_MEMBER_OF`.
- `BORDERS` now stored bidirectionally (both (a,b) and (b,a)) to keep symmetric semantics in the new `nx.DiGraph` world.

### Graph metrics (`src/eurodata/graph/metrics.py`)
- `to_networkx()` returns `nx.DiGraph` (was `nx.Graph`). Carries `props` JSON through as edge attributes.

### API (`src/eurodata/api.py`)
- `EuroData.correlation_graph(indicator: str | None = None) -> pd.DataFrame` — queries `graph_edge` for `CORRELATES_WITH`, joins indicator/domain names, explodes props JSON into columns (relationship, direction, q_value, n_countries). Accepts optional `indicator` name filter (matches either side). Registered as `_delegate` and exported in `__all__`.

### Backend endpoint (`web/backend/main.py`)
- `GET /api/correlation-graph?indicator=...` — returns `{"rows": [...]}` with the dataframe records.
- Auto-sorted by absolute weight descending.

### Frontend page (`web/frontend/src/app/correlations/page.tsx`)
- Route `/correlations`. Navbar link "Correlations" added.
- Indicator dropdown filter (populated from `/api/indicators`).
- Top-N selector: 20 / 50 / 100 / All.
- Cards display: indicator_a ↔ indicator_b, weight with sign, domain, lag label, q-value, country count, horizontal bar (green positive, red negative).
- Arrow: `→` a_leads_b, `←` b_leads_a, `↔` undetermined.
- Loading/error/empty states handled.
- Next.js build passes (static prerender).

### Tests (all passing)
- `tests/test_graph_correlate.py`: 4 tests — planted lagged relationship + direction, idempotent rebuild, no-data empty, `correlation_graph()` API method.
- `tests/test_web_api.py`: 2 new tests — `test_correlation_graph()` checks all fields present, q < 0.05, and indicator filter works. Now 10 total tests in this file.

### Dev server
- Backend on `:8000`, frontend on `:3000`, both with hot-reload. Live endpoint verified returning 247 correlation pairs.

## What remains / possible next steps

1. **Revisit data quality** — several high-weight pairs are trivial (GDP ↔ GDP per capita r≈1.0, same-year). May want to filter out pairs where one indicator is a subcomponent of the other, or add a minimum distinctivity filter.
2. **Per-country drill-down** — the `per_country` array in props has iso3-level correlations, granger p-values, direction for each country. Could add a modal or expandable section per card showing country-level details.
3. **Force-directed graph** — a D3/vis network visualization as alternative to the flat card list.
4. **Update home page** — the roadmap card on `/` lists "Correlation graph" as "Planned". Mark it shipped.
5. **Update docs** — `docs/` directory or README about the correlation methodology.
6. **Export CSV** — add a download button on the correlations page.
7. **Pagination** — the full dataset (247 rows) loads in one request; could add server-side pagination if it gets much larger.

## Important conventions
- Python: 3.13+, duckdb, networkx, statsmodels, scipy, fastapi, pydantic.
- Typescript/React: Next.js 15 (app router), tailwind, `@/lib/api` has `api<T>()` fetch helper, `@/lib/utils` has `cn()`.
- Tests: pytest, no specific runner config. Use `PYTHONPATH=src .venv/bin/python -m pytest`.
- Frontend build: `cd web/frontend && npx next build` (or `npm run build`).
- Dev: `npm run dev` in `web/frontend/`, uvicorn in `web/backend/` (currently running with `--reload`).
- Do NOT add comments to code. Do NOT create README/docs files unless asked.
