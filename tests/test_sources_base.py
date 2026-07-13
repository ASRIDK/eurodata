from eurodata.sources.base import Record, BaseFetcher, parse_period
from eurodata.sources.registry import register, get_fetcher, all_sources


def test_record_defaults():
    r = Record(iso3="DEU", indicator_code="nama_10_gdp", year=2020, value=1.5)
    assert r.quarter is None and r.unit is None


def test_parse_period():
    assert parse_period("2020") == (2020, None, None)
    assert parse_period("2020-Q3") == (2020, 3, None)
    assert parse_period("2020-07") == (2020, None, 7)
    assert parse_period(" 2020-12 ") == (2020, None, 12)
    for bad in ("", "20", "2020-13", "2020-Q5", "2020-W07", "2020-07-15", "n/a"):
        assert parse_period(bad) is None, bad


def test_registry_roundtrip():
    class Dummy(BaseFetcher):
        source_name = "Dummy"
        def fetch(self, start_year: int):
            return [Record("DEU", "x", 2020, 1.0)]
    register(Dummy)
    assert "Dummy" in all_sources()
    assert isinstance(get_fetcher("Dummy"), Dummy)
