from eurodata.sources.ecb import normalize_ecb


def test_normalize_ecb_currency_and_geo():
    rows = [
        {"REF_AREA": "DE", "TIME_PERIOD": "2020", "OBS_VALUE": 1.2, "CURRENCY": "EUR"},
        {"REF_AREA": "ZZ", "TIME_PERIOD": "2020", "OBS_VALUE": 9.9, "CURRENCY": "EUR"},  # dropped
    ]
    recs = normalize_ecb(rows, indicator_code="ICP.M.DE.N.000000")
    assert len(recs) == 1
    assert recs[0].iso3 == "DEU" and recs[0].currency == "EUR"
