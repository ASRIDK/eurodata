"""The committed map geometry must cover every code we render.

This is the guard that would have caught the NUTS-2021-vintage problem (seven
regions silently missing) before it reached the map, and it will catch a future
re-fetch that regresses coverage.
"""
import json
from pathlib import Path

from eurodata.reference.countries import COUNTRIES
from eurodata.reference.nuts import NUTS2_REGIONS

GEO = Path(__file__).resolve().parent.parent / "web/frontend/public/geo"


def _ids(filename: str) -> set[str]:
    data = json.loads((GEO / filename).read_text())
    return {f["properties"]["id"] for f in data["features"]}


def test_every_nuts2_region_has_geometry():
    missing = {r["code"] for r in NUTS2_REGIONS} - _ids("nuts2.geojson")
    assert not missing, f"NUTS2 regions without geometry: {sorted(missing)}"


def test_every_country_except_kosovo_has_geometry():
    # GISCO does not distinguish Kosovo from Serbia; that gap is handled in the
    # UI, so it is the one permitted exception.
    missing = {c["iso3"] for c in COUNTRIES} - _ids("europe-countries.geojson")
    assert missing == {"XKX"}, f"unexpected countries without geometry: {sorted(missing - {'XKX'})}"
