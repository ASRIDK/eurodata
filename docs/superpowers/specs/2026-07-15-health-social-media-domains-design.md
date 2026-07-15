# Design: Health & Social Media domains

**Date:** 2026-07-15
**Status:** Approved (design), pending implementation plan

## Goal

Add two new real-source data domains to the eurodata catalog — **Health** and
**Social Media** — following the established append-only catalog + fetcher-mapping
pattern. Every indicator maps to a live, redistributable official source (World
Bank or Eurostat); no synthetic data, no un-sourced proxies. This continues the
"More domains" roadmap item.

Scope decisions taken during brainstorming:

- The planned names "AI & Innovation" and "Startups & Investment" already exist
  in the catalog as **AI & Technology** and **Startups & Business**. They are
  left untouched — only **Health** and **Social Media** are new.
- Social Media is scoped to *usage* statistics (the only officially published,
  redistributable social-media data). Platform/engagement metrics (TikTok users,
  hours/day, market share) come only from private, non-redistributable sources
  and are explicitly out of scope.

## Resulting catalog totals

- Domains: 7 → **9**
- Indicators: 37 → **47** (+7 Health, +3 Social Media)

## Health domain — 7 indicators (World Bank, CC BY 4.0)

All verified live 2026-07-15 against api.worldbank.org for FRA/DEU/POL, 2010–2023.
For each, the catalog `api_code` **is** the World Bank series code (self-mapping in
`WB_CODES`), matching the v2/v3 convention.

| Name | api_code | Unit | Notes (verified coverage) |
|---|---|---|---|
| Health Expenditure (% GDP) | `SH.XPD.CHEX.GD.ZS` | % | current health expenditure, 42 non-null, →2023 |
| Physicians | `SH.MED.PHYS.ZS` | per 1,000 people | 40 non-null, →2023 |
| Hospital Beds | `SH.MED.BEDS.ZS` | per 1,000 people | 40 non-null, →2023 |
| Out-of-pocket Health Spending | `SH.XPD.OOPC.CH.ZS` | % of current health exp | 42 non-null, →2023 |
| Measles Immunization | `SH.IMM.MEAS` | % of children 12–23 months | 42 non-null, →2023 |
| Infant Mortality | `SP.DYN.IMRT.IN` | per 1,000 live births | 42 non-null, →2023 |
| Suicide Mortality | `SH.STA.SUIC.P5` | per 100,000 people | 36 non-null, series ends ~2021 (WHO lag) |

Life Expectancy already lives in the Demographics domain (`SP.DYN.LE00.IN`) and is
deliberately **not** duplicated here.

## Social Media domain — 3 indicators (Eurostat, CC BY 4.0)

All verified live 2026-07-15 against the Eurostat JSON API; each filter set pins
exactly one series per country/year.

| Name | dataset | Dimension pin | Unit | Coverage |
|---|---|---|---|---|
| Individuals in Social Networks | `isoc_ci_ac_i` | `indic_is=I_IUSNET, unit=PC_IND, ind_type=IND_TOTAL` | % of individuals | 43 geos, 2011–2025 |
| Youth (16–24) in Social Networks | `isoc_ci_ac_i` | `indic_is=I_IUSNET, unit=PC_IND, ind_type=Y16_24` | % of individuals 16–24 | 43 geos, 2011–2025 |
| Enterprises Using Social Media | `isoc_cismt` | `indic_is=E_SM1_ANY, unit=PC_ENT, size_emp=GE10, nace_r2=C10-S951_X_K` | % of enterprises 10+ | 41 geos, biennial 2014–2025 |

## Architecture / wiring changes

The pattern is fixed; the work is mechanical and append-only.

1. **`src/eurodata/reference/catalog.py`**
   - Append 2 entries to `DOMAINS` (colors `#9D755D`, `#BAB0AC` — the two unused
     Vega category-10 slots).
   - Append 10 entries to `INDICATORS` (append-only preserves positional seed ids).
   - Health entries follow the "api_code = WB series code" convention; Social Media
     entries use the Eurostat dataset id as api_code, except the youth cut (see #3).

2. **`src/eurodata/sources/world_bank.py`**
   - Add 7 self-mapping entries to `WB_CODES` (`"SH.XPD.CHEX.GD.ZS": "SH.XPD.CHEX.GD.ZS"`, etc.).

3. **`src/eurodata/sources/eurostat.py`**
   - Add `SERIES_PARAMS` entries for the three Social Media series.
   - The two `isoc_ci_ac_i` cuts share one dataset id, which the current
     `fetch()` loop cannot express (it keys directly on dataset id = api_code).
     Change: allow a `SERIES_PARAMS` key of the form `"<dataset>#<suffix>"` to
     mean "this catalog api_code, fetched from `<dataset>`." The loop splits on
     `#` to derive the dataset for the HTTP call while emitting records under the
     full catalog api_code. Existing keys without `#` are unaffected.
   - Concretely: catalog api_code for the youth indicator is `isoc_ci_ac_i#Y16_24`;
     the total indicator keeps `isoc_ci_ac_i`.

4. **Tests** (hardcoded catalog counts live here per project convention)
   - `tests/test_seed.py`, `tests/test_api.py`, `tests/test_graph_build.py`:
     bump domain count 7 → 9 and indicator count 37 → 47.
   - Add a focused unit test for the new Eurostat `#`-suffix dataset-split logic
     (parses `isoc_ci_ac_i#Y16_24` → dataset `isoc_ci_ac_i`, api_code kept whole).

5. **DB rebuild + ingestion** (full rebuild chosen this round)
   - Stop any uvicorn/read process (DuckDB write-lock), then
     `PYTHONPATH=src python scripts/init_db.py` and run ingestion
     (`run_ingestion.py`, or per-source). Raw snapshots land in `data/raw/`.
   - World Bank's API was intermittently timing out on 2026-07-15; ingestion may
     need a retry pass. Empty/failed series are logged to `ingestion_error` and
     do not fail the run — matching documented graceful-degradation behavior.

## Testing / verification

- `PYTHONPATH=src python -m pytest -q` — full suite green with bumped counts.
- Spot-check one indicator per new domain via `ed.statistic_best` (e.g.
  Health Expenditure and Individuals in Social Networks) returns real rows.
- Confirm both new domains appear in the web backend catalog response
  (`GET /api/...` domain/indicator listing) so the frontend Explore/graph pages
  pick them up.

## Out of scope

- Renaming or expanding AI & Technology / Startups & Business.
- Any private-source social-media data (platform metrics, engagement).
- Frontend changes beyond what the existing domain-driven pages render automatically.
