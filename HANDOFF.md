# eurodata — Session Handoff

> **Update (2026-07-24, country profiles + maps).** `/country/[iso3]` now leads
> with a data-composed summary and two choropleths, and the correlations section
> is removed. `EuroData.country_profile()` returns the facts (rank, European
> median, blocs, most distinctive decade movers); the frontend composes the
> prose so it can't drift from the numbers. "Fastest rising/falling" is a
> cross-country percentile of the decade change, not raw percent — raw percent
> was dominated by rate indicators with near-zero baselines and surfaced
> Europe-wide shifts (see spec). `components/choropleth.tsx` is a dependency-free
> SVG map; two GISCO GeoJSON files are vendored under `web/frontend/public/geo/`
> via `scripts/fetch_geometry.py` (NUTS **2024**, countries joined on ISO3_CODE).
> Spec: `docs/superpowers/specs/2026-07-23-country-profile-summary-and-maps-design.md`.
> Verified: 167 pytest, eslint 0, build clean, browser-driven for a full-data
> country (FRA), a no-regional-data country (ISL), and Kosovo (no GISCO geometry,
> renders unhighlighted with a note).
>
> **Regional coverage: 33 of 50 countries.** The other 17 show a national-level
> context map and an honest "no regional data" state. Filling them is specced
> separately (`2026-07-23-subnational-coverage-expansion-design.md`) and **not
> yet implemented** — it is a data-sourcing project: 5 are microstates (no
> subdivisions), 8 are in DOSE V2.14 (RUS/UKR/CHE/GEO/AZE/BLR/BIH/GBR), 4 need
> bespoke national sources. **Blocking check before starting it:** GADM geometry
> prohibits commercial redistribution, so its vendoring must be confirmed or
> Natural Earth admin-1 used instead.

> **Update (2026-07-23, propagation engine).** `/propagate` ships: shock one
> indicator, follow signed activation along the `CORRELATES_WITH` edges, read the
> result as a cascade of hops. Core is `src/eurodata/graph/propagate.py` (pure, no
> DB or pandas import), surfaced via `ed.propagate()`, `GET /api/propagate`, and
> the page. Spec and its calibration measurements:
> `docs/superpowers/specs/2026-07-23-propagation-engine-design.md`.
>
> Two graph properties shaped the algorithm and are worth knowing before tuning:
> summing arrivals saturates (a shock reaches 30 of 36 indicators), hence
> strongest-path rather than accumulation; and without `edge_floor` almost
> everything lands on hop 1, because at median degree 14 a direct edge beats a
> two-hop product. Defaults `decay=0.6 threshold=0.05 edge_floor=0.30 max_hops=3`
> give ~13 nodes over two hops for a typical shock.
>
> **Known limitation:** those defaults were calibrated against the *pooled*
> `correlation_graph()` only. They do not transfer to `propagate(country=...)`,
> where per-country correlations are uniformly stronger — ESP returns 27 nodes,
> DEU 17, FRA 23, and raising `edge_floor` barely helps (ESP at 0.6 still returns
> 19). The page drives the pooled mode only, so the default user path is the
> calibrated one; per-country needs its own calibration before it is exposed in
> the UI.

