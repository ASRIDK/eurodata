# Eurodata

Open-source **European data intelligence platform**: a Python-importable dataset,
a reproducible ingestion pipeline, and an exploratory Streamlit dashboard for
studying Europe through open data — economy, demographics, digital, energy &
climate, AI & technology, plus a curated **event layer** for before/after
analysis.

- **Facts** — 40k+ official statistics (32 indicators × 50 countries × 2000–2025)
  in a single DuckDB fact table with revision lineage and per-record source.
- **Events** — 43 curated, dated European events (memberships, crises, policy
  milestones) with primary-source URLs, for event studies.
- **Graph** — countries, indicators, sources and blocs as a NetworkX-ready
  structural graph.
- **Provenance-first** — every indicator has a definition, license and an
  explicit *proxy* flag when the series is a stand-in for the official concept.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
python scripts/init_db.py        # create + seed data/eurodata.duckdb
python scripts/run_ingestion.py  # fetch World Bank + Eurostat (a few minutes)
streamlit run app/streamlit_app.py
```

## Python API

```python
import eurodata as ed

ed.countries()                       # 50 European countries
ed.blocs()                           # EU, Eurozone, Schengen, EFTA, EEA, NATO
ed.domains(); ed.indicators()        # catalog with definitions + proxy flags
ed.search_indicators("AI")

ed.series(country="FRA", indicator="GDP")            # tidy DataFrame
ed.series(indicator="Median Age", bloc="EU")         # bloc filter
ed.compare(["FRA", "DEU", "ITA"], "Unemployment Rate")
ed.latest("GDP per capita")
ed.coverage()                        # rows/countries/years per indicator

# Event layer
ed.events(country="UKR", since="2020-01-01")
ed.events(event_type="ai_regulation")
ed.event_study(indicator="Inflation (HICP)",
               event_code="energy-crisis-2021", window_years=3)

# Correlations (per-country Pearson; correlation ≠ causation)
ed.correlate("Internet Users %", "GDP per capita")
ed.lagged_correlation("R&D Expenditure (% GDP)", "GDP per capita", lag=2)

# Escape hatches
ed.query("SELECT * FROM statistic_best LIMIT 10")    # raw SQL → DataFrame
db = ed.open("path/to/other.duckdb")                 # custom database
```

Unknown names raise `ed.EuroDataLookupError` with did-you-mean suggestions.

## Data sources & licensing

| Source | Used for | License |
|--------|----------|---------|
| **Eurostat** (JSON API) | Median age, HICP inflation, AI adoption, ICT specialists | CC BY 4.0 |
| **World Bank** | 22 indicator series (fallback + global coverage) | CC BY 4.0 |
| **ECB / OECD** | *disabled* — fetchers not wired yet; the pipeline records an explicit skip | — |
| **eurodata curated** | event layer (each event cites its primary source) | CC BY 4.0 compilation |

When both Eurostat and World Bank provide a series, `statistic_best` prefers
Eurostat. Three indicators are **proxies** and flagged as such in the catalog
and dashboard: Inflation (WB CPI vs HICP), Broadband (subscriptions vs
coverage), Government Debt (central vs general government).

See [docs/data-dictionary.md](docs/data-dictionary.md),
[docs/events.md](docs/events.md) and
[docs/contributing-sources.md](docs/contributing-sources.md).

## Reproducibility

The database is fully rebuildable from scripts: `init_db.py` (schema + seeds) →
`run_ingestion.py` (fetch with timeouts/retries; failures land in
`ingestion_run` / `ingestion_error`, never silently swallowed) →
`build_graph.py` → `make_release.py` (Parquet export of redistributable data).

```bash
PYTHONPATH=src python -m pytest -q   # 42 tests, no network needed
```
