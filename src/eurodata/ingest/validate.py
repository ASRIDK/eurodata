from __future__ import annotations

import math

from eurodata.reference.countries import COUNTRIES
from eurodata.reference.nuts import NUTS2_REGIONS
from eurodata.sources.base import Record

# Record.iso3 doubles as a generic geography code: country iso3 or, for
# sub-national indicators, a NUTS 2 region code (both land in geography.code).
_VALID_ISO3 = {c["iso3"] for c in COUNTRIES} | {r["code"] for r in NUTS2_REGIONS}
_MIN_YEAR, _MAX_YEAR = 1900, 2035


def validate_records(records: list[Record]) -> tuple[list[Record], list[tuple[Record, str]]]:
    valid: list[Record] = []
    rejected: list[tuple[Record, str]] = []
    seen: set[tuple] = set()
    for r in records:
        if r.iso3 not in _VALID_ISO3:
            rejected.append((r, "unknown_iso3")); continue
        if r.value is None or (isinstance(r.value, float) and not math.isfinite(r.value)):
            rejected.append((r, "non_finite_value")); continue
        if not (_MIN_YEAR <= r.year <= _MAX_YEAR):
            rejected.append((r, "year_out_of_range")); continue
        key = (r.iso3, r.indicator_code, r.year, r.quarter, r.month)
        if key in seen:
            rejected.append((r, "duplicate")); continue
        seen.add(key)
        valid.append(r)
    return valid, rejected
