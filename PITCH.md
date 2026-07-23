# Eurodata — Pitch Deck

> Open-source European data intelligence platform.
> 50 countries · 48 indicators · 81,347 data points · 6 dated vintages · 2000–2026
> Python API + Next.js dashboard + AI analyst

---

## The Problem

European open data is **fragmented** across Eurostat, ECB, OECD, World Bank — each with different APIs, formats, licensing, update frequencies, and reliability. Researchers, journalists, and analysts waste time stitching together disjoint datasets. There is no single, provenance-first source that:

- Merges multiple official sources with explicit **reliability scoring**
- Flags **proxy indicators** transparently (e.g., "this CPI is a proxy for HICP")
- Tracks **vintages and revisions** so you know which version you're looking at — and
  **surfaces them**: a `revisions()` API, a `/revisions` browse page, and an inline
  "N values revised" chip on the Explore chart. Every ingestion is stored as a dated
  vintage; the current 6 span 12 days in July 2026, over which no source restated a
  figure, so the revision views are correct but still empty. They fill in as sources
  publish restatements on their monthly and quarterly cycles.
- Provides an **event layer** for before/after causal studies
- Is fully **reproducible** from raw API responses to final dataset

## The Solution

**Eurodata** is a single DuckDB fact database + Python API + Web dashboard that does exactly this.

---

## Functionality by Functionality

### 1. Data Ingestion Pipeline

| Source | Indicators | Reliability | License |
|--------|-----------|-------------|---------|
| Eurostat (JSON API) | Median Age, HICP, GDP growth, AI adoption, ICT specialists, social media, enterprise demography | 0.95 | CC BY 4.0 |
| ECB (SDMX) | Long-term interest rates, exchange rates | 0.95 | Attribution |
| OECD (SDMX) | Monthly unemployment | 0.92 | Attribution |
| World Bank | 22+ series — GDP, population, health, education, R&D | 0.90 | CC BY 4.0 |

**Key idea**: When multiple sources cover the same indicator, `statistic_best` view keeps the highest-reliability source per (geography, indicator, period). Eurostat and ECB beat OECD and World Bank. Three indicators are explicitly flagged as **proxies** with a `proxy_note` explaining the difference.

**Problem encountered**: Eurostat's SDMX library hung for 15+ minutes with no timeout, silently swallowing errors. Rewrote to hit the JSON REST API directly with proper timeouts, retries, and error logging. Raw responses are snapshot with SHA256 for reproducibility.

**Problem encountered**: the `statistic_record` UNIQUE constraint had never fired. Its key included
`quarter` and `month`, which were NULL for annual rows — and since `NULL != NULL`, every row carried
a NULL in the key and the constraint matched nothing, so the `ON CONFLICT DO NOTHING` the ingestion
already used silently deduplicated nothing. A third of the table (147,250 of 436,997 rows) was exact
duplicates and `ingestion_run.records_processed` was inflated. Fixed by making `quarter`/`month`
`NOT NULL DEFAULT 0` — 0 being valid for neither — which is the only one of the three candidate
designs that both enforces uniqueness and leaves `ON CONFLICT DO NOTHING` skipping rather than
raising on DuckDB 1.5.4. The dedup was verified value-preserving: `statistic_best` is byte-identical
before and after across all 81,347 rows.

**Current coverage**: 81,347 rows in `statistic_best` (289,747 in `statistic_record` across 6
vintages), 48 indicators across 9 domains, 50 countries plus 284 NUTS 2 regions, 2000–2026.

### 2. Python API (`eurodata`)

```python
import eurodata as ed

ed.countries()          # 50 European countries
ed.series("FRA", "GDP") # tidy DataFrame with source/provenance
ed.compare(["FRA", "DEU"], "Unemployment Rate")
ed.latest("GDP per capita")
ed.events(country="UKR", since="2020")  # 43 curated events
ed.correlate("R&D", "GDP per capita")   # per-country Pearson r on YoY GROWTH (default)
ed.country_correlations("FRA")          # France's OWN strongest correlations
ed.revisions("GDP", "FRA")              # vintage-by-vintage revision trail
ed.forecast("GDP", "FRA", horizon=5)    # trend extrapolation
```

**Provenance-first correlation**: `correlate()` / `lagged_correlation()` default to
year-over-year **growth rates** (`on="growth"`), so two series that merely trend upward
no longer read as spuriously ~0.99 correlated. `on="levels"` is still available. This is
the same methodology the structural correlation graph uses.

