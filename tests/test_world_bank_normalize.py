from eurodata.sources.world_bank import normalize_world_bank


def test_normalize_world_bank_uses_iso3_and_skips_nulls():
    rows = [
        {"countryiso3code": "DEU", "date": "2020", "value": 100.0},
        {"countryiso3code": "FRA", "date": "2019", "value": None},  # dropped
        {"countryiso3code": "USA", "date": "2020", "value": 5.0},   # non-Europe dropped
    ]
    recs = normalize_world_bank(rows, indicator_code="SP.POP.TOTL")
    assert len(recs) == 1
    assert recs[0].iso3 == "DEU" and recs[0].year == 2020
