from eurodata.sources.eurostat import SERIES_PARAMS, jsonstat_rows, normalize_eurostat


def _payload():
    # Minimal JSON-stat 2.0 shape: freq(1) x geo(2) x time(2), one value missing.
    return {
        "id": ["freq", "geo", "time"],
        "size": [1, 2, 2],
        "dimension": {
            "freq": {"category": {"index": {"A": 0}}},
            "geo": {"category": {"index": {"DE": 0, "EL": 1}}},
            "time": {"category": {"index": {"2020": 0, "2021": 1}}},
        },
        "value": {"0": 10.0, "1": 11.0, "3": 21.5},
    }


def test_jsonstat_rows_decodes_row_major():
    rows = jsonstat_rows(_payload())
    got = {(r["geo"], r["TIME_PERIOD"]): r["value"] for r in rows}
    assert got == {("DE", "2020"): 10.0, ("DE", "2021"): 11.0,
                   ("EL", "2021"): 21.5}


def test_jsonstat_to_records_end_to_end():
    recs = normalize_eurostat(jsonstat_rows(_payload()), "demo_pjanind")
    by_key = {(r.iso3, r.year): r.value for r in recs}
    assert by_key[("DEU", 2020)] == 10.0
    assert by_key[("GRC", 2021)] == 21.5  # EL -> GRC geo fix


def test_series_params_pin_known_datasets():
    # Guard against accidentally unpinning a dimension (which re-creates the
    # v1 full-dataset hang).
    assert SERIES_PARAMS["demo_pjanind"] == {"indic_de": "MEDAGEPOP"}
    assert SERIES_PARAMS["prc_hicp_aind"]["coicop"] == "CP00"
    assert SERIES_PARAMS["isoc_eb_ai"]["indic_is"] == "E_AI_TANY"
