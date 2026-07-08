from eurodata.sources.eurostat import normalize_eurostat


def test_normalize_maps_geo_and_filters_non_europe():
    # Simulated tidy rows from a Eurostat SDMX response.
    rows = [
        {"geo": "DE", "TIME_PERIOD": "2020", "value": 100.0, "unit": "EUR"},
        {"geo": "FR", "TIME_PERIOD": "2020", "value": 200.0, "unit": "EUR"},
        {"geo": "US", "TIME_PERIOD": "2020", "value": 999.0, "unit": "EUR"},  # non-Europe, dropped
        {"geo": "EL", "TIME_PERIOD": "2019", "value": 50.0, "unit": "EUR"},   # EL -> GRC
    ]
    recs = normalize_eurostat(rows, indicator_code="nama_10_gdp")
    by_iso = {(r.iso3, r.year): r.value for r in recs}
    assert by_iso[("DEU", 2020)] == 100.0
    assert by_iso[("GRC", 2019)] == 50.0
    assert all(r.iso3 != "USA" for r in recs)
    assert len(recs) == 3
