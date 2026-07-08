# eurodata — Design Spec (v1)

> Status: Approved for planning
> Date: 2026-07-08
> Reference project: AdemMarghli/AfriNet (see `docs/reference/afrinet-reference.md`)

## 1. Purpose

**eurodata** is an open-source, file-based **European data intelligence dataset** covering all of
geographical Europe (~44 countries). It aggregates trustworthy statistics from official sources,
models the relationships between countries/indicators/sources as a **graph**, and ships everything
as downloadable open files (Parquet / CSV / DuckDB / GraphML). A light Streamlit dashboard supports
exploration.

The mission is to be *the most trustworthy open European dataset* for research, analysis, and
investment — plus a structural relationship graph on top.

## 2. Scope

### In scope (v1)
- Ingestion pipeline (registry-based fetchers) for **4 domains**: Demographics, Economy,
  Digital & Connectivity, Energy & Green.
- Primary sources: **Eurostat** (primary), **ECB**, **OECD**, **World Bank**.
- Single-fact-table DuckDB store with data lineage / revision vintages.
- **Structural graph** (nodes + edges) stored in DuckDB, materialized to NetworkX for metrics
  (centrality, community detection). Edge types: `MEMBER_OF`, `BORDERS`, `TRADES_WITH`,
  `BELONGS_TO`, `PROVIDES`.
- Rule-based validation (no LLM).
- Light Streamlit exploration dashboard.
- Versioned open-data release bundle (redistributable sources only).

### Deferred to v2 (explicitly NOT in v1)
- **Correlation edges** (`CORRELATES_WITH`) — require rigorous methodology: growth-rate/first-difference
  correlation (not levels), multiple-comparison (FDR) correction, and lagged / Granger-style
  directionality. Building these naively produces spurious garbage; deferred until done properly.
- **Neuro engine** (spreading-activation propagation over the correlation graph). Depends on v2
  correlation edges.
- **Forecasting** (trend projection). Deferred so v1 concentrates on dataset trustworthiness.
- Additional domains: Health, AI/Innovation, Startups & Investment, Social Media.
- Sub-national NUTS-region data (schema is forward-compatible; not populated in v1).

