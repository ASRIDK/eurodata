# Country profile — summary and maps

_Design spec — 2026-07-23_

## Purpose

Turn `/country/[iso3]` from a KPI grid into a page that answers "what is this
country like, and where does it sit in Europe" at a glance: a prose summary
assembled from the country's own figures, a map placing it in European context,
and a map of its internal regional spread.

The correlations section is **removed**. It presented graph relationships that
belong on `/correlations` and `/propagate`, not on a country's basic profile.

## Verified facts this design rests on

Measured this session, not assumed:

| Fact | Value |
| --- | --- |
| Countries in the catalog | 50 |
| Countries with **any** NUTS 2 data | **33** — 17 have none |
| Indicators available at NUTS 2 level | **1** (GDP per capita, 6,896 rows) |
| Geometry currently in the repo | **none** — no GeoJSON, TopoJSON, or shapes |
| NUTS **2021** geometry vs our regions | 286 of 293 — misses NL35, NL36, PT19, PT1A–PT1D |
| NUTS **2024** geometry vs our regions | **293 of 293, zero missing** |
| GISCO countries joined on `CNTR_ID` | 47 of 50 — GISCO uses `UK` and `EL`, we use `GB`/`GR` |
| GISCO countries joined on `ISO3_CODE` | **49 of 50** — only Kosovo missing |

Two of these change the design outright: the NUTS **2024** vintage is required
(2021 silently drops seven regions), and countries must join on `ISO3_CODE`, not
`CNTR_ID`.

## Geometry assets

Vendored under `web/frontend/public/geo/`, committed, with
`scripts/fetch_geometry.py` to regenerate them. Vendoring keeps builds
reproducible and removes a runtime dependency on a third-party host.

| File | Source | Notes |
| --- | --- | --- |
| `nuts2.geojson` | GISCO `NUTS_RG_60M_2024_4326_LEVL_2` | 434 KB raw; all 293 regions match |
| `europe-countries.geojson` | GISCO `CNTR_RG_60M_2020_4326` | 723 KB raw, filtered to our 50 → far smaller |

Both are CC BY 4.0. The page carries a "© EuroGeographics / Eurostat GISCO"
attribution. `fetch_geometry.py` filters to the codes we actually use and drops
unused properties, so the committed files stay as small as the data allows.

## Rendering — no map library

GeoJSON in lat/lng projects to SVG paths in roughly thirty lines. Adding d3-geo
or Leaflet for two static choropleths would be disproportionate in a codebase
that lazy-loads even recharts. A single generic component serves both maps:

```tsx
<Choropleth
  geojson={...}            // FeatureCollection
  featureId={(f) => ...}   // ISO3_CODE or NUTS_ID
  values={{ FRA: 7.5 }}    // id -> number
  highlight="FRA"          // outlined
  unit="%"
/>
```

It computes a bounding box from the features, projects with a plain
equirectangular transform corrected by `cos(mean latitude)` (adequate for a
continent-scale static map; a conformal projection buys nothing here), applies a
sequential colour scale, and renders a legend. Countries with no value render in
a neutral "no data" fill, which is a real state — several indicators do not
cover all 50.

Both maps are lazily imported so they add nothing to other routes' bundles,
following the existing `block-chart-lazy` pattern.

## Data — facts in Python, sentences in TSX

New `EuroData.country_profile(country) -> dict`, exposed as
`GET /api/country-profile?country=`:

```python
{
  "iso3": "FRA", "name": "France", "iso2": "FR",
  "blocs": [{"code": "EU", "name": "European Union", "since_year": 1958}, ...],
  "headline": [                       # one per KPI_INDICATORS entry
    {"indicator": "GDP", "value": 3.37e12, "unit": "USD", "period": "2025",
     "rank": 2, "of": 44, "median": 4.1e11}
  ],
  "fastest_rising":  {"indicator": "Renewable Energy Share %", "change": 11.2,
                      "unit": "%", "from_year": 2015, "to_year": 2025},
  "fastest_falling": {...},
  "n_indicators": 46,
  "last_year": 2025,
}
```

Rank and median come from `latest(indicator)`, which already returns every
country's newest value for an indicator (44 rows for Unemployment Rate).
Rise/fall is the 10-year change per indicator, expressed in the indicator's own
unit — not a percentage of a percentage.

**The split is deliberate.** Facts, ranks and deltas are computed in Python where
the data lives and where they are unit-testable. The frontend only composes
sentences from them, so the prose can never drift from the numbers rendered
beside it — the failure mode that ruled out generating the summary with the
model.

## The page

Order after the change:

1. Flag, name, ISO codes, bloc chips *(unchanged)*
2. **Summary paragraph** *(new)*
3. KPI grid *(unchanged)*
4. **Europe in context** *(new)* — choropleth of all 50 countries for a selected
   indicator, this country outlined, with its rank stated
5. **Regional spread** *(new)* — NUTS 2 choropleth of this country's own regions,
   GDP per capita
6. Recent events *(unchanged)*
7. "Explore full time series" link *(unchanged)*
8. ~~Strongest correlations~~ **removed**

Summary wording, assembled from the facts above:

> France is the 2nd largest of 44 European economies by GDP ($3.37T, 2025), with
> 68.7M people. A member of the European Union since 1958 and the Eurozone since
> 1999. Unemployment is 7.5%, above the European median of 5.9%. Across 46
> tracked indicators, its fastest rise over the last decade is Renewable Energy
> Share % (+11.2pp) and its steepest fall is Greenhouse Gas Emissions (−18.4%).

Every clause is dropped when its fact is unavailable, rather than printed with a
placeholder.

## Honest gaps, handled explicitly

- **17 of 50 countries have no NUTS 2 data.** Those pages state that regional
  data is not available for the country instead of rendering an empty map.
- **Only GDP per capita exists at NUTS 2 level**, so the regional map has no
  indicator selector. The Europe map does.
- **Kosovo (XKX) has no geometry in GISCO** — it is absorbed into Serbia's
  polygon, because not all EU members recognise it. Highlighting Kosovo as part
  of Serbia would be factually wrong, so its page renders the Europe map with no
  highlight and a note that the source geometry does not distinguish it. This is
  a property of the source, and the page says so rather than hiding it.
- Indicators already carry staleness and proxy flags; the summary states the
  period for every figure it quotes, so a 2020 value is never presented as current.

## Error handling

- Unknown country → existing `EuroDataLookupError` → 404, as elsewhere in the API.
- A geometry file failing to load → the section renders its heading and a short
  "map unavailable" line; the rest of the profile is unaffected.
- An indicator with no value for this country → neutral fill on the map, clause
  omitted from the summary. Not an error.

## Testing

**Python:** `country_profile` against the in-memory fixture — rank and median
correct against a known set, blocs with join years, rise/fall picking the right
indicator and sign, and the shape returned for a country with sparse data.
Endpoint tested via TestClient including the 404.

**Geometry:** a test asserting every code in `NUTS2_REGIONS` has a matching
feature in the committed `nuts2.geojson`, and every country in `COUNTRIES`
except `XKX` has one in `europe-countries.geojson`. This is what would have
caught the 2021-vintage problem, and it will catch a future re-fetch that
regresses it.

**Frontend:** `next build`, `eslint` at 0, and a Playwright drive of a country
with regional data (FRA), one without (ISL), and Kosovo — asserting the summary
renders, both maps appear where expected, the correct empty states appear where
not, no horizontal overflow at 390px, and no console errors.

## Out of scope

- Any map interaction beyond hover — no pan, zoom, or click-through
- Regional data for indicators other than GDP per capita (none exists)
- Replacing the globe on the home page
