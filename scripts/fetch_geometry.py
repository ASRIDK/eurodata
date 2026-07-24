"""Fetch and trim the map geometry the country profile renders.

Writes two GeoJSON files into web/frontend/public/geo/. They are committed to
the repo rather than fetched at runtime, so builds are reproducible and the app
has no runtime dependency on a third-party host. Re-run this to refresh them.

Source: Eurostat GISCO, © EuroGeographics for the administrative boundaries,
CC BY 4.0 — attribution is rendered on the page.

Two source details are load-bearing and were verified against our catalog:

* NUTS **2024**, not 2021. The 2021 vintage is missing seven regions we carry
  (NL35, NL36, PT19, PT1A-PT1D) because NUTS 2024 split them; 2024 matches all
  293 of ours exactly.
* Countries join on ``ISO3_CODE``, not ``CNTR_ID``. GISCO's country id follows
  the EU's convention (``UK``, ``EL``) rather than ISO (``GB``, ``GR``), which
  silently loses three of our countries.

Kosovo (XKX) has no feature at all: GISCO does not distinguish it from Serbia.
That is a property of the source, and the page says so rather than shading
Kosovo as part of another country.

    python scripts/fetch_geometry.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

try:
    from _bootstrap import ensure_paths
    ensure_paths()
except ModuleNotFoundError:
    pass

from eurodata.reference.countries import COUNTRIES  # noqa: E402
from eurodata.reference.nuts import NUTS2_REGIONS  # noqa: E402

GISCO = "https://gisco-services.ec.europa.eu/distribution/v2"
NUTS_URL = f"{GISCO}/nuts/geojson/NUTS_RG_60M_2024_4326_LEVL_2.geojson"
CNTR_URL = f"{GISCO}/countries/geojson/CNTR_RG_60M_2020_4326.geojson"

OUT_DIR = Path(__file__).resolve().parent.parent / "web/frontend/public/geo"

# Everything east/south of this is dropped from the country file: GISCO ships
# the whole world, and we only ever draw Europe.
EUROPE_BBOX = (-32.0, 32.0, 74.0, 84.0)  # west, south, east, north


def _get(url: str) -> dict:
    print(f"  fetching {url.rsplit('/', 1)[-1]} ...", flush=True)
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)


def _round_coords(obj, ndigits: int = 3):
    """Trim coordinate precision. At 60M resolution three decimals (~100m) is
    already far finer than a continent-scale SVG can show, and it roughly halves
    the file."""
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(c), ndigits) for c in obj]
        return [_round_coords(o, ndigits) for o in obj]
    return obj


def _slim(feature: dict, keep: dict[str, str]) -> dict:
    """Drop every property except the ones we render, and rename them to a
    single shape so the frontend does not care which file it loaded."""
    props = feature["properties"]
    return {
        "type": "Feature",
        "properties": {new: props.get(old) for old, new in keep.items()},
        "geometry": {
            "type": feature["geometry"]["type"],
            "coordinates": _round_coords(feature["geometry"]["coordinates"]),
        },
    }


def build_countries() -> dict:
    data = _get(CNTR_URL)
    wanted = {c["iso3"] for c in COUNTRIES}
    w, s, e, n = EUROPE_BBOX
    out = []
    for f in data["features"]:
        iso3 = f["properties"].get("ISO3_CODE")
        if iso3 not in wanted:
            continue
        out.append(_slim(f, {"ISO3_CODE": "id", "NAME_ENGL": "name"}))
    missing = wanted - {f["properties"]["id"] for f in out}
    print(f"  countries: {len(out)} features, missing {sorted(missing) or 'none'}")
    return {"type": "FeatureCollection", "features": out,
            "bbox": [w, s, e, n]}


def build_nuts2() -> dict:
    data = _get(NUTS_URL)
    wanted = {r["code"] for r in NUTS2_REGIONS}
    out = [_slim(f, {"NUTS_ID": "id", "NAME_LATN": "name"})
           for f in data["features"] if f["properties"].get("NUTS_ID") in wanted]
    missing = wanted - {f["properties"]["id"] for f in out}
    print(f"  nuts2: {len(out)} features, missing {sorted(missing) or 'none'}")
    if missing:
        print("  WARNING: regions without geometry will not render. Check the "
              "NUTS vintage in NUTS_URL against reference/nuts.py.", file=sys.stderr)
    return {"type": "FeatureCollection", "features": out}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, build in (("europe-countries", build_countries), ("nuts2", build_nuts2)):
        path = OUT_DIR / f"{name}.geojson"
        # separators: GeoJSON is mostly punctuation; dropping the spaces after
        # commas is a free ~15% on a file this shape.
        path.write_text(json.dumps(build(), separators=(",", ":")))
        print(f"  wrote {path.relative_to(OUT_DIR.parent.parent.parent.parent)} "
              f"({path.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
