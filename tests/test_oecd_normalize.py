from eurodata.sources.oecd import normalize_oecd


def test_normalize_oecd_iso3_direct():
    rows = [
        {"LOCATION": "DEU", "TIME_PERIOD": "2020", "ObsValue": 3.3},
        {"LOCATION": "JPN", "TIME_PERIOD": "2020", "ObsValue": 4.4},  # non-Europe dropped
    ]
    recs = normalize_oecd(rows, indicator_code="GDP")
    assert len(recs) == 1 and recs[0].iso3 == "DEU"