**Key idea**: Every function is also available as a module-level shortcut (`ed.series(...)`) that auto-opens the bundled database. Unknown names raise `EuroDataLookupError` with "did you mean?" suggestions.

**Design choice**: Pure pandas DataFrames output — zero lock-in. You can also drop into raw SQL via `ed.query("SELECT ...")` or get a DuckDB relation for lazy composition.

### 3. Data Model

```
geography (50 countries + 293 NUTS2 regions) ──┬── statistic_record (all vintages)
      │                                         └── statistic_best (deduplicated view)
      ├── bloc (EU, Eurozone, Schengen, EFTA, EEA, NATO)
      │   └── geography_bloc (membership with since/until years)
      ├── indicator ─── domain (9 domains)
      ├── source (5 sources with reliability scores)
      ├── event (43 curated events)
      └── graph_node ─── graph_edge (BORDERS, PROVIDES, MEMBER_OF, CORRELATES_WITH)
```

**Key idea**: The `statistic_record` table preserves **all vintages** — when a source corrects a number, both the old and new versions remain, with vintage dates. `statistic_best` is a view that picks the latest vintage from the highest-reliability source.

**Problem encountered & fixed**: the `UNIQUE(geography_id, indicator_id, source_id, year, quarter, month, vintage_date)` constraint never actually fired. `quarter`/`month` were nullable, so every key carried a NULL and — since `NULL != NULL` — the constraint (and the `ON CONFLICT DO NOTHING` idempotency in the ingestion pipeline) matched nothing; re-ingestion silently accumulated exact duplicates. Fixed by making `quarter`/`month` `NOT NULL DEFAULT 0` (0 = "not applicable"). `statistic_best` already de-duplicated defensively, so the **user-visible dataset is unchanged**; a value-preserving migration (`scripts/migrate_dedup.py`) removes the historical duplicates from the raw table.

**Problem encountered**: The schema started with 2 indicators, grew to 47. Every addition had to be append-only (positional IDs in the seed catalog). Solution: documented this constraint and all additions go at the end of `INDICATORS` list in `reference/catalog.py`.

### 4. Structural Graph

The `graph_edge` table stores 4 edge types:

| Edge Type | Count | Meaning |
|-----------|-------|---------|
| `BORDERS` | ~400 | Geographic adjacency (bidirectional) |
| `MEMBER_OF` | ~200 | Country → bloc membership |
| `PROVIDES` | ~80 | Source → indicator (actually ingested) |
| `CORRELATES_WITH` | **247** | Growth-rate correlation across Europe |

**Key idea (CORRELATES_WITH)**: This is the flagship analytical feature. Instead of naive level-level correlation (which finds spurious trends), it:

