from eurodata.sources.base import Record
from eurodata.ingest.validate import validate_records


def test_validate_splits_valid_and_rejected():
    recs = [
        Record("DEU", "x", 2020, 100.0),
        Record("DEU", "x", 2020, 100.0),          # duplicate -> rejected
        Record("ZZZ", "x", 2020, 5.0),            # bad iso3 -> rejected
        Record("FRA", "x", 1700, 5.0),            # year out of range -> rejected
        Record("FRA", "x", 2020, float("nan")),   # NaN -> rejected
    ]
    valid, rejected = validate_records(recs)
    assert len(valid) == 1
    reasons = {r[1] for r in rejected}
    assert {"duplicate", "unknown_iso3", "year_out_of_range", "non_finite_value"} <= reasons