> **Update (2026-07-23, CI + source monitoring + api coverage).** PRs #1-#5 are
> merged to `main`; the dedup migration has been run against the production
> database (436,997 → 289,747 rows, `statistic_best` byte-identical). Added
> since:
>
> - **CI covers the frontend.** `.github/workflows/ci.yml` gained a `frontend`
>   job running `npx eslint src` then `npm run build`. Previously CI ran pytest
>   only, so a lint or build regression could land on `main` unnoticed.
> - **Scheduled source monitoring.** `scripts/check_sources.py` probes every
>   registered fetcher against the live APIs and reports records, per-series
>   errors, and fatal failures; exit 1 if an enabled source returns nothing.
>   `.github/workflows/source-health.yml` runs it Mondays 06:00 UTC and opens (or
>   comments on) an issue labelled `source-health`, closing it when the sources
>   recover. This exists because the original failure mode was *silent*: a
>   broken Eurostat fetcher looked identical to one with no data. Note this is a
>   health probe, not an ingestion — nothing is written to DuckDB, since the
>   database is gitignored and CI has nowhere to persist it. **Ingestion itself
>   is still a manual local step** (`scripts/run_ingestion.py`).
>   Baseline run: ECB 588, Eurostat 884, OECD 491, World Bank 1,666 records; the
>   World Bank probe takes ~6 min because it paces its ~34 series.
> - **`api.py` coverage.** 32 of 34 public methods are now exercised (the other
>   two are a property and an internal helper). Added tests for `domains`,
>   `sources`, `years`, `event_types`, `ingestion_summary` (including that an
>   error outside a run's window is *not* attributed to it), `correlation_graph`
>   before the graph is built, and `indicator_trends` (rebasing to 100, raw
>   medians, the year window, and the empty result when an indicator has no
>   data). Suite: 130 passing. The `indicator_trends` and `ingestion_summary`
>   tests were mutation-checked — both fail when the behaviour they describe is
>   broken.

> **Update (2026-07-22, frontend a11y follow-ups).** On branch
> `feat/frontend-a11y-followups` (stacked on PR3). The three items PR3 deferred
> now ship, build/lint/Playwright-verified: (1) **Explore URL-state sync** —
> indicator/country/forecast/horizon read from and mirrored to the query string
> (shareable/bookmarkable); (2) **globe accessibility** — `role="img"` +
> aria-label on the canvas and an `sr-only` `<nav>` of all 50 countries linking
> to `/country/[iso3]` (keyboard/screen-reader path); (3) **chart mixed-unit
> dual-axis + non-color encoding** — optional per-series `axis:"left"|"right"`
> (+`unitRight`) renders a second Y axis, and plain multi-series line/area charts
> get distinct dash patterns as a non-colour channel (forecast charts opt out).
> eslint 0/0, `npm run build` clean, 390px no-overflow retained. Remaining
> polish: final visual tuning of the dash palette / dual axis.

> **Update (2026-07-22, PR3 — frontend: revisions UI, mobile, per-country
> correlations).** Stacked on PR2. Mobile navbar rebuilt as a responsive
> hamburger (aria-expanded/controls, Esc + click-away); verified
> `scrollWidth === clientWidth` at 390px on all 8 routes via Playwright. New
> `/revisions` browse route (largest revisions + most-revised leaderboard) and
> an inline `RevisionsChip` ("N values revised" → vintage trail) on the Explore
> chart. Country page now uses `/api/country-correlations` (the country's own
> growth-rate correlations) and drops the "Europe-wide" caveat. Added: CSV
> export buttons (Explore/Ranking via `/api/export`), amber staleness badges
> from `years_stale`, forecast typical-error (`backtest_mae`) surfaced on the
> Explore forecast note, per-route `metadata` via `layout.tsx` files (fixing the
> shared `<title>` and the stale "26 indicators/50 countries" → "48/50"), and an
> `exportUrl` helper + revision types in `lib/api.ts`. The 4 pre-existing
> `react-hooks/set-state-in-effect` lint errors are resolved (eslint **0
> errors/0 warnings**, from 4); `npm run build` clean (TypeScript passes).
> Lint locally with `./node_modules/.bin/eslint src` (a global eslint 10 shadows
> the project's eslint 9 and errors — use the local binary).
> **Deferred frontend follow-ups** (need live/visual verification): dual-axis
> for mixed-unit comparisons, a keyboard/text alternative + non-color encoding
> for the globe canvas, and Explore URL-state sync. PITCH.md rewritten to match
> what now ships.

> **Update (2026-07-22, PR2 — revisions API + backend hardening).** Stacked on
> PR1. New public API: `revisions(indicator, country)` (full vintage-by-vintage
> trail from `statistic_record`, with a per-period summary in `df.attrs`),
> `revisions_summary(country?, indicator?)` (one row per revised
> indicator/country/period — feeds the /revisions browse view), and
> `country_correlations(country)` (walks the FDR-surviving graph pairs and
> computes *this country's* growth-rate r, so country pages stop showing
> Europe-wide edges as local). `correlate()`/`lagged_correlation()` now default
> to **YoY growth** (`on="growth"`; `on="levels"` still available) so two
> trending series no longer read ~0.99; the chat `correlate` tool description
> was updated to match. New endpoints: `/api/revisions`,
> `/api/revisions-summary`, `/api/country-correlations`, `/api/export`
> (CSV/Parquet for series/latest/compare/coverage/revisions-summary),
> `years_stale` now flows through `/api/coverage`. `/api/countries` and
> `/api/indicators` carry an ETag/Cache-Control keyed on the latest vintage
> (304 on `If-None-Match`). `/api/chat` is rate-limited per IP (429 +
> `Retry-After`; `CHAT_RATE_LIMIT`/`CHAT_RATE_WINDOW`, default 20/60s).
> `deps.py` dropped the global `threading.Lock` for per-request DuckDB cursors
> over one shared read-only connection (concurrent readers). Tests:
> `tests/test_web_endpoints.py` (in-memory injected DB, no real data needed) +
> new api coverage. Suite: 87 passing, 34 skipped (real-DB fixtures).

> **Update (2026-07-22, PR1 — data-integrity sentinel): the `statistic_record`
> UNIQUE constraint now actually fires.** `quarter`/`month` were nullable, so
> every key carried a NULL and (since `NULL != NULL`) the constraint — and the
> `ON CONFLICT DO NOTHING` dedup in `ingest/pipeline.py` — matched nothing;
> ~34% of rows were exact duplicates. They are now `NOT NULL DEFAULT 0` (0 =
> "not applicable"; annual rows are (0,0)). Four read-side traps in `api.py`
> that branched on month/quarter *nullity* were switched to `> 0`
> (`_SERIES_SQL`, `provenance`, `forecast` frequency inference, `event_study`
> `t_mid` — the last two silently mis-treated every annual series once NULL
> became 0). `coverage()` gained an additive `years_stale` column.
>
> **OPEN ITEM — run locally against the built DB** (it isn't in the repo; the
> web clone can't reproduce its 6 vintages): `python scripts/migrate_dedup.py`.
> It backs up to `data/eurodata.duckdb.bak`, converts NULL→0, collapses exact
> duplicates (keeps the most-recent `retrieved_at` per key), rebuilds with the
> sentinel constraint, and refuses to proceed if any `statistic_best` sample
> value changes. Then fill the post-dedup row/indicator counts into PITCH.md.
> Migration logic is unit-tested (`tests/test_migrate_dedup.py`) against a
> synthetic pre-migration DB. Suite: 77 passing, 34 skipped (real-DB fixture).

> **Update (2026-07-13): Startups & Business domain (7th) added** — 6
> indicators, ids 27–32, +4,380 rows (31,190 total in `statistic_best`):
> New Business Density / New Businesses Registered (WB Entrepreneurship DB,
> 2006–2024), Self-employed % / Private Sector Credit (WB, 2000–2025),
> Enterprise Birth Rate (Eurostat bd_9bd_sz_cl_r2, V97020, 2004–2020) and
> High-growth Enterprises % (Eurostat bd_9pm_r2, V97460, 2011–2020) — both
> Eurostat filter sets verified against the live JSON API; those datasets END
> in 2020 (discontinued after NACE rev). WB Doing Business codes (IC.REG.*)
> are retired from the API — don't re-add. Graph rebuilt (7 domain nodes).
> Tests updated (hardcoded 26/6 counts in test_seed/test_api/test_graph_build
> are now 32/7); suite 58 passing. Live AI-analyst answer over the new domain
> verified (Estonia tops EU new-business density, 26.76/1k in 2024).

> **Update (2026-07-10, v3 session): web platform landed.** FastAPI backend
> (`web/backend/`) wraps the `ed` API 1:1 over a read-only DuckDB handle and
> adds `POST /api/chat` — a Claude tool-use AI analyst over whitelisted
> read-only tools, answering with typed blocks (text/chart/table/sources/
> warning/follow_ups). Next.js 16 + Tailwind v4 frontend (`web/frontend/`):
> Home, Explore, Events, and the flagship `/chat` page with the AIInput
> component (auto-resize, Enter submits, mic icon, send button fades in).
> Spec: `docs/superpowers/specs/2026-07-10-eurodata-v3-web-prompt.md`.
> Verified: 58 pytest passing; `npm run build` clean (4 routes); Playwright
> drive of /chat (empty state, submit, 503 failure state) and /explore (live
> chart + table from the backend).
>
> **Provider switched to Google Gemini** (same session, user request): chat
> uses the `google-genai` SDK, key `GOOGLE_API_KEY`, model `GEMINI_MODEL`
> (default `gemini-flash-latest`; retries + fallbacks `gemini-3.5-flash`,
> `gemini-3-flash-preview` ride out 429/503/retired-model errors — Gemini
> free tier throws these regularly; `gemini-2.5-*` is retired for new keys).
> **Live end-to-end verified** with a real key: Gemini called get_series and
> answered France-GDP-since-2000 with text + 26-point chart + table +
> `GDP · World Bank` provenance chip + follow-ups. Key lives in `.env`
> (gitignored); without it /api/chat returns 503 and the UI shows a clean
> error. Run: `PYTHONPATH=src:. uvicorn web.backend.main:app --port 8000` +
> `cd web/frontend && npm run dev` (see `web/README.md`).

> **Superseded (2026-07-09, v2 session):** the platform work described in the
> README has since landed: public Python API (`import eurodata as ed`,
> `src/eurodata/api.py`), Eurostat fetcher rewritten on the JSON API with
> timeouts/retries (no more 15-min hang; Median Age + exact HICP + AI adoption
> + ICT specialists now real), World Bank expanded to 24 series, AI & Technology
> domain, curated `event` table (43 events) with `event_study`/`correlate`
> utilities, corrected bloc memberships (Eurozone 21, Schengen 29, NATO added),
> `ingestion_error` table + explicit skip reasons for ECB/OECD, provenance
> columns (`definition`/`is_proxy`/`proxy_note`), 10-tab dashboard (Events,
> Correlations, Data Catalog, AI & Tech), docs under `docs/`, 42 tests passing.
> Database: 40,389 rows. Sections below describe the **v1** session only.

_Date: 2026-07-09_

This document captures everything done in this working session: the starting
state, what was investigated, the root causes found, every change made, how it
was verified, and what is deliberately left open.

---

## 1. Starting point

The request was simply **"launch the euro data project."** The repo is a
Python / Streamlit + DuckDB project (`eurodata`) — an open, file-based European
data-intelligence dataset (facts + a structural graph). Not a Vercel/Next.js
project (session hooks kept mis-suggesting those skills; ignored).

On first launch the app came up fine at `http://localhost:8501`, but the user's
reaction was: **"there is only a graph and a table, nothing else… didn't you
take inspiration from AfriNet?"**

That kicked off the real work.

---

## 2. Diagnosis

### 2a. The app was a 40-line MVP
`app/streamlit_app.py` was literally: two dropdowns → one `st.line_chart` → one
`st.dataframe`. That "graph" was the line chart; the "table" was the dataframe.
Nothing else — no domains, no map, no rankings, and the structural graph
(73 nodes / 174 edges) was **not surfaced at all**.

### 2b. AfriNet was never a build target
`docs/reference/afrinet-reference.md` is a **competitor teardown** (an analysis
of someone else's repo: 7 domains, 20+ sources, CrewAI agents, forecasting), not
a spec eurodata was built to match. The README explicitly scopes v1 down to
_"dataset + structural graph"_ with correlation/forecasting deferred to v2.

### 2c. The data was almost empty — and the "primary" sources were dead
The schema defines **10 indicators across 4 domains**, but only **2** had data.
Investigation of the source fetchers revealed why:

| Source | Status | Result |
|--------|--------|--------|
| **ECB** (`sources/ecb.py`) | stub — `fetch()` returns `[]` | 0 rows |
| **OECD** (`sources/oecd.py`) | stub — `fetch()` returns `[]` | 0 rows |
| **Eurostat** (`sources/eurostat.py`) | real SDMX calls, but **every call wrapped in `except Exception: continue`** | 0 rows (silently) |
| **World Bank** (`sources/world_bank.py`) | real, but only **2 series mapped** (`SP.POP.TOTL`, `NY.GDP.MKTP.CD`) | **2,441 rows — 100% of the dataset** |

So the entire dataset was being carried by the World Bank _fallback_ fetcher
with just two hardcoded codes. Confirmed via `ingestion_run` history: ECB /
Eurostat / OECD all "completed" with `records_processed = 0`.

### 2d. The Eurostat 15-minute hang
When ingestion was later run with per-source timing, Eurostat took **923
seconds (~15 min)** and returned 0 records — its SDMX client blocks with no
timeout across all 10 series, and the `except: continue` hides it. **This was
the reason earlier background ingestion runs appeared "stuck."** It is currently
dead weight (World Bank covers the same indicators).

---

## 3. Plan chosen by the user

Presented a fork; the user chose **"Ingest first, then UI"**, then for the UI
chose the **"Full multi-domain dashboard"** option (tabs, KPIs, compare, bloc
rankings, choropleth map, network graph).

---

## 4. Changes made

### Phase 1 — Data ingestion

**`src/eurodata/sources/world_bank.py`** — expanded `WB_CODES` from 2 → 9
Eurostat-api-code → World Bank-series mappings:

| Indicator | Eurostat code | World Bank series | Note |
|-----------|---------------|-------------------|------|
| Population | `demo_pjan` | `SP.POP.TOTL` | (existing) |
| GDP | `nama_10_gdp` | `NY.GDP.MKTP.CD` | (existing) current US$ |
| GDP per capita | `sdg_08_10` | `NY.GDP.PCAP.CD` | current US$ |
| Inflation (HICP) | `prc_hicp_aind` | `FP.CPI.TOTL.ZG` | **proxy** — CPI ≠ HICP |
| Unemployment Rate | `une_rt_a` | `SL.UEM.TOTL.ZS` | |
| Internet Users % | `isoc_ci_ifp_iu` | `IT.NET.USER.ZS` | |
| Broadband Coverage % | `isoc_ci_it_en2` | `IT.NET.BBND.P2` | **proxy** — subs/100 ≠ household coverage |
| Renewable Energy Share % | `nrg_ind_ren` | `EG.FEC.RNEW.ZS` | |
| Greenhouse Gas Emissions | `env_air_gge` | `EN.GHG.ALL.MT.CE.AR5` | Mt CO2e |

**Median Age** (`demo_pjanind`) has no honest World Bank equivalent → left empty,
awaiting Eurostat wiring. Proxy caveats are documented as inline comments; source
is recorded as "World Bank" so provenance stays truthful.

Result: **2,441 → 10,251 rows**, 9 indicators, all 4 domains, ~49 countries,
years 2000–2024.

### Phase 2 — Dashboard UI

**`app/components.py`** — rewritten as a pure (Streamlit-free, unit-testable)
data + figure layer. Public function `indicator_timeseries(con, iso3, name)` was
**preserved** (its signature/return is covered by `tests/test_components.py`).
Added:
- `list_countries`, `list_indicators` (only indicators with data), `indicators_in_domain`, `indicator_unit`
- `multi_country_timeseries`, `kpi` (latest value + YoY %)
- `latest_by_country`, `bloc_rankings`
- `choropleth_figure` (Plotly `scope="europe"`, ISO-3 locations — no GeoJSON needed)
- `network_figure` (reuses `eurodata.graph.metrics`: NetworkX spring layout, degree centrality → node size, Louvain community, + top-centrality table)

**`app/streamlit_app.py`** — rewritten into a 6-tab dashboard with cached data
access (`@st.cache_resource` connection + `@st.cache_data` query wrappers using
`_con` underscore param so Streamlit skips hashing the connection):
- **Overview** — 6 KPI cards (YoY deltas), Europe choropleth map, bloc rankings bar + table
- **Economy / Demographics / Digital / Energy & Green** — multi-country compare line chart + latest-value ranking table
- **Graph** — structural network + top-centrality table

### Correctness fixes
- **USD/EUR mislabel:** GDP & GDP per capita were seeded with unit `EUR`, but the
  ingested World Bank values are **current US$**. Corrected to `USD` in **both**
  the live DB (`UPDATE indicator …`) and the seed catalog
  (`src/eurodata/reference/catalog.py`).
- Replaced the retired `use_container_width=True` with `width="stretch"`
  (deprecation cutoff has passed).

### Note on `connect(read_only=True)`
The app opens the DB **read-only** (`get_con()` → `connect(read_only=True)`), so
it coexists with ingestion/other readers instead of holding an exclusive write
lock. (During the session the read-write lock repeatedly blocked inspection —
read-only avoids that. This edit to line 22 was made mid-session and kept.)

---

## 5. Files touched

```
src/eurodata/sources/world_bank.py     WB_CODES: 2 → 9 indicators
src/eurodata/reference/catalog.py      GDP / GDP per capita unit EUR → USD
app/components.py                       rewritten: pure data + Plotly figure helpers
app/streamlit_app.py                    rewritten: 6-tab dashboard + caching
data/eurodata.duckdb                    re-ingested (10,251 rows); GDP units → USD
HANDOFF.md                              this file
```

No changes to tests, schema, or the graph build.

---

## 6. Verification (evidence, not assertion)

- **Full test suite:** `pytest` → **24 passed**.
- **Component smoke test:** every helper run against a copy of the real DB —
  countries, indicators, time series, multi-country, KPI, latest, bloc rankings,
  choropleth (1 trace), network (6 traces, top node = "European Union" bloc).
- **Headless app run:** Streamlit `AppTest.from_file(...).run()` executes the
  entire script (all 6 tabs) with **0 exceptions**; GDP KPI renders
  `4,685.59B USD`; all six tab labels present.
- **Live server:** `curl localhost:8501` → **HTTP 200**, no errors in log.
- _Not done:_ visual screenshot — the Claude-in-Chrome extension is not
  connected. `AppTest` actually executes every tab, which is a stronger check
  for runtime errors than a screenshot.

---

## 7. Data coverage (current)

| Domain | Indicator | Rows | Countries |
|--------|-----------|------|-----------|
| Demographics | Population | 1,225 | 49 |
| Demographics | Median Age | **0** | — (needs Eurostat) |
| Economy | GDP | 1,216 | 49 |
| Economy | GDP per capita | 1,216 | 49 |
| Economy | Inflation (HICP) | 1,130 | 46 |
| Economy | Unemployment Rate | 1,097 | 44 |
| Digital & Connectivity | Internet Users % | 1,179 | 49 |
| Digital & Connectivity | Broadband Coverage % | 1,129 | 48 |
| Energy & Green | Greenhouse Gas Emissions | 1,050 | 42 |
| Energy & Green | Renewable Energy Share % | 1,009 | 46 |

**Total: 10,251 rows, 2000–2024.**

---

## 8. Known issues / open items

1. **Eurostat fetcher hangs ~15 min** on every ingestion run (SDMX with no
   timeout, error swallowed). Currently unused. Fix: add a request timeout,
   or disable it until real dataflow keys are wired. Same stubs to finish for
   **ECB** and **OECD** (both return `[]`).
2. **Bloc membership data looks wrong** — `geography_bloc` shows **Eurozone = 3
   countries** and **EU = 28**. Eurozone should be ~20 and EU 27. This is a
   pre-existing seed-data issue (`src/eurodata/reference/blocs.py` /
   `model/seed.py`), **not** introduced this session. It makes the Overview bloc
   rankings misleading. Worth auditing.
3. **Median Age** is empty — no World Bank equivalent. Needs the real Eurostat
   `demo_pjanind` path (or another source).
4. **Two indicators are proxies, not exact matches:** Inflation uses WB CPI (not
   Eurostat HICP); Broadband uses WB fixed-broadband subscriptions/100 (not
   Eurostat household coverage %). Fine for a v1 fallback, but note it before
   presenting these as official EU figures. A cleaner long-term design is
   per-record units/source in `statistic_record` rather than a single
   `indicator.unit`.
5. **AfriNet-scale features not built** (by design for v1): AI validation agents,
   forecasting, correlation engine, social-media/startup domains.

---

## 9. How to run

```bash
# from repo root
source .venv/bin/activate

# (re)ingest data — currently World Bank only; ~15 extra min if Eurostat runs
PYTHONPATH=src python scripts/run_ingestion.py

# launch the dashboard
streamlit run app/streamlit_app.py
# → http://localhost:8501

# tests
PYTHONPATH=src python -m pytest -q
```

Note: the dashboard opens the DB read-only, so ingestion and the app can run at
the same time. `lint = ruff check` is the project standard but **ruff is not
installed** in the current `.venv`.
