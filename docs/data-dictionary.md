# Data dictionary

## Core tables

| Table | Contents |
|-------|----------|
| `geography` | 50 European countries (ISO2/ISO3, transcontinental/disputed flags) |
| `bloc`, `geography_bloc` | EU, Eurozone, Schengen, EFTA, EEA, NATO memberships with `since_year`/`until_year`. **Current membership queries must filter `until_year IS NULL`** (e.g. GBR has EU membership 1973–2020). |
| `domain` | Demographics, Economy, Digital & Connectivity, Energy & Green, AI & Technology, Governance & Geopolitics |
| `indicator` | 32 indicators (7 domains): `unit`, `api_code` (source series key), `definition`, `is_proxy`, `proxy_note` |
| `source` | Source organizations with `license` and `redistributable` |
| `statistic_record` | Facts: value, unit, year, `vintage_date` (revision lineage), `retrieved_at` |
| `event` | Curated events: `event_type`, `iso3`/`bloc_code` scope, dates, `source_url`, `confidence`, `tags`, `affected_domains` |
| `ingestion_run` | One row per source per pipeline run: `completed` / `completed_with_errors` / `failed` / `skipped` (+ reason) |
| `ingestion_error` | Per-series fetch failures (source, series, error, timestamp) |
| `raw_snapshot` | Raw response cache metadata |
| `graph_node`, `graph_edge` | Structural graph |

## Views

- `statistic_current` — latest vintage per (geography, indicator, source, period).
- `statistic_best` — one value per (geography, indicator, period), preferring
  the indicator's priority source, then the lowest source id (Eurostat < World
  Bank). **Use this view for analysis** — the API and dashboard do.

## Indicators

Run `ed.indicators()` for the full catalog with definitions. Proxy indicators
(`is_proxy = TRUE`):

| Indicator | Proxy note |
|-----------|-----------|
| Inflation (HICP) | World Bank rows are CPI inflation (FP.CPI.TOTL.ZG), not Eurostat HICP. Eurostat HICP rows (exact) are preferred where present. |
| Broadband Coverage % | Fixed broadband subscriptions per 100 people, not household coverage %. |
| Government Debt (% GDP) | Central government debt (IMF GFS), not Maastricht general government debt; sparse coverage. |

Monetary aggregates (GDP, GDP per capita) are **current US$** (World Bank).
