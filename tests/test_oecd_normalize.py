from eurodata.sources.oecd import normalize_oecd


def test_normalize_oecd_iso3_and_aggregates():
    rows = [
        {"REF_AREA": "DEU", "TIME_PERIOD": "2025-03", "OBS_VALUE": "3.4"},
        {"REF_AREA": "JPN", "TIME_PERIOD": "2025-03", "OBS_VALUE": "2.5"},   # non-Europe dropped
        {"REF_AREA": "OECD", "TIME_PERIOD": "2025-03", "OBS_VALUE": "4.9"},  # aggregate dropped
        {"REF_AREA": "EA", "TIME_PERIOD": "2025-03", "OBS_VALUE": "6.2"},    # aggregate dropped
    ]
    recs = normalize_oecd(rows, indicator_code="DF_IALFS_UNE_M", unit="%")
    assert len(recs) == 1
    r = recs[0]
    assert (r.iso3, r.year, r.month, r.value, r.unit) == ("DEU", 2025, 3, 3.4, "%")


def test_normalize_oecd_annual_still_works():
    rows = [{"REF_AREA": "FRA", "TIME_PERIOD": "2020", "OBS_VALUE": "8.0"}]
    recs = normalize_oecd(rows, indicator_code="X")
    assert recs[0].year == 2020 and recs[0].month is None and recs[0].quarter is None
