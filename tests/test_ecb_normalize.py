from eurodata.sources.ecb import normalize_ecb, normalize_ecb_exr


def test_normalize_ecb_currency_and_geo():
    rows = [
        {"REF_AREA": "DE", "TIME_PERIOD": "2020", "OBS_VALUE": 1.2, "CURRENCY": "EUR"},
        {"REF_AREA": "ZZ", "TIME_PERIOD": "2020", "OBS_VALUE": 9.9, "CURRENCY": "EUR"},  # dropped
    ]
    recs = normalize_ecb(rows, indicator_code="ICP.M.DE.N.000000")
    assert len(recs) == 1
    assert recs[0].iso3 == "DEU" and recs[0].currency == "EUR"


def test_normalize_ecb_monthly_periods():
    rows = [
        {"REF_AREA": "FR", "TIME_PERIOD": "2024-03", "OBS_VALUE": "2.85"},
        {"REF_AREA": "FR", "TIME_PERIOD": "2024-W07", "OBS_VALUE": "9.9"},  # weekly dropped
        {"REF_AREA": "IT", "TIME_PERIOD": "2024-11", "OBS_VALUE": "3.55"},
    ]
    recs = normalize_ecb(rows, indicator_code="IRS")
    assert [(r.iso3, r.year, r.month, r.value) for r in recs] == [
        ("FRA", 2024, 3, 2.85), ("ITA", 2024, 11, 3.55)]
    assert all(r.quarter is None for r in recs)


def test_normalize_ecb_exr_maps_currency_to_country():
    rows = [
        {"CURRENCY": "GBP", "TIME_PERIOD": "2024-10", "OBS_VALUE": "0.8349"},
        {"CURRENCY": "PLN", "TIME_PERIOD": "2024-10", "OBS_VALUE": "4.31"},
        {"CURRENCY": "USD", "TIME_PERIOD": "2024-10", "OBS_VALUE": "1.09"},  # non-Europe dropped
    ]
    recs = normalize_ecb_exr(rows, indicator_code="EXR")
    by_iso = {r.iso3: r for r in recs}
    assert set(by_iso) == {"GBR", "POL"}
    assert by_iso["GBR"].value == 0.8349 and by_iso["GBR"].month == 10
    assert by_iso["GBR"].unit == "GBP per EUR" and by_iso["GBR"].currency == "GBP"