1. Converts each indicator to **year-over-year % growth rates** per country
2. Tests **3 lag scenarios** per pair: contemporaneous, A-leads-B, B-leads-A
3. Pools across countries via **Fisher-z weighted average** (fixed-effect meta-analysis)
4. **Bonferroni-corrects** for the 3 lag tests tried on each pair
5. Applies **Benjamini-Hochberg FDR** correction across all pairs tested
6. Confirms direction with **Granger causality** (per-country, Fisher's method combined)

Result: **247 significant edges** at q<0.05. Top correlations are sensible (GDP ↔ GDP per capita r≈0.999, New Business Density ↔ New Businesses Registered r≈0.999). More interesting: R&D Expenditure ↔ High-tech Exports, Internet Users ↔ GDP per capita.

**Why it matters**: You can ask "what leads what?" and get a statistically rigorous answer, not a guess from raw levels.

### 5. Forecasting

Pure numpy/pandas trend extrapolation — **not** prediction. Auto-selects from 6 models (drift, linear, log-linear, Holt, seasonal naive, Holt-Winters) via one-step backtest error. Returns point + empirical uncertainty band.

**Key idea**: Honest about limits. Every forecast carries a disclaimer: "Trend extrapolation, not a prediction. This projects the historical pattern forward… it cannot anticipate future shocks, policy changes, or turning points."

**Problem encountered**: Short annual series (15–25 points) + many model candidates → overfitting risk. Solution: minimum 6 observations before model selection degrades to drift; backtest only the last 5 points; tied models resolve to the simpler one.

### 6. Event Layer

43 curated events spanning:
- EU enlargements (2004, 2007, 2013) and Brexit (2020)
- Euro adoption (2002, 2023, 2026)
- Financial crises (2008, 2011 Eurozone)
- COVID-19 pandemic (2020)
- Energy crisis (2021)
- Russo-Ukrainian war (2022)
- AI regulation (EU AI Act 2024)
- Schengen expansions, NATO accessions, sanctions

**Key idea**: The `event_study()` function runs a before/after comparison: for each event, it finds affected countries (via bloc membership at the event date) and computes mean indicator value in `[event-window, event)` vs `[event, event+window)`. Returns delta, % change, and sample sizes. Descriptive, not causal — but a powerful starting point.

**Problem encountered**: Date alignment — events happen mid-year but most indicators are annual. Solution: use period midpoints (e.g., month → `year + (month-0.5)/12`) for sub-annual precision, then average within windows.

### 7. Sub-national Data (NUTS 2)

**Newest feature** (added 2026-07-16). **293 NUTS2 regions** seeded, **6,896 rows** of GDP per capita from Eurostat. One indicator live: "GDP per capita (NUTS 2 region)".

**Problem encountered**: NUTS codes change every 3 years with the Eurostat classification revision. Solution: pinned to the 2021 classification from the live `nama_10r_2gdp` data dimension, so codes are guaranteed to match the actual ingested data.

**Current gap**: Only one NUTS2 indicator. The pipeline and schema support more, but Eurostat ingestion is slow (per-series API calls).

### 8. Web Frontend (Next.js 16)

**Routes**:

| Route | What it does |
|-------|-------------|
| `/` (Home) | Full-viewport interactive 3D globe hero, stats overview, sources |
| `/explore` | Select countries/indicators → line chart + data table (NUTS regions supported), with an inline revisions chip, staleness badge, forecast accuracy and CSV export |
| `/ranking` | Country rankings by indicator, with CSV export |
| `/correlations` | Browse the correlation edges, filter by indicator, sort by strength |
| `/revisions` | Browse how official statistics changed across vintages — largest revisions and most-revised indicators |
| `/propagate` | Shock an indicator and trace the ripple across the correlation graph, hop by hop, with the path each result arrived by |
| `/country/[iso3]` | Per-country profile: KPIs, bloc memberships, events, and the country's **own** strongest growth-rate correlations |
| `/events` | Browse 43 events, run event-study analysis |
| `/chat` | AI analyst with Gemini — natural language over the dataset |

**Key idea**: Every page fetches from the FastAPI backend with a single `api<T>()` helper + typed `Row`/`ChartSpec`/`Block` types. The backend wraps the Python API 1:1 — zero business logic in the frontend.

**Mobile**: a responsive hamburger navbar; verified no horizontal overflow at a 390px viewport across every route.

**Problem encountered**: Tailwind v4 migration — shadcn/ui doesn't support v4 yet. Solution: manual `components/ui/` folder with Tailwind-only components, no shadcn dependency.

### 9. AI Analyst (Chat)

Gemini function-calling loop over 7 read-only tools:
- `get_series`, `compare_countries`, `get_latest`, `search_indicators`
- `get_events`, `run_event_study`
- `get_correlation_graph`, `correlate_indicators`
- `render_chart`, `render_table`

**Key idea**: The model never invents numbers — every tool call hits the real DuckDB. The system prompt explicitly tells it to say when a series is a proxy and to never present forecasts as predictions. Responses come back as typed blocks: text / chart / table / sources / warning / follow_ups.

**Problem encountered**: Google Gemini free tier regularly throws 429 (rate limit) and 503 (overloaded). Solution: retry loop with 2 fallback models (`gemini-3.5-flash`, `gemini-3-flash-preview`). Without a configured API key, the endpoint returns 503 with a clean frontend error.

### 10. Streamlit Dashboard (Legacy)

The original 6-tab dashboard (Overview, Economy, Demographics, Digital, Energy, Graph). Still functional, served as the template for the web frontend. Pure Python + Plotly + NetworkX.

**Problem encountered**: Streamlit reruns the entire script on every interaction. Solution: `@st.cache_data` with underscore-prefixed connection parameter to skip hashing. DB opened read-only to coexist with ingestion.

---

## Architecture

```
┌──────────┐     ┌──────────────┐     ┌────────────────┐
│  Sources  │────▶│  Ingestion   │────▶│  DuckDB fact   │
│ Eurostat │     │  Pipeline    │     │  table (81k    │
│ World Bank│     │  (scripts/)  │     │  rows + schema)│
│ ECB/OECD │     │              │     │                │
└──────────┘     └──────────────┘     └───────┬────────┘
                                              │
                    ┌─────────────────────────┼──────────────┐
                    │                         │              │
               ┌────▼─────┐           ┌───────▼────┐  ┌─────▼──────┐
               │  Python   │           │  FastAPI    │  │  Streamlit  │
               │  API      │           │  Backend    │  │  Dashboard  │
               │  (eurodata)│           │  (:8000)    │  │  (:8501)    │
               └──────────┘           └───────┬────┘  └────────────┘
                                              │
                                        ┌─────▼──────┐
                                        │  Next.js 16 │
                                        │  Frontend   │
                                        │  (:3000)    │
                                        └────────────┘
```

---

## Key Differentiators

| Feature | Eurodata | Other tools |
|---------|----------|-------------|
| **Provenance-first** | Every row tracks source + vintage + proxy flag | Most aggregate without source tracking |
| **Event layer** | 43 dated events with before/after analysis | None |
| **Correlation graph** | 247 FDR-corrected, growth-rate, lag-tested edges | Raw level-level correlation |
| **Multiple sources** | Reliability scoring deduplicates across 5 sources | Single-source silos |
| **Reproducible** | `init_db → ingest → build_graph → release`, all scripted | Manual exports |
| **Sub-national** | 293 NUTS2 regions with GDP per capita | Country-level only |
| **AI interface** | Natural language over the dataset | API or dashboard only |

---

## What's Being Built Now

### Globe Hero (home page redesign)

Full-viewport interactive 3D globe (cobe library) replacing the current hero:
- **On load**: Only the globe + transparent navbar — zero distraction, pure data visualization
- **Zoomed on Europe** with markers at 50 European cities (capitals + economic hubs)
- **Click a marker** → popup with 5 eurodata KPIs (GDP, population, unemployment, etc.) fetched live from the API
- **Scroll down** → globe smoothly shrinks into the top area, content (stats, sources, roadmap) scrolls in
- **Navbar** transitions from transparent to solid on scroll

Inspiration: [0.xyz/security](https://www.0.xyz/security) — clean, dark, minimal, user's focus is on the data.

---

## Test Coverage

**99 tests passing** (20s suite, no network needed):

| Test file | What it covers |
|-----------|---------------|
| `test_api.py` | Every EuroData method against a real in-memory DB |
| `test_web_api.py` | 10 FastAPI endpoint tests |
| `test_web_chat.py` | AI analyst flow |
| `test_graph_correlate.py` | Planted lagged relationship + FDR |
| `test_forecast.py` | All 6 models, backtest, edge cases |
| `test_seed.py` | Schema + seed integrity |
| `test_sources_*.py` | Eurostat, World Bank, ECB, OECD normalizers |
| `test_pipeline.py` | Full ingestion cycle |
| `test_db_schema.py` | 293 NUTS2 regions, 6 blocs, 47 indicators |

---

## How to Run

```bash
# Backend (from repo root)
source .venv/bin/activate
PYTHONPATH=src:. uvicorn web.backend.main:app --port 8000

# Frontend (separate terminal)
cd web/frontend && npm run dev

# AI analyst needs GOOGLE_API_KEY in .env
# Tests
PYTHONPATH=src .venv/bin/python -m pytest
```

---

## Current Gaps & Next Steps

1. **More NUTS2 indicators** — pipeline supports it, but Eurostat ingestion is per-series
2. **ECB/OECD stubs** — both return `[]`; need real dataflow wiring
3. **GDP deflator** — missing; would allow real vs nominal separation
4. **Health/Social Media domains** — data exists but no event coverage for these domains
5. **Playwright tests** — need CI integration (the frontend is not yet covered by CI)
6. **Chat streaming** — currently waits for full response; SSE would improve UX
7. **Run the dedup migration** — `scripts/migrate_dedup.py` against the built database
   (removes the historical `statistic_record` duplicates; value-preserving)

*(Now shipped, was previously deferred: Explore URL-state sync, a keyboard/screen-reader
alternative for the globe canvas, non-color series encoding, and dual-axis support for
mixed-unit comparisons — final visual tuning of the dash palette / dual axis is a suggested
polish pass.)*