## 3. Key Design Decisions (with rationale)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **DuckDB for both facts and graph** (graph as node/edge tables), NetworkX materialized on demand. No KùzuDB. | Graph is tiny (~thousands of nodes, tens of thousands of edges) — fits in memory. Avoids a young extra dependency and keeps the whole dataset a single downloadable file. |
| D2 | **One fact table + SQL views.** No denormalized per-domain tables. | AfriNet's biggest flaw was maintaining both a fact table and per-domain tables that drift out of sync. Single source of truth. |
| D3 | **Keep revision history via vintages.** `statistic_record` unique on `(geography, indicator, source, year, quarter, month, vintage_date)`; never overwrite. | Official sources revise figures (e.g. Eurostat revises GDP). Point-in-time lineage makes releases reproducible and auditable. |
| D4 | **Unified `geography` table** with `level` + `parent_id`. | Forward-compatible for NUTS sub-national regions (Europe's research/investment superpower) without a future schema rewrite. v1 populates `level='country'` only. |
| D5 | **Rule-based validation, no LLM agents.** | European official data is clean and well-documented; deterministic rules (ranges, z-scores, gaps, dedup) are simpler, testable, and sufficient. |
| D6 | **Per-source `redistributable` flag** gates the release bundle. | "Open dataset" collides with source terms. Eurostat/World Bank are redistributable with attribution; commercial sources are link-only. Bundle includes only what we may legally re-host. |
| D7 | **Explicit currency / price-basis columns** on facts (`unit`, `currency`, `price_basis`). | Cross-country economic comparison is misleading without nominal/real/PPP + currency context. |
| D8 | **SDMX client for Eurostat + ECB + OECD.** | All three expose SDMX APIs; one client library (`pandasdmx`/`sdmx1`) handles all three. World Bank via `wbgapi`. |

## 4. Architecture

```
                    ┌─────────────── INGESTION ───────────────┐
  Eurostat/ECB/OECD │  sources/ (registry + BaseFetcher)       │
  World Bank        │  → normalized records + provenance       │
                    │  → raw snapshots cached (reproducibility) │
                    └───────────────────┬──────────────────────┘
                                        │  rule-based validation
                                        ▼
                    ┌─────────── FACTS (DuckDB) ───────────┐
                    │  geography, bloc, domain, indicator,   │
                    │  source, statistic_record (+ vintages) │
                    │  views: _current, _best                │
                    └───────────────────┬────────────────────┘
                                        │  graph/build.py
                                        ▼
                    ┌─────────── GRAPH (DuckDB tables) ─────┐
                    │  graph_node, graph_edge                │
                    │  → materialized to NetworkX for metrics│
                    │  (centrality, Louvain communities)     │
                    └───────────────────┬────────────────────┘
                                        │
              ┌─────────────────────────┴──────────────────────────┐
              ▼                                                     ▼
   app/streamlit_app.py                              export/release.py
   (Plotly + pyvis exploration)          versioned bundle: Parquet/CSV/DuckDB/GraphML
                                         (redistributable sources only) → GitHub/Zenodo
```

## 5. Data Model (DuckDB)

### Reference tables
- **`geography`** — `(id, code, level ['country'|'nuts1'|'nuts2'|'nuts3'], parent_id, name, iso2, iso3,
  official_name, capital, latitude, longitude, area_km2, is_transcontinental, is_disputed, note)`.
  v1: `level='country'` only.
- **`bloc`** — `(id, code, name)` for EU, Eurozone, Schengen, EFTA, EEA.
- **`geography_bloc`** — `(geography_id, bloc_id, since_year, until_year)` membership over time.
- **`domain`** — `(id, name, description, color)`.
- **`indicator`** — `(id, domain_id, name, unit, description, api_code, source_priority,
  is_forecastable, frequency)`.
- **`source`** — `(id, name, organization, url, api_endpoint, reliability_score, license,
  redistributable BOOLEAN, update_frequency)`.

### Fact table
- **`statistic_record`** — `(id, geography_id, indicator_id, source_id, year, quarter, month,
  value, unit, currency, price_basis ['nominal'|'real'|'ppp'|NULL], confidence_score, is_estimated,
  vintage_date, retrieved_at)`.
  Unique: `(geography_id, indicator_id, source_id, year, quarter, month, vintage_date)`.
- **View `statistic_current`** — latest `vintage_date` per series/period.
- **View `statistic_best`** — applies `indicator.source_priority` to pick one winning source when
  multiple sources cover the same series.

### Provenance / operations
- **`raw_snapshot`** — `(id, source, endpoint, params, retrieved_at, file_path, sha256)`.
- **`ingestion_run`** — `(id, source, started_at, ended_at, status, records_processed, error)`.

### Graph tables
- **`graph_node`** — `(id, node_type ['country'|'indicator'|'domain'|'source'|'bloc'], ref_id, label)`.
- **`graph_edge`** — `(id, src_node_id, dst_node_id, edge_type, weight, props JSON)`.
  v1 edge types: `MEMBER_OF`, `BORDERS`, `TRADES_WITH`, `BELONGS_TO`, `PROVIDES`.

## 6. Components (units, each independently testable)

| Unit | Responsibility | Depends on |
|------|----------------|------------|
| `config.py` | Pydantic settings from `.env` | pydantic-settings |
| `db.py` | DuckDB connection + schema init | duckdb |
| `model/schema.sql` | All table + view DDL | — |
| `reference/` (`countries`, `blocs`, `borders`) | Canonical country list, bloc memberships, border adjacency | — |
| `model/seed.py` | Seed reference tables from `reference/` + domain/indicator/source catalog | db, reference |
| `sources/base.py` | `BaseFetcher` interface → `list[Record]` (normalized `{iso3, indicator_code, year, value, unit, ...}`) | — |
| `sources/registry.py` | Register/lookup fetchers | base |
| `sources/eurostat|ecb|oecd|world_bank.py` | One fetcher each | pandasdmx / wbgapi |
| `ingest/snapshot.py` | Cache + hash raw pulls | requests |
| `ingest/validate.py` | Rule-based QA (ranges, z-score, gaps, dedup, ISO norm) | — |
| `ingest/pipeline.py` | Orchestrate fetch → validate → upsert; log runs | sources, validate, db |
| `graph/build.py` | Populate `graph_node`/`graph_edge` from facts + reference | db, reference |
| `graph/metrics.py` | NetworkX centrality + Louvain communities | networkx, python-louvain |
| `export/release.py` | Build versioned bundle (redistributable only) | db |
| `app/streamlit_app.py` + `components.py` | Read-only exploration dashboard | streamlit, plotly, pyvis |

## 7. Data Flow

1. `scripts/run_ingestion.py` → `ingest/pipeline.py` iterates registered sources.
2. Each fetcher pulls from its API; `snapshot.py` caches raw response with `retrieved_at` + `sha256`.
3. Records normalized to a common shape, then `validate.py` applies rule-based checks.
4. Valid records upserted into `statistic_record` with a `vintage_date` (new vintages preserved).
5. `scripts/build_graph.py` → `graph/build.py` builds nodes/edges from facts + reference tables.
6. `graph/metrics.py` computes centrality/communities (materialized to NetworkX).
7. Dashboard reads `statistic_current`/`statistic_best` + graph tables.
8. `scripts/make_release.py` → `export/release.py` produces the versioned open bundle.

## 8. Error Handling

- Fetchers wrapped with `tenacity` retries (network/rate-limit); failures logged to `ingestion_run`,
  pipeline continues with other sources (partial success is acceptable).
- Validation failures are recorded (not silently dropped): flagged records get `is_estimated`/low
  `confidence_score` or are quarantined with a reason, never silently overwritten.
- Missing/unknown ISO3 or unmapped indicator codes → skipped with a logged warning.
- Graph build is idempotent (truncate + rebuild) to avoid partial-state corruption.

## 9. Testing Strategy

- **Fetcher unit tests** — mock SDMX/API responses, assert normalization correctness (per source).
- **Schema/load tests** — build a fixture DuckDB, assert upsert + vintage-uniqueness behavior.
- **Validation tests** — each rule (range, z-score, gap, dedup, ISO norm) with pass/fail fixtures.
- **Graph build tests** — known reference input → expected node/edge counts and types.
- **Metrics tests** — small hand-built graph → known centrality/community results.
- **Release test** — assert non-redistributable sources are excluded from the bundle.
- Framework: `pytest`.

## 10. Country List Policy (D-c)

Canonical list = geographical Europe sovereign states (~44). Handling of edge cases:
- **Transcontinental** (Russia, Turkey): included, `is_transcontinental = true`.
- **Disputed** (Kosovo): included with code `XKX`/`XK`, `is_disputed = true`, `note` documenting
  inconsistent source coverage.
- **Micro-states** (Andorra, Monaco, San Marino, Liechtenstein, Vatican): included; expect data gaps
  surfaced by coverage tracking rather than excluded.
- Caucasus (Georgia, Armenia, Azerbaijan): included as geographical Europe.

## 11. Tech Stack

Python 3.11+ · duckdb, pandas, pyarrow · pandasdmx (or sdmx1), wbgapi, requests · networkx,
python-louvain · streamlit, plotly, pyvis · pydantic-settings, tenacity, python-dotenv · pytest.

## 12. Distribution

`make_release.py` produces `data/releases/eurodata-vX/`:
- `facts.parquet` (long format) + per-domain CSVs
- `eurodata.duckdb` (queryable)
- `graph_nodes.csv`, `graph_edges.csv`, `eurodata.graphml`
- `data_dictionary.md`, `sources.md` (with per-source license), `CHANGELOG.md`
Published to **GitHub Releases**; **Zenodo** for a citable DOI.
