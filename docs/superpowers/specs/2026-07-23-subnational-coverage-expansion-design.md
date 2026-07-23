# Subnational coverage expansion — regional data beyond NUTS

_Design spec — 2026-07-23_
_Sub-project of `2026-07-23-country-profile-summary-and-maps-design.md`_

## Purpose

The country-profile regional map covers 33 of 50 countries, because Eurostat's
NUTS 2 regional accounts stop at EU/EFTA/candidate members. This adds regional
coverage for the remaining 17 so that every country profile shows something
truthful, and states plainly where data does not exist.

This is a **separate spec on purpose**. It is a data-sourcing project with its
own sources, geometry, licences and reconciliation problems; folding it into the
profile work would block a finished feature behind an open-ended one. The
profile ships with its empty state and populates as this lands.

## Verified coverage (measured, not assumed)

The 17 are four different problems, not one.

### Group A — microstates: nothing to import (5)

`AND`, `LIE`, `MCO`, `SMR`, `VAT`. These have no meaningful internal
subdivisions. The correct treatment is not an import but a rendering decision:
**the country is its own single region**, shaded with its national value. No
source, no geometry beyond the country outline we already have.

### Group B — covered by DOSE (8)

[DOSE V2.14](https://doi.org/10.5281/zenodo.20035157) (Global Data on Subnational
Economic Output, MCC/Potsdam), a 17.5 MB CSV of 45,389 region-years. Verified
against the file:

| Country | Regions | Years |
| --- | --- | --- |
| RUS | 79 | 1994–2019 |
| UKR | 27 | 1995–2019 |
| CHE | 26 (cantons) | 2008–2018 |
| GEO | 11 | 2006–2019 |
| AZE | 10 | 2006–2019 |
| BLR | 6 | 2009–2019 |
| BIH | 3 | 2003–2019 |
| GBR | 4 (nations only) | 1968–2017 |

### Group C — absent from DOSE, need bespoke national sources (4)

`ISL`, `ARM`, `MDA`, `XKX`. Each needs its own statistics office (Statistics
Iceland, ArmStat, BNS Moldova, Kosovo Agency of Statistics) with its own format
and region definition. Small region counts (roughly 2–8 each), so the work is
per-country integration rather than volume.

### Group D — a Eurostat gap that looks fillable but is not (1, overlaps B)

`CHE` appears in Eurostat's `nama_10r_2gdp` **geo dimension with all 7 NUTS 2
codes, and no values at all** — every Swiss observation is `null`. Our pipeline
already handles this correctly by producing nothing. Switzerland is therefore
sourced from DOSE (cantons, 26 regions) rather than Eurostat.

## Three properties that constrain the design

These are why DOSE data cannot simply be appended to the NUTS series.

1. **Different measure.** DOSE reports *gross regional product per capita in
   USD*; Eurostat reports *GDP per inhabitant in EUR*. Different concept,
   different currency.
2. **Different vintage.** DOSE ends 2017–2019; NUTS 2 runs to 2024. A blended
   European regional map would compare 2024 Polish regions against 2018 Russian
   ones.
3. **Different region system.** DOSE uses GADM `GID_1` codes; ours are NUTS.
   Geometry must come from GADM level 1, not GISCO.

**Consequence, and the central rule of this spec:** the regional map renders
**one source per country**, labelled with its source, unit and year. There is no
pan-European regional choropleth mixing the two. This preserves the project's
provenance-first character rather than manufacturing false comparability.

## Data model

A new indicator, kept separate from the NUTS one:

- `Gross Regional Product per capita (subnational)` — unit `USD`, source
  `DOSE`, `is_proxy = true` with a `proxy_note` explaining it is GRP in USD and
  not comparable with the Eurostat NUTS 2 series.

Regions are seeded into `geography` exactly as NUTS regions are — `code` =
GADM `GID_1`, `parent_id` = the country, `level = 'gadm1'` to distinguish them
from `nuts2`. The existing `statistic_record` path needs no change: the ingestion
pipeline already keys geographies on `geography.code`.

## Components

**`src/eurodata/reference/gadm.py`** — the region catalog (code, name,
parent_iso3) for the 8 DOSE countries, generated from the DOSE CSV and committed,
mirroring how `nuts.py` was derived from Eurostat's live geo dimension.

**`src/eurodata/sources/dose.py`** — a `BaseFetcher` following the existing
source pattern. Reads the Zenodo CSV (pinned to the V2.14 DOI for
reproducibility, not "latest"), filters to the 8 countries, emits `Record`s of
`grp_pc_usd` per region-year. Registered like the other sources so it flows
through `run_all` and appears in the source-health probe.

**`scripts/fetch_geometry.py`** — extended to also emit
`web/frontend/public/geo/gadm1.geojson`, filtered to the 8 countries' regions
and simplified. GADM's full level-1 set is far too large to vendor whole; only
the ~166 regions we use are kept.

**Frontend** — the existing `Choropleth` component takes geometry and a value
map, so it needs no change. The country page picks the geometry file and value
source by country, and renders the source/unit/year label beneath.

## Licensing

DOSE is CC BY 4.0 — attribution required, redistribution permitted. **GADM is
not**: it prohibits commercial redistribution. The plan must verify GADM's terms
before vendoring its geometry, and fall back to Natural Earth admin-1 (public
domain) if they do not permit it. This is a blocking check, not a footnote.

## Testing

- Every code in `gadm.py` has a matching feature in the committed
  `gadm1.geojson` — the same guard that would have caught the NUTS-vintage
  problem in the parent spec.
- The DOSE fetcher normalizes a fixture CSV slice into `Record`s with the right
  region codes, years and units, without touching the network.
- `country_profile` returns the correct source label and unit for a DOSE country
  (RUS) and a NUTS country (FRA), proving the two paths stay distinct.
- A test asserting the DOSE indicator is flagged `is_proxy` with a non-empty
  `proxy_note`, so the incomparability can never be silently dropped.

## Honest limits, to be stated in the UI

- **4 countries (ISL, ARM, MDA, XKX) will still have no regional data** after
  this. Group C is scoped but not solved here; each needs its own integration.
- **The UK gets 4 nations, not ITL regions** — coarser than a UK reader expects.
  ONS ITL data would be a better source and is the obvious follow-up.
- **DOSE data is 5–7 years old.** The map labels its year per country; the
  staleness badge already built for indicators applies.

## Out of scope

- A pan-European regional choropleth mixing sources (deliberately excluded above)
- ONS ITL ingestion for a finer UK breakdown (follow-up)
- Group C's four bespoke national integrations (follow-up, one spec each)
- Any subnational indicator other than GRP per capita
